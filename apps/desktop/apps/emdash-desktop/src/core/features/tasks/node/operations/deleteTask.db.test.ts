import { openFixture } from '@tooling/utils/db';
import { eq } from 'drizzle-orm';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import {
  createWorkspaceRegistry,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import { tasks } from '@core/services/app-db/node/schema';
import { reconcileSweepTriggers } from '@core/services/reconcile-sweep/node/reconcile-sweep-triggers';
import type { MementosRuntimeClient } from '@core/services/runtime-broker/api/clients';
import { deleteTask, type TaskDeletionDependencies } from './deleteTask';

/**
 * Task deletion as a plain function (operation-log retirement spec §3, §7): the
 * desktop-local stages complete immediately in one transaction, the host-artifact half
 * rides the workspace removal verbs (reachable → verb, unreachable → durable tombstone,
 * ADR 0006), and nothing submits to the operations kernel — the dependency surface has
 * no submitter at all. Ported from the retired delete-task-definition tests.
 */
describe('deleteTask', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
  });

  afterEach(() => {
    fixture.close();
  });

  async function seedTask(options: { workspace?: boolean } = {}): Promise<void> {
    await fixture.db.insert(workspaces).values({
      id: 'repo-root',
      type: 'local',
      kind: 'repository',
      location: 'local',
      path: '/repo',
    });
    fixture.sqlite
      .prepare(
        `INSERT INTO projects (id, name, repository_workspace_id) VALUES ('project-1', 'Project', 'repo-root')`
      )
      .run();
    if (options.workspace !== false) {
      await fixture.db.insert(workspaces).values({
        id: 'workspace-1',
        type: 'local',
        kind: 'worktree',
        location: 'local',
        path: '/repo/.worktrees/example',
        parentId: 'repo-root',
        config: {
          version: '2',
          git: {
            kind: 'create-branch',
            branchName: 'example',
            fromBranch: { type: 'local', branch: 'main' },
          },
          workspace: { kind: 'new-worktree' },
        },
      });
    }
    await fixture.db.insert(tasks).values({
      id: 'task-1',
      projectId: 'project-1',
      name: 'Task',
      status: 'in_progress',
      workspaceId: options.workspace !== false ? 'workspace-1' : null,
    });
  }

  function seedTaskConversation(id: string): void {
    const registry = createConversationRegistry(fixture.db);
    registry.adopt({
      id,
      title: `Conversation ${id}`,
      provider: 'claude',
      type: 'acp',
      location: 'local',
      workspacePath: '/repo/.worktrees/example',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
      observedStatus: 'present',
    });
    registry.annotate(id, { taskId: 'task-1', projectId: 'project-1' });
  }

  function makeRuntimes() {
    const registry = {
      deleteWorktree: vi.fn(async (_input: { workspaceId: string; deleteBranch: boolean }) => ({
        success: true as const,
        data: undefined,
      })),
      deleteWorkspace: vi.fn(async (_input: { workspaceId: string }) => ({
        success: true as const,
        data: undefined,
      })),
    };
    const runtimes = {
      client: vi.fn(async () => ({
        success: true as const,
        data: { workspaceRegistry: registry },
      })),
    };
    return { registry, runtimes };
  }

  function unreachableRuntimes() {
    return {
      client: vi.fn(async () => ({
        success: false as const,
        error: { type: 'host-unreachable' as const, message: 'ssh down' },
      })),
    };
  }

  function makeDependencies(runtimes: TaskDeletionDependencies['runtimes']) {
    const sessionCleanup = {
      resolve: vi.fn(async () => ({
        acpConversationIds: [] as string[],
        tuiConversationIds: [] as string[],
        terminalSessionIds: [] as string[],
        tmuxSessionNames: [] as string[],
      })),
      killAcp: vi.fn(async () => {}),
      killTerminals: vi.fn(async () => {}),
    };
    const mementos = {
      deleteBySubject: vi.fn(async () => ({ success: true as const, data: undefined })),
    };
    const telemetry = { capture: vi.fn() };
    const unregisterFileSearchRoot = vi.fn();
    const dependencies: TaskDeletionDependencies = {
      db: fixture.db,
      runtimes,
      sessionCleanup,
      getMementosRuntimeClient: async () => mementos as unknown as MementosRuntimeClient,
      telemetry,
      unregisterFileSearchRoot,
    };
    return { dependencies, sessionCleanup, mementos, telemetry, unregisterFileSearchRoot };
  }

  it('deletes desktop rows immediately and removes the worktree through the verb when reachable', async () => {
    await seedTask();
    const { registry, runtimes } = makeRuntimes();
    const { dependencies, telemetry, mementos } = makeDependencies(runtimes);

    const result = await deleteTask(dependencies, { taskId: 'task-1' });

    expect(result.success).toBe(true);
    const taskRows = await fixture.db.select().from(tasks).where(eq(tasks.id, 'task-1'));
    expect(taskRows).toHaveLength(0);
    expect(registry.deleteWorktree).toHaveBeenCalledWith({
      workspaceId: 'workspace-1',
      deleteBranch: false,
    });
    expect(createWorkspaceRegistry(fixture.db).getLive('workspace-1')).toBeUndefined();
    expect(mementos.deleteBySubject).toHaveBeenCalled();
    expect(telemetry.capture).toHaveBeenCalledWith('task_deleted', {
      project_id: 'project-1',
      task_id: 'task-1',
    });
  });

  it('passes deleteBranch through to the verb', async () => {
    await seedTask();
    const { registry, runtimes } = makeRuntimes();
    const { dependencies } = makeDependencies(runtimes);

    await deleteTask(dependencies, { taskId: 'task-1', deleteBranch: true });

    expect(registry.deleteWorktree).toHaveBeenCalledWith({
      workspaceId: 'workspace-1',
      deleteBranch: true,
    });
  });

  it('completes the desktop half without queueing workspace recovery when the host drops', async () => {
    await seedTask();
    const { dependencies } = makeDependencies(unreachableRuntimes());
    const poked = vi.fn();
    const unsubscribe = reconcileSweepTriggers.subscribe(poked);

    const result = await deleteTask(dependencies, { taskId: 'task-1' });
    unsubscribe();

    expect(result.success).toBe(true);
    // Desktop stages never block on the host: the task row is already gone.
    expect(await fixture.db.select().from(tasks).where(eq(tasks.id, 'task-1'))).toHaveLength(0);
    // The workspace row stays unchanged and can be removed explicitly after access returns.
    const row = createWorkspaceRegistry(fixture.db).getLive('workspace-1');
    expect(row?.deletionTombstone).toBeNull();
    expect(poked).not.toHaveBeenCalled();
  });

  it('cascades accepted conversation deletion as conversation-registry tombstones', async () => {
    await seedTask();
    seedTaskConversation('conv-1');
    const { runtimes } = makeRuntimes();
    const { dependencies } = makeDependencies(runtimes);

    const result = await deleteTask(dependencies, { taskId: 'task-1' });

    expect(result.success).toBe(true);
    // The record stays live as the pending state with its own durable tombstone —
    // converged by the conversations reconcile-sweep kind, never a kernel submit.
    const row = createConversationRegistry(fixture.db).getLive('conv-1');
    expect(row?.deletionTombstone).toMatchObject({ targetRecordId: 'conv-1' });
  });

  it('declined conversation cascade unlinks the records into the discovery surface', async () => {
    await seedTask();
    seedTaskConversation('conv-1');
    const { runtimes } = makeRuntimes();
    const { dependencies } = makeDependencies(runtimes);

    const result = await deleteTask(dependencies, {
      taskId: 'task-1',
      deleteConversations: false,
    });

    expect(result.success).toBe(true);
    const row = createConversationRegistry(fixture.db).getLive('conv-1');
    expect(row).toMatchObject({ taskId: null, projectId: null, deletionTombstone: null });
  });

  it('never removes a shared workspace: unlink only when another live task references it', async () => {
    await seedTask();
    await fixture.db.insert(tasks).values({
      id: 'task-2',
      projectId: 'project-1',
      name: 'Sibling',
      status: 'in_progress',
      workspaceId: 'workspace-1',
    });
    const { registry, runtimes } = makeRuntimes();
    const { dependencies } = makeDependencies(runtimes);

    const result = await deleteTask(dependencies, { taskId: 'task-1' });

    expect(result.success).toBe(true);
    expect(await fixture.db.select().from(tasks).where(eq(tasks.id, 'task-1'))).toHaveLength(0);
    expect(registry.deleteWorktree).not.toHaveBeenCalled();
    expect(createWorkspaceRegistry(fixture.db).getLive('workspace-1')).toBeDefined();
  });

  it('keeps the worktree when deleteWorktree is declined', async () => {
    await seedTask();
    const { registry, runtimes } = makeRuntimes();
    const { dependencies } = makeDependencies(runtimes);

    const result = await deleteTask(dependencies, { taskId: 'task-1', deleteWorktree: false });

    expect(result.success).toBe(true);
    expect(registry.deleteWorktree).not.toHaveBeenCalled();
    expect(createWorkspaceRegistry(fixture.db).getLive('workspace-1')).toBeDefined();
  });

  it('never destroys a scanner-adopted worktree even when deletion defaults on', async () => {
    await seedTask();
    await fixture.db
      .update(workspaces)
      .set({ config: null, origin: 'adopted' })
      .where(eq(workspaces.id, 'workspace-1'));
    const { registry, runtimes } = makeRuntimes();
    const { dependencies } = makeDependencies(runtimes);

    const result = await deleteTask(dependencies, { taskId: 'task-1' });

    expect(result.success).toBe(true);
    expect(registry.deleteWorktree).not.toHaveBeenCalled();
    expect(registry.deleteWorkspace).not.toHaveBeenCalled();
    expect(createWorkspaceRegistry(fixture.db).getLive('workspace-1')).toBeDefined();
  });

  it('never interprets task deletion as directory artifact deletion', async () => {
    await seedTask();
    await fixture.db
      .update(workspaces)
      .set({ kind: 'directory', config: null })
      .where(eq(workspaces.id, 'workspace-1'));
    const { registry, runtimes } = makeRuntimes();
    const { dependencies } = makeDependencies(runtimes);

    const result = await deleteTask(dependencies, { taskId: 'task-1' });

    expect(result.success).toBe(true);
    expect(registry.deleteWorktree).not.toHaveBeenCalled();
    expect(registry.deleteWorkspace).not.toHaveBeenCalled();
    expect(createWorkspaceRegistry(fixture.db).getLive('workspace-1')).toBeDefined();
  });

  it('kills sessions best-effort: a cleanup failure never blocks the deletion', async () => {
    await seedTask();
    const { runtimes } = makeRuntimes();
    const { dependencies, sessionCleanup } = makeDependencies(runtimes);
    sessionCleanup.resolve.mockRejectedValueOnce(new Error('runtime gone'));

    const result = await deleteTask(dependencies, { taskId: 'task-1' });

    expect(result.success).toBe(true);
    expect(await fixture.db.select().from(tasks).where(eq(tasks.id, 'task-1'))).toHaveLength(0);
  });

  it('returns task-not-found for an unknown id without touching anything', async () => {
    const { registry, runtimes } = makeRuntimes();
    const { dependencies } = makeDependencies(runtimes);

    const result = await deleteTask(dependencies, { taskId: 'missing' });

    expect(result).toEqual({
      success: false,
      error: { type: 'task-not-found', message: 'Task missing was not found' },
    });
    expect(registry.deleteWorktree).not.toHaveBeenCalled();
  });

  it('refuses while the project is being deleted', async () => {
    await seedTask();
    fixture.sqlite
      .prepare(`UPDATE projects SET deleted_at = '2026-01-01T00:00:00.000Z' WHERE id = 'project-1'`)
      .run();
    const { runtimes } = makeRuntimes();
    const { dependencies } = makeDependencies(runtimes);

    const result = await deleteTask(dependencies, { taskId: 'task-1' });

    expect(result.success).toBe(false);
    if (!result.success) expect(result.error.type).toBe('project-deleting');
    expect(await fixture.db.select().from(tasks).where(eq(tasks.id, 'task-1'))).toHaveLength(1);
  });
});

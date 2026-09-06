import { openFixture } from '@tooling/utils/db';
import { eq } from 'drizzle-orm';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import {
  createWorkspaceRegistry,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import { tasks } from '@core/services/app-db/node/schema';
import { deleteWorkspaceThroughRegistry } from './workspace-removal';

/**
 * Workspace removal through the registry verbs (ADR 0005): one fail-fast host RPC,
 * then the mirror row untracks. An unavailable attachment or mid-call disconnect
 * refuses without creating recovery work. Conversation coupling stays spec §7.1:
 * archive semantics by default, explicit per-record deletes on opt-in.
 */
describe('deleteWorkspaceThroughRegistry', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
  });

  afterEach(() => {
    fixture.close();
  });

  async function seedWorktree(kind: 'worktree' | 'directory' = 'worktree'): Promise<void> {
    await fixture.db.insert(workspaces).values({
      id: 'repo-root',
      type: 'local',
      kind: 'repository',
      location: 'local',
      path: '/repo',
    });
    await fixture.db.insert(workspaces).values({
      id: 'workspace-1',
      type: 'local',
      kind,
      location: 'local',
      path: '/repo/.worktrees/example',
      parentId: 'repo-root',
    });
  }

  function seedConversationAtPath(id: string, workspacePath: string): void {
    createConversationRegistry(fixture.db).adopt({
      id,
      title: `Conversation ${id}`,
      provider: 'claude',
      type: 'acp',
      location: 'local',
      workspacePath,
      lastObservedAt: '2026-01-01T00:00:00.000Z',
      observedStatus: 'present',
    });
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

  it('calls the deleteWorktree verb and untracks the mirror row on success', async () => {
    await seedWorktree();
    const { registry, runtimes } = makeRuntimes();

    const result = await deleteWorkspaceThroughRegistry(fixture.db, runtimes, 'workspace-1', {
      deleteBranch: true,
    });

    expect(result.success).toBe(true);
    expect(registry.deleteWorktree).toHaveBeenCalledWith({
      workspaceId: 'workspace-1',
      deleteBranch: true,
    });
    expect(registry.deleteWorkspace).not.toHaveBeenCalled();
    expect(createWorkspaceRegistry(fixture.db).getLive('workspace-1')).toBeUndefined();
    // Reachable-host removals never tombstone: the verb call is the whole story.
    const [row] = await fixture.db
      .select()
      .from(workspaces)
      .where(eq(workspaces.id, 'workspace-1'));
    expect(row?.deletionTombstone).toBeNull();
  });

  it('routes directory rows through the deleteWorkspace verb', async () => {
    await seedWorktree('directory');
    const { registry, runtimes } = makeRuntimes();

    const result = await deleteWorkspaceThroughRegistry(fixture.db, runtimes, 'workspace-1');

    expect(result.success).toBe(true);
    expect(registry.deleteWorkspace).toHaveBeenCalledWith({ workspaceId: 'workspace-1' });
    expect(registry.deleteWorktree).not.toHaveBeenCalled();
    expect(createWorkspaceRegistry(fixture.db).getLive('workspace-1')).toBeUndefined();
  });

  describe('unreachable host: fail-fast without recovery work', () => {
    function unreachableRuntimes() {
      return {
        client: vi.fn(async () => ({
          success: false as const,
          error: { type: 'host-unreachable' as const, message: 'ssh down' },
        })),
      };
    }

    it('refuses without changing the durable row or conversations', async () => {
      await seedWorktree();
      seedConversationAtPath('conv-stay', '/repo/.worktrees/example');

      const result = await deleteWorkspaceThroughRegistry(
        fixture.db,
        unreachableRuntimes(),
        'workspace-1',
        { deleteBranch: true, deleteConversations: true }
      );

      expect(result).toEqual({
        success: false,
        error: {
          type: 'project-unavailable',
          message: 'This action requires live Project access.',
        },
      });
      const row = createWorkspaceRegistry(fixture.db).getLive('workspace-1');
      expect(row).toBeDefined();
      expect(row?.deletionTombstone).toBeNull();
      expect(createConversationRegistry(fixture.db).getLive('conv-stay')).toBeDefined();
    });

    it('refuses repeated calls without recording queued intent', async () => {
      await seedWorktree();
      const runtimes = unreachableRuntimes();

      const first = await deleteWorkspaceThroughRegistry(fixture.db, runtimes, 'workspace-1', {
        deleteBranch: true,
      });
      const second = await deleteWorkspaceThroughRegistry(fixture.db, runtimes, 'workspace-1', {
        deleteBranch: false,
      });

      expect(first.success).toBe(false);
      expect(second.success).toBe(false);
      expect(
        createWorkspaceRegistry(fixture.db).getLive('workspace-1')?.deletionTombstone
      ).toBeNull();
    });

    it('refuses when the verb reports a mid-call disconnect', async () => {
      await seedWorktree();
      const { registry, runtimes } = makeRuntimes();
      registry.deleteWorktree.mockResolvedValueOnce({
        success: false,
        error: { type: 'host-unreachable', message: 'went away mid-call' },
      } as never);

      const result = await deleteWorkspaceThroughRegistry(fixture.db, runtimes, 'workspace-1');

      expect(result).toEqual({
        success: false,
        error: {
          type: 'project-unavailable',
          message: 'This action requires live Project access.',
        },
      });
      expect(
        createWorkspaceRegistry(fixture.db).getLive('workspace-1')?.deletionTombstone
      ).toBeNull();
    });

    it('still refuses while a live task references the workspace — no tombstone', async () => {
      await seedWorktree();
      fixture.sqlite
        .prepare(`INSERT INTO projects (id, name) VALUES ('project-1', 'Project')`)
        .run();
      await fixture.db.insert(tasks).values({
        id: 'task-1',
        projectId: 'project-1',
        name: 'Task',
        status: 'in_progress',
        workspaceId: 'workspace-1',
      });

      const result = await deleteWorkspaceThroughRegistry(
        fixture.db,
        unreachableRuntimes(),
        'workspace-1'
      );

      expect(result.success).toBe(false);
      if (!result.success) expect(result.error.type).toBe('workspace-in-use');
      expect(
        createWorkspaceRegistry(fixture.db).getLive('workspace-1')?.deletionTombstone
      ).toBeNull();
    });
  });

  it('surfaces a failed verb without untracking', async () => {
    await seedWorktree();
    const { registry, runtimes } = makeRuntimes();
    registry.deleteWorktree.mockResolvedValueOnce({
      success: false,
      error: { type: 'remove-failed', message: 'locked worktree' },
    } as never);

    const result = await deleteWorkspaceThroughRegistry(fixture.db, runtimes, 'workspace-1');

    expect(result).toEqual({
      success: false,
      error: { type: 'delete-failed', message: 'locked worktree' },
    });
    expect(createWorkspaceRegistry(fixture.db).getLive('workspace-1')).toBeDefined();
  });

  it('refuses while a live task still references the workspace, without calling the host', async () => {
    await seedWorktree();
    fixture.sqlite.prepare(`INSERT INTO projects (id, name) VALUES ('project-1', 'Project')`).run();
    await fixture.db.insert(tasks).values({
      id: 'task-1',
      projectId: 'project-1',
      name: 'Task',
      status: 'in_progress',
      workspaceId: 'workspace-1',
    });
    const { registry, runtimes } = makeRuntimes();

    const result = await deleteWorkspaceThroughRegistry(fixture.db, runtimes, 'workspace-1');

    expect(result.success).toBe(false);
    if (!result.success) expect(result.error.type).toBe('workspace-in-use');
    expect(registry.deleteWorktree).not.toHaveBeenCalled();
    expect(createWorkspaceRegistry(fixture.db).getLive('workspace-1')).toBeDefined();
  });

  it('keeps conversation records by default — archive semantics', async () => {
    await seedWorktree();
    seedConversationAtPath('conv-keep', '/repo/.worktrees/example');
    const { runtimes } = makeRuntimes();

    const result = await deleteWorkspaceThroughRegistry(fixture.db, runtimes, 'workspace-1');

    expect(result.success).toBe(true);
    // Nothing submits anywhere and nothing tombstones: pure archive semantics.
    // The record survives with a dangling path — resumable if the path is recreated.
    expect(createConversationRegistry(fixture.db).getLive('conv-keep')).toMatchObject({
      workspacePath: '/repo/.worktrees/example',
      deletionTombstone: null,
    });
  });

  it('opt-in tombstones same-path, same-host records for the conversations sweep kind', async () => {
    await seedWorktree();
    seedConversationAtPath('conv-here', '/repo/.worktrees/example');
    seedConversationAtPath('conv-elsewhere', '/repo/.worktrees/other');
    const { runtimes } = makeRuntimes();

    const result = await deleteWorkspaceThroughRegistry(fixture.db, runtimes, 'workspace-1', {
      deleteConversations: true,
    });

    expect(result.success).toBe(true);
    // Nothing queues anywhere (ADR 0006): the tombstoned rows are the durable intent,
    // converged by the conversations reconcile-sweep kind.
    const registry = createConversationRegistry(fixture.db);
    expect(registry.getLive('conv-here')?.deletionTombstone).toMatchObject({
      targetRecordId: 'conv-here',
    });
    expect(registry.getLive('conv-elsewhere')?.deletionTombstone).toBeNull();
  });
});

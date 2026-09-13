import type { Logger } from '@emdash/shared/logger';
import { openFixture } from '@tooling/utils/db';
import { eq } from 'drizzle-orm';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  createWorkspaceRegistry,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import { projects, tasks } from '@core/services/app-db/node/schema';
import { reconcileSweepTriggers } from '@core/services/reconcile-sweep/node/reconcile-sweep-triggers';
import type { MementosRuntimeClient } from '@core/services/runtime-broker/api/clients';
import { deleteProject, type ProjectDeletionDependencies } from './deleteProject';

/**
 * Project deletion as a plain function (operation-log retirement spec §3, §7.3): the
 * project row tombstones first, the desktop-local cascade purges immediately, and each
 * provenance worktree rides the workspace removal surface — reachable removes through
 * the verb, unreachable gets a durable deletion tombstone for the reconcile sweep
 * (ADR 0006). Nothing submits to the operations kernel — the dependency surface has no
 * submitter at all. Ported from the retired delete-project-definition tests.
 */
describe('deleteProject', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
  });

  afterEach(() => {
    fixture.close();
  });

  const provenanceConfig = {
    version: '2' as const,
    git: {
      kind: 'create-branch' as const,
      branchName: 'feature/example',
      fromBranch: { type: 'local' as const, branch: 'main' },
      pushBranch: false,
    },
    workspace: { kind: 'new-worktree' as const },
  };

  async function seedProject(): Promise<void> {
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
    // A provenance worktree (emdash-created: config != NULL) — removal candidate.
    await fixture.db.insert(workspaces).values({
      id: 'workspace-1',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/repo/.worktrees/example',
      parentId: 'repo-root',
      config: provenanceConfig,
    });
    // An adopted worktree (no config) — untrack only, never removed in bulk.
    await fixture.db.insert(workspaces).values({
      id: 'workspace-2',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/repo/.worktrees/adopted',
      parentId: 'repo-root',
    });
    await fixture.db.insert(tasks).values([
      {
        id: 'task-1',
        projectId: 'project-1',
        name: 'Task 1',
        status: 'in_progress',
        workspaceId: 'workspace-1',
      },
      {
        id: 'task-2',
        projectId: 'project-1',
        name: 'Task 2',
        status: 'in_progress',
        workspaceId: 'workspace-2',
      },
    ]);
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

  function makeDependencies(runtimes: ProjectDeletionDependencies['runtimes']) {
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
      deleteOrphans: vi.fn(async () => ({ success: true as const, data: undefined })),
    };
    const projectsManager = { invalidate: vi.fn(async () => {}) };
    const pullRequests = { deleteProjectData: vi.fn(async () => {}) };
    const telemetry = { capture: vi.fn() };
    const dependencies: ProjectDeletionDependencies = {
      db: fixture.db,
      runtimes,
      getMementosRuntimeClient: async () => mementos as unknown as MementosRuntimeClient,
      logger: { warn: vi.fn(), info: vi.fn(), error: vi.fn(), debug: vi.fn() } as unknown as Logger,
      projects: projectsManager as unknown as ProjectDeletionDependencies['projects'],
      pullRequests,
      sessionCleanup,
      telemetry,
    };
    return {
      dependencies,
      mementos,
      projectsManager,
      pullRequests,
      sessionCleanup,
      telemetry,
    };
  }

  it('purges the project cascade and removes provenance worktrees through the verb when reachable', async () => {
    await seedProject();
    const { registry, runtimes } = makeRuntimes();
    const { dependencies, projectsManager, pullRequests, telemetry } = makeDependencies(runtimes);
    projectsManager.invalidate.mockImplementationOnce(async () => {
      const [tombstoned] = await fixture.db
        .select()
        .from(projects)
        .where(eq(projects.id, 'project-1'));
      expect(tombstoned?.deletedAt).not.toBeNull();
      expect(await fixture.db.select().from(tasks)).toHaveLength(2);
    });

    const result = await deleteProject(dependencies, 'project-1');

    expect(result.success).toBe(true);
    expect(
      await fixture.db.select().from(projects).where(eq(projects.id, 'project-1'))
    ).toHaveLength(0);
    expect(await fixture.db.select().from(tasks)).toHaveLength(0);
    // Only the provenance worktree removes host-side; the adopted row and the
    // repository root untrack without a host call.
    expect(registry.deleteWorktree).toHaveBeenCalledTimes(1);
    expect(registry.deleteWorktree).toHaveBeenCalledWith({
      workspaceId: 'workspace-1',
      deleteBranch: false,
    });
    const workspaceRegistry = createWorkspaceRegistry(fixture.db);
    expect(workspaceRegistry.getLive('workspace-1')).toBeUndefined();
    expect(workspaceRegistry.getLive('workspace-2')).toBeUndefined();
    expect(workspaceRegistry.getLive('repo-root')).toBeUndefined();
    expect(pullRequests.deleteProjectData).toHaveBeenCalledWith('project-1');
    expect(projectsManager.invalidate).toHaveBeenCalledWith('project-1', 'deletion');
    expect(projectsManager.invalidate.mock.invocationCallOrder[0]!).toBeLessThan(
      registry.deleteWorktree.mock.invocationCallOrder[0]!
    );
    expect(telemetry.capture).toHaveBeenCalledWith('project_deleted', {
      project_id: 'project-1',
    });
    expect(telemetry.capture).toHaveBeenCalledWith('task_deleted', {
      project_id: 'project-1',
      task_id: 'task-1',
    });
  });

  it('cascades workspace deletion tombstones against an unreachable host and pokes the sweep', async () => {
    await seedProject();
    const { dependencies } = makeDependencies(unreachableRuntimes());
    const poked = vi.fn();
    const unsubscribe = reconcileSweepTriggers.subscribe(poked);

    const result = await deleteProject(dependencies, 'project-1');
    unsubscribe();

    expect(result.success).toBe(true);
    // The desktop cascade never blocks on the host: project and task rows are gone.
    expect(
      await fixture.db.select().from(projects).where(eq(projects.id, 'project-1'))
    ).toHaveLength(0);
    expect(await fixture.db.select().from(tasks)).toHaveLength(0);
    // The provenance worktree stays live carrying the durable tombstone (ADR 0006);
    // the adopted row and repository root untrack regardless of reachability.
    const workspaceRegistry = createWorkspaceRegistry(fixture.db);
    expect(workspaceRegistry.getLive('workspace-1')?.deletionTombstone).toMatchObject({
      targetRecordId: 'workspace-1',
    });
    expect(workspaceRegistry.getLive('workspace-2')).toBeUndefined();
    expect(workspaceRegistry.getLive('repo-root')).toBeUndefined();
    expect(poked).toHaveBeenCalled();
  });

  it('keeps a live tombstone when the removal verb fails on a reachable host', async () => {
    await seedProject();
    const { registry, runtimes } = makeRuntimes();
    registry.deleteWorktree.mockResolvedValueOnce({
      success: false,
      error: { type: 'remove-failed', message: 'locked worktree' },
    } as never);
    const { dependencies } = makeDependencies(runtimes);
    const poked = vi.fn();
    const unsubscribe = reconcileSweepTriggers.subscribe(poked);

    const result = await deleteProject(dependencies, 'project-1');
    unsubscribe();

    // The project row still deletes; the failed host-artifact half never discards its
    // intent (spec §9): the provenance worktree keeps a live tombstone for the sweep's
    // normal transient/terminal retry handling instead of untracking and stranding.
    expect(result.success).toBe(true);
    expect(
      await fixture.db.select().from(projects).where(eq(projects.id, 'project-1'))
    ).toHaveLength(0);
    const workspaceRegistry = createWorkspaceRegistry(fixture.db);
    expect(workspaceRegistry.getLive('workspace-1')?.deletionTombstone).toMatchObject({
      targetRecordId: 'workspace-1',
    });
    expect(workspaceRegistry.getLive('workspace-2')).toBeUndefined();
    expect(workspaceRegistry.getLive('repo-root')).toBeUndefined();
    expect(poked).toHaveBeenCalled();
  });

  it('returns project-not-found for an unknown id', async () => {
    const { runtimes } = makeRuntimes();
    const { dependencies } = makeDependencies(runtimes);

    const result = await deleteProject(dependencies, 'missing');

    expect(result).toEqual({
      success: false,
      error: { type: 'project-not-found', message: 'Project missing was not found' },
    });
  });
});

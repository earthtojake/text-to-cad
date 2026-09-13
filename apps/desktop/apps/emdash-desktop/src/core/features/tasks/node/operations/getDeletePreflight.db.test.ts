import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { workspaceRegistryTable as workspaces } from '@core/features/workspaces/api/node/registry';
import type { WorkspaceConfig } from '@core/primitives/workspaces/api';
import { tasks } from '@core/services/app-db/node/schema';
import { getDeletePreflight } from './getDeletePreflight';

/**
 * Informed confirmation reads the mirror alone: dirty state, changed lines,
 * unpushed commits, and the observation stamp come from the synced registry
 * columns — no git or host round-trip happens during preflight.
 */
describe('getDeletePreflight', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
  });

  afterEach(() => {
    fixture.close();
  });

  const worktreeConfig: WorkspaceConfig = {
    version: '2',
    git: {
      kind: 'create-branch',
      branchName: 'feature/example',
      fromBranch: { type: 'local', branch: 'main' },
    },
    workspace: { kind: 'new-worktree' },
  };

  async function seedTask(input?: {
    observedGit?: NonNullable<typeof workspaces.$inferInsert.observedGit>;
    observedAt?: number;
  }): Promise<void> {
    fixture.sqlite.prepare(`INSERT INTO projects (id, name) VALUES ('project-1', 'Project')`).run();
    await fixture.db.insert(workspaces).values({
      id: 'workspace-1',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/repo/.worktrees/example',
      config: worktreeConfig,
      observedGit: input?.observedGit ?? null,
      observedAt: input?.observedAt ?? null,
    });
    await fixture.db.insert(tasks).values({
      id: 'task-1',
      projectId: 'project-1',
      name: 'Task',
      status: 'in_progress',
      workspaceId: 'workspace-1',
    });
  }

  it('reports mirror-derived stakes without touching git or the host', async () => {
    await seedTask({
      observedGit: {
        version: '2',
        branch: 'feature/example',
        dirty: true,
        diffStats: { added: 12, deleted: 3 },
        ahead: 2,
        behind: 0,
        locked: false,
        prunable: false,
        headOid: null,
        upstream: null,
        prBreadcrumb: null,
      },
      observedAt: 1_700_000_000_000,
    });

    const result = await getDeletePreflight(
      fixture.db,
      { requireAttached: () => ({ success: true, data: {} as never }) },
      ['task-1']
    );

    expect(result.tasks).toEqual([
      {
        taskId: 'task-1',
        hasWorktree: true,
        hasUncommittedChanges: true,
        hasDeletableBranch: true,
        changedLines: { added: 12, deleted: 3 },
        unpushedCommits: 2,
        observedAt: 1_700_000_000_000,
        hostReachable: true,
      },
    ]);
  });

  it('treats a workspace without observations as clean and surfaces unavailable attachment', async () => {
    await seedTask();

    const result = await getDeletePreflight(
      fixture.db,
      {
        requireAttached: () => ({
          success: false,
          error: {
            type: 'attachment-unavailable',
            host: {} as never,
            phase: 'waiting',
          },
        }),
      },
      ['task-1']
    );

    expect(result.tasks[0]).toMatchObject({
      hasWorktree: true,
      hasUncommittedChanges: false,
      changedLines: null,
      unpushedCommits: null,
      observedAt: null,
      hostReachable: false,
    });
  });

  it('returns the no-worktree shape for unknown tasks', async () => {
    const result = await getDeletePreflight(
      fixture.db,
      { requireAttached: () => ({ success: true, data: {} as never }) },
      ['missing']
    );

    expect(result.tasks).toEqual([
      {
        taskId: 'missing',
        hasWorktree: false,
        hasUncommittedChanges: false,
        hasDeletableBranch: false,
        hostReachable: true,
      },
    ]);
  });
});

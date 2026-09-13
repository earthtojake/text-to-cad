import type { WorkspaceRecord } from '@emdash/core/runtimes/workspace-registry/api';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createWorkspaceRegistry } from '@core/features/workspaces/api/node/registry';
import {
  applyWorkspaceRegistrySnapshot,
  WorkspaceIdentityConflictError,
} from './apply-workspace-registry-snapshot';

const LOCAL_HOST = { location: 'local', sshConnectionId: null } as const;

function hostRecord(overrides: Partial<WorkspaceRecord> & { id: string }): WorkspaceRecord {
  return {
    kind: 'worktree',
    path: `/worktrees/${overrides.id}`,
    parentId: 'ws-repo',
    origin: 'registered',
    gitAdminName: overrides.id,
    observedStatus: 'present',
    creation: null,
    lastCreateOutcome: null,
    lastRemovalAttempt: null,
    lifecycle: null,
    git: {
      branch: 'feature/x',
      dirty: true,
      diffStats: { added: 12, deleted: 3 },
      ahead: 1,
      behind: 0,
      locked: false,
      prunable: false,
      headOid: 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678',
      upstream: {
        remote: 'origin',
        mergeRef: 'refs/heads/feature/x',
        remoteUrl: 'https://example.com/acme/app.git',
      },
      prBreadcrumb: 'https://github.com/acme/app/pull/7',
    },
    lastActivatedAt: null,
    createdAt: Date.parse('2026-01-01T00:00:00.000Z'),
    updatedAt: Date.parse('2026-01-02T00:00:00.000Z'),
    lastObservedAt: Date.parse('2026-01-02T00:00:00.000Z'),
    config: null,
    runtime: null,
    ...overrides,
  };
}

/**
 * Convergence from the workspace registry `records` live model (ADR 0005). The mirror
 * is never the authority: deliveries overwrite observation columns wholesale (git
 * block, create outcome, runtime overlay included) and never touch annotations; the
 * sweep follows the missing rules and is scoped to the delivering host.
 */
describe('applyWorkspaceRegistrySnapshot', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
  });

  afterEach(() => {
    fixture.close();
  });

  function seedTask(projectId: string, taskId: string, workspaceId: string): void {
    fixture.sqlite
      .prepare(`INSERT INTO projects (id, name) VALUES (?, ?)`)
      .run(projectId, `project-${projectId}`);
    fixture.sqlite
      .prepare(
        `INSERT INTO tasks (id, project_id, name, status, workspace_id)
         VALUES (?, ?, ?, 'running', ?)`
      )
      .run(taskId, projectId, `task-${taskId}`, workspaceId);
  }

  it('adopts unknown host records with observations populated (wiped-client reconvergence)', async () => {
    const result = await applyWorkspaceRegistrySnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {
        'ws-repo': hostRecord({
          id: 'ws-repo',
          kind: 'repository',
          path: '/repos/app',
          parentId: null,
          gitAdminName: null,
        }),
        'wt-1': hostRecord({
          id: 'wt-1',
          lastCreateOutcome: { status: 'succeeded', at: Date.parse('2026-01-01T12:00:00.000Z') },
        }),
      },
      observedAt: Date.parse('2026-01-03T00:00:00.000Z'),
    });

    expect(result).toEqual({
      adopted: 2,
      refreshed: 0,
      markedMissing: 0,
      untracked: 0,
      purgedTombstones: 0,
    });

    const registry = createWorkspaceRegistry(fixture.db);
    expect(registry.getLive('wt-1')).toMatchObject({
      origin: 'registered',
      kind: 'worktree',
      path: '/worktrees/wt-1',
      parentId: 'ws-repo',
      config: null,
      observedStatus: 'present',
      observedGit: {
        version: '2',
        branch: 'feature/x',
        dirty: true,
        diffStats: { added: 12, deleted: 3 },
        headOid: 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678',
        upstream: {
          remote: 'origin',
          mergeRef: 'refs/heads/feature/x',
          remoteUrl: 'https://example.com/acme/app.git',
        },
        prBreadcrumb: 'https://github.com/acme/app/pull/7',
      },
      lastCreateOutcome: { version: '1', status: 'succeeded' },
      runtimeOverlay: null,
      observedAt: Date.parse('2026-01-03T00:00:00.000Z'),
      location: 'local',
      sshConnectionId: null,
    });

    // Reconvergence is idempotent: a replayed snapshot refreshes instead of duplicating.
    const replay = await applyWorkspaceRegistrySnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {
        'ws-repo': hostRecord({ id: 'ws-repo', kind: 'repository', parentId: null }),
        'wt-1': hostRecord({ id: 'wt-1' }),
      },
    });
    expect(replay).toEqual({
      adopted: 0,
      refreshed: 2,
      markedMissing: 0,
      untracked: 0,
      purgedTombstones: 0,
    });
  });

  it('treats a stored v1 observedGit payload as not yet observed and rewrites it as v2', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.recordCreationIntent({
      id: 'wt-1',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/worktrees/wt-1',
    });
    // The exact JSON a pre-v2 desktop stored: version '1', none of the v2 fields.
    // No upcast exists by design — observations are re-derived by the next scan.
    fixture.sqlite.prepare(`UPDATE workspaces SET observed_git = ? WHERE id = 'wt-1'`).run(
      JSON.stringify({
        version: '1',
        branch: 'feature/x',
        dirty: true,
        diffStats: null,
        ahead: null,
        behind: null,
        locked: false,
        prunable: false,
      })
    );

    expect(registry.getLive('wt-1')?.observedGit).toBeNull();

    // The next delivery persists the v2 payload wholesale.
    await applyWorkspaceRegistrySnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: { 'wt-1': hostRecord({ id: 'wt-1' }) },
    });
    expect(registry.getLive('wt-1')?.observedGit).toMatchObject({
      version: '2',
      branch: 'feature/x',
      headOid: 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678',
      upstream: { remote: 'origin' },
      prBreadcrumb: 'https://github.com/acme/app/pull/7',
    });
  });

  it('overwrites observations wholesale — overlay included — but never touches annotations', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.recordCreationIntent({
      id: 'wt-1',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/worktrees/wt-1',
      config: { version: '2', git: { kind: 'none' }, workspace: { kind: 'new-worktree' } },
    });

    const withOverlay = await applyWorkspaceRegistrySnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {
        'wt-1': hostRecord({
          id: 'wt-1',
          runtime: {
            creation: null,
            notices: [],
            activation: {
              phase: 'active',
              scripts: { prepare: 'succeeded', setup: 'running', run: 'pending' },
              activatedAt: Date.parse('2026-01-05T00:00:00.000Z'),
            },
          },
          lastActivatedAt: Date.parse('2026-01-05T00:00:00.000Z'),
        }),
      },
    });
    expect(withOverlay).toEqual({
      adopted: 0,
      refreshed: 1,
      markedMissing: 0,
      untracked: 0,
      purgedTombstones: 0,
    });
    expect(registry.getLive('wt-1')).toMatchObject({
      observedGit: { branch: 'feature/x', diffStats: { added: 12, deleted: 3 } },
      lastActivatedAt: Date.parse('2026-01-05T00:00:00.000Z'),
      runtimeOverlay: { version: '1', activation: { phase: 'active' } },
      // The rich-provenance annotation is client-owned; the snapshot cannot touch it.
      config: { version: '2', git: { kind: 'none' }, workspace: { kind: 'new-worktree' } },
    });

    // A daemon restart delivers runtime null — the persisted overlay column clears.
    await applyWorkspaceRegistrySnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: { 'wt-1': hostRecord({ id: 'wt-1', runtime: null }) },
    });
    expect(registry.getLive('wt-1')).toMatchObject({ runtimeOverlay: null });
  });

  it('carries removal attempts and script outcomes into the mirror observation columns', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.recordCreationIntent({
      id: 'wt-1',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/worktrees/wt-1',
    });

    await applyWorkspaceRegistrySnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {
        'wt-1': hostRecord({
          id: 'wt-1',
          lastRemovalAttempt: {
            stage: 'remove',
            class: 'terminal',
            message: 'worktree is locked',
            at: Date.parse('2026-01-06T00:00:00.000Z'),
          },
          runtime: {
            creation: null,
            notices: [],
            activation: null,
            lifecycle: [
              {
                id: 'setup',
                status: 'failed',
                startedAt: Date.parse('2026-01-05T00:00:00.000Z'),
                finishedAt: Date.parse('2026-01-05T00:00:01.000Z'),
                message: 'exit 3',
                params: {},
              },
            ],
          },
        }),
      },
    });
    expect(registry.getLive('wt-1')).toMatchObject({
      lastRemovalAttempt: {
        version: '1',
        stage: 'remove',
        class: 'terminal',
        message: 'worktree is locked',
      },
      runtimeOverlay: {
        version: '1',
        lifecycle: [expect.objectContaining({ id: 'setup', status: 'failed' })],
      },
    });

    // Wholesale refresh: a delivery without the blocks clears the columns.
    await applyWorkspaceRegistrySnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: { 'wt-1': hostRecord({ id: 'wt-1' }) },
    });
    expect(registry.getLive('wt-1')).toMatchObject({
      lastRemovalAttempt: null,
      runtimeOverlay: null,
    });
  });

  it('sweeps unmatched rows: annotated go visible-missing, pure mirror rows untrack', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.recordCreationIntent({
      id: 'wt-linked',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/worktrees/linked',
      config: null,
    });
    seedTask('project-1', 'task-1', 'wt-linked');
    registry.adopt({
      id: 'wt-mirror',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/worktrees/mirror',
    });

    const result = await applyWorkspaceRegistrySnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {},
      observedAt: Date.parse('2026-01-07T00:00:00.000Z'),
    });

    expect(result).toEqual({
      adopted: 0,
      refreshed: 0,
      markedMissing: 1,
      untracked: 1,
      purgedTombstones: 0,
    });
    expect(registry.getLive('wt-linked')).toMatchObject({
      observedStatus: 'missing',
      observedAt: Date.parse('2026-01-07T00:00:00.000Z'),
    });
    expect(registry.getLive('wt-mirror')).toBeUndefined();
  });

  it('purges a tombstoned row once the delivery confirms the record gone — annotation included', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.recordCreationIntent({
      id: 'wt-doomed',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/worktrees/doomed',
    });
    // Annotated (task-linked) rows normally stay visible as missing; a deletion
    // tombstone overrides that — the user already asked for the row to go.
    seedTask('project-1', 'task-1', 'wt-doomed');
    registry.tombstone('wt-doomed', {
      version: '1',
      targetRecordId: 'wt-doomed',
      tombstonedAt: Date.parse('2026-01-06T00:00:00.000Z'),
      options: { deleteBranch: true, deleteConversations: false },
    });

    // While the record is still delivered, the tombstoned row refreshes and waits.
    const pending = await applyWorkspaceRegistrySnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: { 'wt-doomed': hostRecord({ id: 'wt-doomed', path: '/worktrees/doomed' }) },
    });
    expect(pending).toEqual({
      adopted: 0,
      refreshed: 1,
      markedMissing: 0,
      untracked: 0,
      purgedTombstones: 0,
    });
    expect(registry.getLive('wt-doomed')?.deletionTombstone).toMatchObject({
      targetRecordId: 'wt-doomed',
    });

    // The record disappears from the delivery: mirror-confirmed gone, purge.
    const purged = await applyWorkspaceRegistrySnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {},
    });
    expect(purged).toEqual({
      adopted: 0,
      refreshed: 0,
      markedMissing: 0,
      untracked: 0,
      purgedTombstones: 1,
    });
    expect(registry.getLive('wt-doomed')).toBeUndefined();
  });

  it('scopes the sweep to the snapshot host; other hosts are untouched', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    fixture.sqlite
      .prepare(
        `INSERT INTO ssh_connections (id, name, host, port, username, auth_type)
         VALUES ('ssh-1', 'box', 'box.example', 22, 'dev', 'agent')`
      )
      .run();
    registry.adopt({
      id: 'wt-remote',
      type: 'project-ssh',
      kind: 'worktree',
      location: 'remote',
      sshConnectionId: 'ssh-1',
      path: '/remote/worktree',
      observedStatus: 'present',
    });

    const result = await applyWorkspaceRegistrySnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {},
    });

    expect(result).toEqual({
      adopted: 0,
      refreshed: 0,
      markedMissing: 0,
      untracked: 0,
      purgedTombstones: 0,
    });
    expect(registry.getLive('wt-remote')).toMatchObject({ observedStatus: 'present' });
  });

  it('rejects an id/path collision before adopting, refreshing, or sweeping anything', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.recordCreationIntent({
      id: 'desktop-id',
      type: 'local',
      kind: 'repository',
      location: 'local',
      path: '/repo',
      observedStatus: 'present',
    });
    registry.adopt({
      id: 'would-be-swept',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/work/old',
      observedStatus: 'present',
    });

    const application = applyWorkspaceRegistrySnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {
        'host-id': hostRecord({
          id: 'host-id',
          kind: 'repository',
          path: '/repo',
          parentId: null,
        }),
      },
    });

    await expect(application).rejects.toMatchObject({
      name: 'WorkspaceIdentityConflictError',
      path: '/repo',
      incomingId: 'host-id',
      conflictingId: 'desktop-id',
    });
    expect(registry.getLive('host-id')).toBeUndefined();
    expect(registry.getLive('desktop-id')).toMatchObject({
      path: '/repo',
      observedStatus: 'present',
    });
    expect(registry.getLive('would-be-swept')).toMatchObject({
      path: '/work/old',
      observedStatus: 'present',
    });
  });

  it('rejects duplicate Host path ownership even when neither id exists locally', async () => {
    await expect(
      applyWorkspaceRegistrySnapshot({
        db: fixture.db,
        host: LOCAL_HOST,
        records: {
          first: hostRecord({ id: 'first', path: '/same' }),
          second: hostRecord({ id: 'second', path: '/same' }),
        },
      })
    ).rejects.toBeInstanceOf(WorkspaceIdentityConflictError);
    expect(createWorkspaceRegistry(fixture.db).getLive('first')).toBeUndefined();
    expect(createWorkspaceRegistry(fixture.db).getLive('second')).toBeUndefined();
  });

  it('applies a valid path swap without depending on snapshot record order', async () => {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.adopt({
      id: 'first',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/first',
    });
    registry.adopt({
      id: 'second',
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path: '/second',
    });

    await expect(
      applyWorkspaceRegistrySnapshot({
        db: fixture.db,
        host: LOCAL_HOST,
        records: {
          first: hostRecord({ id: 'first', path: '/second' }),
          second: hostRecord({ id: 'second', path: '/first' }),
        },
      })
    ).resolves.toMatchObject({ refreshed: 2 });
    expect(registry.getLive('first')).toMatchObject({ path: '/second' });
    expect(registry.getLive('second')).toMatchObject({ path: '/first' });
  });
});

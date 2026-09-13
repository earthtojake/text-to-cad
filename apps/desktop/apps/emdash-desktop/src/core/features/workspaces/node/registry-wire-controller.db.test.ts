import { hostRef, LOCAL_HOST_REF, type HostRef } from '@emdash/core/primitives/host/api';
import type { WorkspaceRecord } from '@emdash/core/runtimes/workspace-registry/api';
import { runtimeHostUnavailable } from '@emdash/core/services/runtime-broker/api';
import { err, ok } from '@emdash/shared';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createWorkspaceRegistry } from '@core/features/workspaces/api/node/registry';
import type { WorkspaceConfig, WorkspaceMirrorRow } from '@core/primitives/workspaces/api';
import type { WorkspaceInsert } from '@core/services/app-db/node/schema';
import { createWorkspaceRegistryWireController } from './registry-wire-controller';
import { applyWorkspaceRegistrySnapshot } from './sync/apply-workspace-registry-snapshot';

const REMOTE_HOST = hostRef('remote', 'ssh-1');

const someConfig: WorkspaceConfig = {
  version: '2',
  git: { kind: 'none' },
  workspace: { kind: 'new-worktree' },
};

function hostRecord(overrides: Partial<WorkspaceRecord> & { id: string }): WorkspaceRecord {
  return {
    kind: 'worktree',
    path: `/worktrees/${overrides.id}`,
    parentId: null,
    origin: 'registered',
    gitAdminName: overrides.id,
    observedStatus: 'present',
    creation: null,
    lastCreateOutcome: null,
    lastRemovalAttempt: null,
    lifecycle: null,
    git: null,
    lastActivatedAt: null,
    createdAt: Date.parse('2026-01-01T00:00:00.000Z'),
    updatedAt: Date.parse('2026-01-01T00:00:00.000Z'),
    lastObservedAt: Date.parse('2026-01-01T00:00:00.000Z'),
    config: null,
    runtime: null,
    ...overrides,
  };
}

/**
 * The consolidated renderer workspace API (ADR 0005): mirror-served reads, 1:1 verb
 * pass-throughs that fail fast with the broker's typed resolve error when the host is
 * unreachable, and the desktop-only durable untrack escape hatch.
 */
describe('createWorkspaceRegistryWireController', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;
  let hostVerbs: Record<string, ReturnType<typeof vi.fn>>;
  let reachable: boolean;
  let sweep: {
    retry: ReturnType<typeof vi.fn<(kind: string, host: HostRef, id: string) => void>>;
    drop: ReturnType<typeof vi.fn<(kind: string, id: string) => void>>;
  };

  beforeEach(async () => {
    fixture = await openFixture('empty');
    reachable = true;
    sweep = {
      retry: vi.fn<(kind: string, host: HostRef, id: string) => void>(),
      drop: vi.fn<(kind: string, id: string) => void>(),
    };
    hostVerbs = {
      createWorkspace: vi.fn(async (input: { workspaceId: string; path: string }) =>
        ok(hostRecord({ id: input.workspaceId, path: input.path }))
      ),
      createWorktree: vi.fn(async (input: { workspaceId: string; path: string }) =>
        ok(hostRecord({ id: input.workspaceId, path: input.path, parentId: 'ws-repo' }))
      ),
      activateWorkspace: vi.fn(async (input: { workspaceId: string }) =>
        ok(hostRecord({ id: input.workspaceId }))
      ),
      deactivateWorkspace: vi.fn(async () => ok(undefined)),
      deleteWorkspace: vi.fn(async () => ok(undefined)),
      deleteWorktree: vi.fn(async () => ok(undefined)),
      refresh: vi.fn(async () => ok(undefined)),
      updateWorktree: vi.fn(async () => ok(undefined)),
    };
  });

  afterEach(() => {
    fixture.close();
  });

  function controller(mintId?: () => string) {
    const broker = {
      client: async () =>
        reachable
          ? ok({ workspaceRegistry: hostVerbs })
          : err(runtimeHostUnavailable(REMOTE_HOST, 'offline')),
    };
    return createWorkspaceRegistryWireController({
      db: fixture.db,
      runtimes: broker as never,
      sweep,
      ...(mintId ? { mintId } : {}),
    });
  }

  function seedRow(id: string, overrides: Partial<WorkspaceInsert> = {}): void {
    createWorkspaceRegistry(fixture.db).recordCreationIntent({
      id,
      type: 'local',
      kind: 'worktree',
      location: 'local',
      sshConnectionId: null,
      path: `/work/${id}`,
      config: someConfig,
      ...overrides,
    });
  }

  function seedRemoteConnection(connectionId: string): void {
    fixture.sqlite
      .prepare(
        `INSERT INTO ssh_connections (id, name, host, username) VALUES (?, ?, 'example.test', 'user')`
      )
      .run(connectionId, connectionId);
  }

  describe('listWorkspaces', () => {
    it('scopes by host, decodes host refs, and hides tombstones unless asked', async () => {
      seedRow('wt-local');
      seedRemoteConnection('ssh-1');
      seedRow('wt-remote', { location: 'remote', sshConnectionId: 'ssh-1', path: '/remote/wt' });
      seedRow('wt-gone', { path: '/work/gone' });
      createWorkspaceRegistry(fixture.db).untrack(['wt-gone'], '2026-01-02T00:00:00.000Z');

      const wire = controller();
      const local = (await wire.call('listWorkspaces', {
        scope: { host: LOCAL_HOST_REF },
      })) as WorkspaceMirrorRow[];
      expect(local.map((row) => row.id).sort()).toEqual(['wt-local']);
      expect(local[0]).toMatchObject({
        host: LOCAL_HOST_REF,
        path: '/work/wt-local',
        config: someConfig,
      });

      const remote = (await wire.call('listWorkspaces', {
        scope: { host: REMOTE_HOST },
      })) as WorkspaceMirrorRow[];
      expect(remote.map((row) => row.id)).toEqual(['wt-remote']);
      expect(remote[0]?.host).toEqual(REMOTE_HOST);

      const withTombstones = (await wire.call('listWorkspaces', {
        scope: { host: LOCAL_HOST_REF },
        includeUntracked: true,
      })) as WorkspaceMirrorRow[];
      expect(withTombstones.map((row) => row.id).sort()).toEqual(['wt-gone', 'wt-local']);
      const tombstone = withTombstones.find((row) => row.id === 'wt-gone');
      expect(tombstone?.untrackedAt).toBe('2026-01-02T00:00:00.000Z');
    });

    it('scopes by project through task links and the repository workspace', async () => {
      seedRow('ws-repo', { kind: 'repository', path: '/work/repo' });
      seedRow('wt-task');
      seedRow('wt-other');
      fixture.sqlite
        .prepare(`INSERT INTO projects (id, name, repository_workspace_id) VALUES (?, ?, ?)`)
        .run('project-1', 'p', 'ws-repo');
      fixture.sqlite
        .prepare(
          `INSERT INTO tasks (id, project_id, name, status, workspace_id)
           VALUES ('task-1', 'project-1', 't', 'running', 'wt-task')`
        )
        .run();

      const rows = (await controller().call('listWorkspaces', {
        scope: { projectId: 'project-1' },
      })) as WorkspaceMirrorRow[];
      expect(rows.map((row) => row.id).sort()).toEqual(['ws-repo', 'wt-task']);
    });
  });

  describe('verb pass-throughs', () => {
    it('mints ids for the create verbs and Claims the mirror row on success', async () => {
      const wire = controller(() => 'minted-id');
      const result = (await wire.call('createWorktree', {
        host: LOCAL_HOST_REF,
        repositoryId: 'ws-repo',
        branch: 'feature/x',
        baseRef: 'origin/main',
        path: '/work/new-wt',
        config: someConfig,
      })) as { success: boolean };

      expect(result.success).toBe(true);
      expect(hostVerbs.createWorktree).toHaveBeenCalledWith({
        workspaceId: 'minted-id',
        repositoryId: 'ws-repo',
        branch: 'feature/x',
        baseRef: 'origin/main',
        path: '/work/new-wt',
        preservePatterns: [],
      });
      // The mirror row exists immediately — links can attach before sync catches up.
      expect(createWorkspaceRegistry(fixture.db).getLive('minted-id')).toMatchObject({
        path: '/work/new-wt',
        config: someConfig,
        origin: 'registered',
        location: 'local',
      });
    });

    it('claims the Host canonical id when the proposed id already has a path owner', async () => {
      hostVerbs.createWorkspace.mockResolvedValueOnce(
        ok(hostRecord({ id: 'canonical-id', kind: 'repository', path: '/work/repo' }))
      );

      const result = await controller(() => 'proposed-id').call('createWorkspace', {
        host: LOCAL_HOST_REF,
        path: '/work/repo',
        config: someConfig,
      });

      expect(result).toMatchObject({ success: true, data: { id: 'canonical-id' } });
      const registry = createWorkspaceRegistry(fixture.db);
      expect(registry.getLive('proposed-id')).toBeUndefined();
      expect(registry.getLive('canonical-id')).toMatchObject({
        path: '/work/repo',
        config: someConfig,
      });
    });

    it('explicitly retracks an untracked canonical id on create success', async () => {
      seedRow('canonical-id', { kind: 'repository', path: '/work/repo' });
      const registry = createWorkspaceRegistry(fixture.db);
      registry.untrack(['canonical-id'], '2026-01-02T00:00:00.000Z');
      hostVerbs.createWorkspace.mockResolvedValueOnce(
        ok(hostRecord({ id: 'canonical-id', kind: 'repository', path: '/work/repo' }))
      );

      await expect(
        controller(() => 'proposed-id').call('createWorkspace', {
          host: LOCAL_HOST_REF,
          path: '/work/repo',
        })
      ).resolves.toMatchObject({ success: true, data: { id: 'canonical-id' } });
      expect(registry.getLive('canonical-id')).toMatchObject({
        path: '/work/repo',
        untrackedAt: null,
      });
    });

    it('returns a typed Claim conflict instead of reviving a Tombstone', async () => {
      seedRow('canonical-id', { kind: 'repository', path: '/work/repo' });
      const registry = createWorkspaceRegistry(fixture.db);
      registry.tombstone('canonical-id', {
        version: '1',
        targetRecordId: 'canonical-id',
        tombstonedAt: 1,
        options: { deleteBranch: false, deleteConversations: false },
      });
      hostVerbs.createWorkspace.mockResolvedValueOnce(
        ok(hostRecord({ id: 'canonical-id', kind: 'repository', path: '/work/repo' }))
      );

      await expect(
        controller(() => 'proposed-id').call('createWorkspace', {
          host: LOCAL_HOST_REF,
          path: '/work/repo',
        })
      ).resolves.toEqual(err({ type: 'workspace-tombstoned', workspaceId: 'canonical-id' }));
      expect(registry.getLive('canonical-id')?.deletionTombstone).not.toBeNull();
    });

    it('passes through host verb inputs and typed host errors unchanged', async () => {
      hostVerbs.deleteWorktree.mockResolvedValueOnce(
        err({ type: 'not-a-worktree', workspaceId: 'ws-1' })
      );
      const wire = controller();

      await expect(
        wire.call('deleteWorktree', {
          host: LOCAL_HOST_REF,
          workspaceId: 'ws-1',
          deleteBranch: true,
        })
      ).resolves.toEqual(err({ type: 'not-a-worktree', workspaceId: 'ws-1' }));
      expect(hostVerbs.deleteWorktree).toHaveBeenCalledWith({
        workspaceId: 'ws-1',
        deleteBranch: true,
      });

      await wire.call('activateWorkspace', { host: LOCAL_HOST_REF, workspaceId: 'ws-2' });
      expect(hostVerbs.activateWorkspace).toHaveBeenCalledWith({ workspaceId: 'ws-2' });
      await wire.call('deactivateWorkspace', { host: LOCAL_HOST_REF, workspaceId: 'ws-2' });
      expect(hostVerbs.deactivateWorkspace).toHaveBeenCalledWith({ workspaceId: 'ws-2' });
      await wire.call('deleteWorkspace', { host: LOCAL_HOST_REF, workspaceId: 'ws-2' });
      expect(hostVerbs.deleteWorkspace).toHaveBeenCalledWith({ workspaceId: 'ws-2' });
      await wire.call('refresh', { host: LOCAL_HOST_REF });
      expect(hostVerbs.refresh).toHaveBeenCalledWith({});
    });

    it('passes the desktop-compiled update instruction through and returns guard refusals unchanged', async () => {
      hostVerbs.updateWorktree.mockResolvedValueOnce(
        err({ type: 'worktree-dirty', workspaceId: 'wt-1' })
      );
      const wire = controller();

      await expect(
        wire.call('updateWorktree', {
          host: LOCAL_HOST_REF,
          workspaceId: 'wt-1',
          remote: 'origin',
          sourceRef: 'refs/pull/42/head',
        })
      ).resolves.toEqual(err({ type: 'worktree-dirty', workspaceId: 'wt-1' }));
      expect(hostVerbs.updateWorktree).toHaveBeenCalledWith({
        workspaceId: 'wt-1',
        remote: 'origin',
        sourceRef: 'refs/pull/42/head',
      });

      await expect(
        wire.call('updateWorktree', {
          host: LOCAL_HOST_REF,
          workspaceId: 'wt-1',
          remote: 'origin',
          sourceRef: 'refs/heads/feature/x',
        })
      ).resolves.toEqual(ok(undefined));
    });

    it('fails fast with the typed resolve error and no side effects when unreachable', async () => {
      reachable = false;
      const wire = controller(() => 'minted-id');

      const result = await wire.call('createWorkspace', {
        host: REMOTE_HOST,
        path: '/remote/repo',
      });
      expect(result).toEqual(err(runtimeHostUnavailable(REMOTE_HOST, 'offline')));
      expect(hostVerbs.createWorkspace).not.toHaveBeenCalled();
      expect(createWorkspaceRegistry(fixture.db).getLive('minted-id')).toBeUndefined();
    });
  });

  describe('untrackWorkspace', () => {
    it('hides a row durably; a later sync delivery does not resurrect it', async () => {
      seedRow('wt-1');
      const wire = controller();
      await wire.call('untrackWorkspace', { workspaceId: 'wt-1' });

      const registry = createWorkspaceRegistry(fixture.db);
      expect(registry.getLive('wt-1')).toBeUndefined();

      // The host still carries the record (unreachable-at-untrack-time host came back).
      const applied = await applyWorkspaceRegistrySnapshot({
        db: fixture.db,
        host: { location: 'local', sshConnectionId: null },
        records: { 'wt-1': hostRecord({ id: 'wt-1', path: '/work/wt-1' }) },
      });
      expect(applied).toEqual({
        adopted: 0,
        refreshed: 0,
        markedMissing: 0,
        untracked: 0,
        purgedTombstones: 0,
      });
      expect(registry.getLive('wt-1')).toBeUndefined();
    });
  });

  describe('needs-attention affordances (ADR 0006)', () => {
    function seedTombstonedRow(id: string): void {
      seedRow(id);
      const registry = createWorkspaceRegistry(fixture.db);
      registry.tombstone(id, {
        version: '1',
        targetRecordId: id,
        tombstonedAt: Date.parse('2026-01-02T00:00:00.000Z'),
        options: { deleteBranch: true, deleteConversations: false },
      });
      // The sweep recorded a durable terminal stop at the current epoch (0).
      registry.recordTombstoneTerminalStop(id, {
        epoch: 0,
        stage: 'remove',
        message: 'worktree is locked',
        at: Date.parse('2026-01-03T00:00:00.000Z'),
      });
    }

    it('retryWorkspaceRemoval durably advances the attempt epoch and pokes the sweep', async () => {
      seedTombstonedRow('wt-stuck');
      const wire = controller();

      await wire.call('retryWorkspaceRemoval', { workspaceId: 'wt-stuck' });

      const row = createWorkspaceRegistry(fixture.db).getLive('wt-stuck');
      // The tombstone survives: retry re-arms the pending deletion, never cancels it.
      // The stale stop stays on the row but is inert behind the advanced epoch.
      expect(row?.deletionTombstone).toMatchObject({
        targetRecordId: 'wt-stuck',
        attemptEpoch: 1,
        terminalStop: { epoch: 0 },
      });
      expect(sweep.retry).toHaveBeenCalledWith('workspaces', LOCAL_HOST_REF, 'wt-stuck');
    });

    it('retryWorkspaceRemoval is a no-op without a pending tombstone', async () => {
      seedRow('wt-plain');
      const wire = controller();

      await wire.call('retryWorkspaceRemoval', { workspaceId: 'wt-plain' });

      expect(sweep.retry).not.toHaveBeenCalled();
    });

    it('abandonWorkspaceRemoval purges the tombstoned row client-side, keeping host artifacts', async () => {
      seedTombstonedRow('wt-abandoned');
      const wire = controller();

      await wire.call('abandonWorkspaceRemoval', { workspaceId: 'wt-abandoned' });

      const registry = createWorkspaceRegistry(fixture.db);
      expect(registry.getLive('wt-abandoned')).toBeUndefined();
      expect(sweep.drop).toHaveBeenCalledWith('workspaces', 'wt-abandoned');
      // No host verb was issued: the artifacts stay.
      expect(hostVerbs.deleteWorktree).not.toHaveBeenCalled();
      expect(hostVerbs.deleteWorkspace).not.toHaveBeenCalled();

      // The durable untrack keeps sync from resurrecting the surviving host record.
      const applied = await applyWorkspaceRegistrySnapshot({
        db: fixture.db,
        host: { location: 'local', sshConnectionId: null },
        records: { 'wt-abandoned': hostRecord({ id: 'wt-abandoned', path: '/work/wt-abandoned' }) },
      });
      expect(applied.adopted).toBe(0);
      expect(registry.getLive('wt-abandoned')).toBeUndefined();
    });
  });
});

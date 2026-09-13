import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  createWorkspaceRegistry,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import {
  findWorkspaceTombstoneConflict,
  tombstoneWorkspaceRow,
} from '@core/features/workspaces/api/node/registry/workspace-tombstones';
import type { WorkspaceRow } from '@core/services/app-db/node/schema';

/**
 * The tombstone-write seam (ADR 0006): atomicity, duplicate suppression (zero rows
 * updated), frozen options fidelity, and the tombstone-aware creation admission check.
 * The retired enqueue-tombstoned tests are prior art for the surviving write half.
 */
describe('workspace deletion tombstones', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
  });

  afterEach(() => {
    fixture.close();
  });

  function seedWorktree(id: string, path: string): WorkspaceRow {
    return createWorkspaceRegistry(fixture.db).recordCreationIntent({
      id,
      type: 'local',
      kind: 'worktree',
      location: 'local',
      path,
      config: {
        version: '2',
        git: {
          kind: 'create-branch',
          branchName: `branch-${id}`,
          fromBranch: { type: 'local', branch: 'main' },
        },
        workspace: { kind: 'new-worktree' },
      },
    });
  }

  it('writes the tombstone atomically with frozen options and the target record UUID', () => {
    const workspace = seedWorktree('ws-1', '/repo/.worktrees/one');

    const result = tombstoneWorkspaceRow(fixture.db, {
      workspace,
      options: { deleteBranch: true, deleteConversations: true },
      createdAt: 1_700_000_000_000,
    });

    expect(result).toEqual({ success: true, data: { outcome: 'tombstoned' } });
    const row = createWorkspaceRegistry(fixture.db).getLive('ws-1');
    expect(row?.deletionTombstone).toEqual({
      version: '1',
      targetRecordId: 'ws-1',
      tombstonedAt: 1_700_000_000_000,
      options: { deleteBranch: true, deleteConversations: true },
    });
    // The row stays live — the visible pending state — and the mark is durable: it is
    // stored in the mirror column itself, so an app restart reads the same bytes back.
    expect(row?.untrackedAt).toBeNull();
    const stored = fixture.sqlite
      .prepare(`SELECT deletion_tombstone FROM workspaces WHERE id = 'ws-1'`)
      .get() as { deletion_tombstone: string };
    expect(JSON.parse(stored.deletion_tombstone)).toMatchObject({ targetRecordId: 'ws-1' });
  });

  it('suppresses a double-fire: the second write is a duplicate and the first options win', () => {
    const workspace = seedWorktree('ws-1', '/repo/.worktrees/one');

    const first = tombstoneWorkspaceRow(fixture.db, {
      workspace,
      options: { deleteBranch: true, deleteConversations: false },
      createdAt: 1,
    });
    const second = tombstoneWorkspaceRow(fixture.db, {
      workspace,
      options: { deleteBranch: false, deleteConversations: true },
      createdAt: 2,
    });

    expect(first).toEqual({ success: true, data: { outcome: 'tombstoned' } });
    expect(second).toEqual({ success: true, data: { outcome: 'duplicate' } });
    expect(createWorkspaceRegistry(fixture.db).getLive('ws-1')?.deletionTombstone).toMatchObject({
      tombstonedAt: 1,
      options: { deleteBranch: true, deleteConversations: false },
    });
  });

  it('short-circuits on a failed precondition without writing anything', () => {
    const workspace = seedWorktree('ws-1', '/repo/.worktrees/one');

    const result = tombstoneWorkspaceRow(fixture.db, {
      workspace,
      options: { deleteBranch: false, deleteConversations: false },
      createdAt: 1,
      precondition: () => ({ type: 'workspace-in-use', message: 'still referenced' }),
    });

    expect(result).toEqual({
      success: false,
      error: { type: 'workspace-in-use', message: 'still referenced' },
    });
    expect(createWorkspaceRegistry(fixture.db).getLive('ws-1')?.deletionTombstone).toBeNull();
  });

  describe('creation admission', () => {
    it('refuses a workspace target carrying a pending tombstone', () => {
      const workspace = seedWorktree('ws-1', '/repo/.worktrees/one');
      tombstoneWorkspaceRow(fixture.db, {
        workspace,
        options: { deleteBranch: false, deleteConversations: false },
        createdAt: 1,
      });

      const conflict = findWorkspaceTombstoneConflict(fixture.db, {
        kind: 'workspace',
        workspaceId: 'ws-1',
      });

      expect(conflict).toMatchObject({
        type: 'workspace-tombstone-pending',
        workspaceId: 'ws-1',
      });
      expect(
        findWorkspaceTombstoneConflict(fixture.db, { kind: 'workspace', workspaceId: 'ws-2' })
      ).toBeUndefined();
    });

    it('refuses placement on a tombstone-pending branch or path, same host only', () => {
      const workspace = seedWorktree('ws-1', '/repo/.worktrees/one');
      tombstoneWorkspaceRow(fixture.db, {
        workspace,
        options: { deleteBranch: true, deleteConversations: false },
        createdAt: 1,
      });

      expect(
        findWorkspaceTombstoneConflict(fixture.db, {
          kind: 'placement',
          location: 'local',
          sshConnectionId: null,
          branch: 'branch-ws-1',
        })
      ).toMatchObject({ type: 'workspace-tombstone-pending', workspaceId: 'ws-1' });
      expect(
        findWorkspaceTombstoneConflict(fixture.db, {
          kind: 'placement',
          location: 'local',
          sshConnectionId: null,
          path: '/repo/.worktrees/one',
        })
      ).toMatchObject({ type: 'workspace-tombstone-pending', workspaceId: 'ws-1' });
      expect(
        findWorkspaceTombstoneConflict(fixture.db, {
          kind: 'placement',
          location: 'local',
          sshConnectionId: null,
          branch: 'branch-other',
          path: '/repo/.worktrees/other',
        })
      ).toBeUndefined();
      // A different host is a different registry — no cross-host refusals.
      expect(
        findWorkspaceTombstoneConflict(fixture.db, {
          kind: 'placement',
          location: 'remote',
          sshConnectionId: 'ssh-1',
          branch: 'branch-ws-1',
        })
      ).toBeUndefined();
    });

    it('keeps a tombstone-pending path out of placement: the row stays live and holds it', () => {
      const workspace = seedWorktree('ws-1', '/repo/.worktrees/one');
      tombstoneWorkspaceRow(fixture.db, {
        workspace,
        options: { deleteBranch: false, deleteConversations: false },
        createdAt: 1,
      });

      // The path allocator skips any live row's path; a tombstoned row is live, so
      // placement can never pick /repo/.worktrees/one while the deletion is pending.
      expect(
        createWorkspaceRegistry(fixture.db).findLiveByPath('local', null, '/repo/.worktrees/one')
          ?.id
      ).toBe('ws-1');
    });
  });

  describe('identity-keyed removal (regression)', () => {
    it('never lets an old tombstone reach a new record at the old path', () => {
      const registry = createWorkspaceRegistry(fixture.db);
      const workspace = seedWorktree('ws-old', '/repo/.worktrees/reused');
      tombstoneWorkspaceRow(fixture.db, {
        workspace,
        options: { deleteBranch: true, deleteConversations: false },
        createdAt: 1,
      });
      // The user untracks the pending row (Untrack-anyway) and a new record is born at
      // the same path under a fresh UUID — the delete-racing-create shape.
      registry.untrack(['ws-old'], '2026-01-01T00:00:00.000Z');
      const fresh = seedWorktree('ws-new', '/repo/.worktrees/reused');

      // The tombstone froze the old record's UUID, not the path: the new row carries no
      // tombstone, and the old mark stays pinned to the untracked row it targeted. Any
      // executor is id-keyed by construction (verbs no-op on absent ids).
      expect(fresh.deletionTombstone).toBeNull();
      expect(registry.getLive('ws-new')?.deletionTombstone).toBeNull();
      const old = fixture.db
        .select()
        .from(workspaces)
        .all()
        .find((row) => row.id === 'ws-old');
      expect(old?.deletionTombstone).toMatchObject({ targetRecordId: 'ws-old' });
      expect(old?.untrackedAt).not.toBeNull();

      // Admission no longer refuses the path or branch — the pending mark left with the
      // row it belonged to.
      expect(
        findWorkspaceTombstoneConflict(fixture.db, {
          kind: 'placement',
          location: 'local',
          sshConnectionId: null,
          path: '/repo/.worktrees/reused',
          branch: 'branch-ws-old',
        })
      ).toBeUndefined();
      expect(
        findWorkspaceTombstoneConflict(fixture.db, { kind: 'workspace', workspaceId: 'ws-new' })
      ).toBeUndefined();
    });

    it('refuses to tombstone rows that are no longer live', () => {
      const registry = createWorkspaceRegistry(fixture.db);
      const workspace = seedWorktree('ws-old', '/repo/.worktrees/reused');
      registry.untrack(['ws-old'], '2026-01-01T00:00:00.000Z');

      const result = tombstoneWorkspaceRow(fixture.db, {
        workspace,
        options: { deleteBranch: false, deleteConversations: false },
        createdAt: 2,
      });

      // Zero rows updated: the guard treats a dead row like a duplicate — no new mark.
      expect(result).toEqual({ success: true, data: { outcome: 'duplicate' } });
      const old = fixture.db
        .select()
        .from(workspaces)
        .all()
        .find((row) => row.id === 'ws-old');
      expect(old?.deletionTombstone).toBeNull();
    });
  });
});

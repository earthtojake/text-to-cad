import type { HostRef } from '@emdash/core/primitives/host/api';
import { and, isNotNull } from 'drizzle-orm';
import {
  tombstoneWorkspaceConversationDeletions,
  type WorkspaceRemovalBroker,
} from '@core/features/workspaces/api/node/operations/workspace-removal';
import {
  createWorkspaceRegistry,
  liveWorkspaces,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import { tombstoneAttemptEpoch } from '@core/primitives/reconcile/api/tombstone-attempts';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { hostIdentityFilter } from '@core/services/reconcile-sweep/node/host-identity-filter';
import type {
  ReconcileSweepKind,
  ReconcileTombstone,
  RemovalFailure,
} from '@core/services/reconcile-sweep/node/reconcile-sweep-service';

/**
 * The workspaces registration for the entity-generic reconcile sweep (ADR 0006):
 * pending tombstones are live mirror rows carrying a `deletionTombstone`, removal is
 * the registry's idempotent `deleteWorktree`/`deleteWorkspace` verb called with the
 * tombstone's frozen options and target record UUID, and gone-confirmation is the
 * sync path having untracked the row (the snapshot application purges tombstoned rows
 * once a delivery no longer carries the record). Failure classes are host-decided and
 * arrive on the RPC error detail; a terminal one is recorded durably on the tombstone
 * row itself, epoch-tagged, so the stop survives restarts and registry syncs.
 */
export function createWorkspaceDeletionSweepKind(options: {
  db: AppDb;
  runtimes: WorkspaceRemovalBroker;
}): ReconcileSweepKind {
  const { db, runtimes } = options;
  return {
    kind: 'workspaces',

    async readTombstones(host: HostRef): Promise<readonly ReconcileTombstone[]> {
      const rows = db
        .select()
        .from(workspaces)
        .where(
          and(
            liveWorkspaces(),
            hostIdentityFilter(host, workspaces),
            isNotNull(workspaces.deletionTombstone)
          )
        )
        .all();
      return rows.flatMap((row) => {
        const tombstone = row.deletionTombstone;
        if (tombstone === null) return [];
        return [
          {
            id: row.id,
            attemptEpoch: tombstoneAttemptEpoch(tombstone),
            terminalStopEpoch: tombstone.terminalStop?.epoch ?? null,
          },
        ];
      });
    },

    async executeRemoval(host, id) {
      const row = createWorkspaceRegistry(db).getLive(id);
      const tombstone = row?.deletionTombstone ?? null;
      // The row vanished under the sweep (forget-host, sync purge): nothing to issue,
      // nothing to assert.
      if (!row || tombstone === null) return 'ok';
      const client = await runtimes.client(host);
      if (!client.success) return 'unreachable';
      const verbs = client.data.workspaceRegistry;
      // Identity-keyed removal: the verb targets the frozen record UUID, so a new
      // record at the old path is never touched and an absent id is a no-op success.
      const removed =
        row.kind === 'worktree'
          ? await verbs.deleteWorktree({
              workspaceId: tombstone.targetRecordId,
              deleteBranch: tombstone.options.deleteBranch,
            })
          : await verbs.deleteWorkspace({ workspaceId: tombstone.targetRecordId });
      if (!removed.success) {
        if (removed.error.type === 'host-unreachable') return 'unreachable';
        return { failed: deleteVerbFailure(removed.error) };
      }
      // The frozen opt-in cascade, compiled at sweep time (spec §7.1) — same shape as
      // the reachable-host delete path: conversation deletion tombstones, converged by
      // the conversations kind on sweeps of this host (registered after this kind, so
      // the same pass usually picks them up — a heuristic; the backstop is the
      // guarantee). The workspace tombstone itself still waits for mirror
      // confirmation; only the RPC's positive success runs the cascade.
      if (tombstone.options.deleteConversations) {
        tombstoneWorkspaceConversationDeletions(db, {
          workspacePath: row.path ?? undefined,
          host,
          createdAt: Date.now(),
        });
      }
      return 'ok';
    },

    async confirmGone(_host, id) {
      // The sync snapshot application untracks tombstoned rows once a delivery
      // confirms the record absent — a row no longer live is a purged tombstone.
      return createWorkspaceRegistry(db).getLive(id) === undefined;
    },

    async recordTerminalStop(_host, id, stop) {
      // Epoch-guarded durable write on the tombstone row (ADR 0006): a Retry that
      // already advanced the epoch discards the stale stop inside the registry.
      const written = createWorkspaceRegistry(db).recordTombstoneTerminalStop(id, stop);
      if (written > 0) appDbPokes.workspaces.poke({ workspaceId: id });
    },
  };
}

/**
 * Maps the delete verb's RPC error detail to the sweep's loop-control failure. The
 * host stays the classifier: `remove-failed` carries the host-decided stage/class
 * (the same facts as the record's `lastRemovalAttempt`); `not-a-worktree` is a
 * structural refusal an identical retry cannot fix — terminal.
 */
function deleteVerbFailure(error: { type: string; message?: string }): RemovalFailure {
  // Structural read: the broker slice types the error minimally, but the registry
  // contract's remove-failed errors carry the host-decided stage and class.
  const detail = error as { type: string; message?: string; stage?: unknown; class?: unknown };
  if (detail.type === 'not-a-worktree') {
    return {
      class: 'terminal',
      stage: 'remove',
      message: 'The record is not a worktree.',
    };
  }
  return {
    class: detail.class === 'terminal' ? 'terminal' : 'transient',
    stage: typeof detail.stage === 'string' ? detail.stage : 'remove',
    message:
      typeof detail.message === 'string'
        ? detail.message
        : `Workspace deletion failed (${detail.type}).`,
  };
}

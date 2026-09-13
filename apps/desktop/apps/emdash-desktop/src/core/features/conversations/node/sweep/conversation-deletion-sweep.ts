import type { HostRef } from '@emdash/core/primitives/host/api';
import { and, isNotNull } from 'drizzle-orm';
import {
  executeConversationRemoval,
  type ConversationRemovalBroker,
} from '@core/features/conversations/api/node/operations/conversation-removal';
import {
  conversationRegistryTable as conversations,
  createConversationRegistry,
  liveConversations,
} from '@core/features/conversations/api/node/registry';
import { tombstoneAttemptEpoch } from '@core/primitives/reconcile/api/tombstone-attempts';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { hostIdentityFilter } from '@core/services/reconcile-sweep/node/host-identity-filter';
import type {
  ReconcileSweepKind,
  ReconcileTombstone,
} from '@core/services/reconcile-sweep/node/reconcile-sweep-service';

/**
 * The conversations registration for the entity-generic reconcile sweep (ADR 0006):
 * pending tombstones are live mirror rows carrying a `deletionTombstone`, removal is
 * the idempotent conversation removal verb — kill any live session, then the id-keyed
 * host index delete — and gone-confirmation is the conversation sync having untracked
 * the row (the snapshot application purges tombstoned rows once a delivery no longer
 * carries the record). Dangling-tolerant by construction: the verb needs no workspace
 * row, so conversations of an already-removed workspace converge the same way.
 * Failure classes come from the RPC error detail (host-decided); a terminal one is
 * recorded durably on the tombstone row, epoch-tagged, so a persistently failing
 * removal stops retrying and surfaces why instead of spinning silently forever.
 */
export function createConversationDeletionSweepKind(options: {
  db: AppDb;
  runtimes: ConversationRemovalBroker;
}): ReconcileSweepKind {
  const { db, runtimes } = options;
  return {
    kind: 'conversations',

    async readTombstones(host: HostRef): Promise<readonly ReconcileTombstone[]> {
      const rows = db
        .select()
        .from(conversations)
        .where(
          and(
            liveConversations(),
            hostIdentityFilter(host, conversations),
            isNotNull(conversations.deletionTombstone)
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
      const row = createConversationRegistry(db).getLive(id);
      const tombstone = row?.deletionTombstone ?? null;
      // The row vanished under the sweep (forget-host, sync purge): nothing to issue,
      // nothing to assert.
      if (!row || tombstone === null) return 'ok';
      // Identity-keyed removal: the verb targets the frozen record UUID, so an absent
      // id is a no-op success and an already-gone conversation converges silently.
      return executeConversationRemoval(runtimes, host, tombstone.targetRecordId);
    },

    async confirmGone(_host, id) {
      // The sync snapshot application untracks tombstoned rows once a delivery
      // confirms the record absent — a row no longer live is a purged tombstone.
      return createConversationRegistry(db).getLive(id) === undefined;
    },

    async recordTerminalStop(_host, id, stop) {
      // Epoch-guarded durable write on the tombstone row (ADR 0006): a Retry that
      // already advanced the epoch discards the stale stop inside the registry.
      const written = createConversationRegistry(db).recordTombstoneTerminalStop(id, stop);
      if (written > 0) appDbPokes.conversations.poke({});
    },
  };
}

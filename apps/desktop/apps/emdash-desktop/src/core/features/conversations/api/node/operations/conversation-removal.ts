import type { HostRef } from '@emdash/core/primitives/host/api';
import type { Result } from '@emdash/shared';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import type { ConversationDeletionTombstone } from '@core/primitives/conversations/api';
import type { AppDb, DrizzleTx } from '@core/services/app-db/node/db';

/**
 * Conversation removal for the reconcile sweep era (ADR 0006, operation-log
 * retirement spec §2). Deletion intent is a durable tombstone on the mirror row —
 * nothing queues anywhere — and execution is one idempotent removal verb: killing
 * any live session is part of the verb (conversation spec §4.3), followed by the
 * id-keyed host index delete, which no-ops on absent records. The verb survives
 * unreachability through the tombstone + sweep, not an outbox entry.
 */

export type ConversationRemovalFailure = {
  /** Host-decided (ADR 0006): read from the RPC error detail; the client never classifies. */
  class: 'transient' | 'terminal';
  stage: string;
  message: string;
};

export type ConversationRemovalOutcome =
  /** The RPC finished; it asserts nothing — the purge waits on mirror confirmation. */
  | 'ok'
  /** The host could not be reached: not an attempt; the reconnect sweep retries. */
  | 'unreachable'
  /** The verb failed on a reachable host: the sweep schedules per-item backoff; a terminal class stops it. */
  | { failed: ConversationRemovalFailure };

/**
 * Structural slice of the runtime broker: the session-kill and index-delete verbs
 * this module calls. The production `RuntimeBroker` satisfies it; tests fake it.
 */
export type ConversationRemovalBroker = {
  client(host: HostRef): Promise<
    Result<
      {
        acp: {
          kill(input: { conversationId: string }): Promise<unknown>;
          deleteAttachments(input: { conversationId: string }): Promise<unknown>;
        };
        tuiAgents: { delete(input: { conversationId: string }): Promise<unknown> };
        conversations: {
          delete(input: {
            conversationId: string;
          }): Promise<Result<void, { type: string; message?: string }>>;
        };
      },
      { type: string; message: string }
    >
  >;
};

export type ConversationTombstoneOutcome = 'tombstoned' | 'duplicate';

/**
 * Marks one live conversation mirror row with a durable deletion tombstone, inside the
 * caller's transaction — the shared seam for every conversation deletion cascade
 * (task/project/automation delete flows, the workspace `deleteConversations` cascade,
 * and the offline branch of user-initiated deletion). The payload — the target record's
 * UUID and the write stamp — is compiled before the write, and the write is a single
 * guarded UPDATE: zero rows updated means the row is already tombstoned or no longer
 * live, which suppresses duplicates without overwriting the first write.
 */
export function tombstoneConversationForRemoval(
  tx: DrizzleTx,
  input: { conversationId: string; createdAt: number }
): { outcome: ConversationTombstoneOutcome } {
  const tombstone: ConversationDeletionTombstone = {
    version: '1',
    targetRecordId: input.conversationId,
    tombstonedAt: input.createdAt,
  };
  // AppDb and its transaction expose the same query-builder surface (see the registry's
  // `source`); constructing the sole-writer over the tx keeps the write in the caller's
  // transaction without threading a second handle.
  const registry = createConversationRegistry(tx as unknown as AppDb, {
    now: () => new Date(input.createdAt).toISOString(),
  });
  const changes = registry.tombstone(input.conversationId, tombstone);
  return { outcome: changes === 0 ? 'duplicate' : 'tombstoned' };
}

/**
 * The idempotent conversation removal verb, ported from the retired
 * `host.deleteConversation` operation handler: kill any live session — never a
 * separate desktop-ordered step — then delete the host conversation index row.
 * Safe to re-issue (the index delete no-ops on absent ids) and dangling-tolerant:
 * it needs no workspace row, so a conversation whose workspace is already gone
 * removes the same way. The return is loop control for the sweep, never truth —
 * the tombstone purges only on mirror-confirmed gone.
 */
export async function executeConversationRemoval(
  runtimes: ConversationRemovalBroker,
  host: HostRef,
  conversationId: string
): Promise<ConversationRemovalOutcome> {
  const client = await runtimes.client(host);
  if (!client.success) return 'unreachable';

  // Best effort: a conversation has at most one live session, of unknown type from
  // here, so both kills run; absent sessions are no-ops and kill failures must not
  // block record deletion (the host reaps orphaned sessions).
  try {
    await client.data.acp.kill({ conversationId });
  } catch {
    // Swallowed by design; see comment above.
  }
  try {
    await client.data.tuiAgents.delete({ conversationId });
  } catch {
    // Swallowed by design; see comment above.
  }

  const deleted = await client.data.conversations.delete({ conversationId });
  if (!deleted.success) {
    if (deleted.error.type === 'host-unreachable') return 'unreachable';
    return { failed: deleteVerbFailure(deleted.error) };
  }

  // Attachment cleanup rides the removal verb (spec §3.6, §4.2): once the record is gone
  // the acp runtime purges the conversation's attachment directory. Best effort — a failed
  // purge leaves an inert orphaned directory, never a blocked deletion.
  try {
    await client.data.acp.deleteAttachments({ conversationId });
  } catch {
    // Swallowed by design; see comment above.
  }
  return 'ok';
}

/**
 * Maps the delete verb's RPC error detail to the sweep's loop-control failure. The
 * host stays the classifier: the index delete declares no domain errors today, so
 * failures are transport-shaped and default to transient — but a host-written
 * `class: 'terminal'` on the error detail stops the item durably, the same contract
 * the workspace verbs carry.
 */
function deleteVerbFailure(error: { type: string; message?: string }): ConversationRemovalFailure {
  // Structural read: the broker slice types the error minimally; hosts that classify
  // put stage/class on the error detail (ADR 0006).
  const detail = error as { type: string; message?: string; stage?: unknown; class?: unknown };
  return {
    class: detail.class === 'terminal' ? 'terminal' : 'transient',
    stage: typeof detail.stage === 'string' ? detail.stage : 'remove',
    message:
      typeof detail.message === 'string'
        ? detail.message
        : `Conversation deletion failed (${detail.type}).`,
  };
}

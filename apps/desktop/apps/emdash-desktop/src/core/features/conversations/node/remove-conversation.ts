import { hostRefFromParts } from '@emdash/core/primitives/host/api';
import {
  executeConversationRemoval,
  tombstoneConversationForRemoval,
  type ConversationRemovalBroker,
} from '@core/features/conversations/api/node/operations/conversation-removal';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import type { AppDb } from '@core/services/app-db/node/db';
import type { ConversationRow } from '@core/services/app-db/node/schema';
import { reconcileSweepTriggers } from '@core/services/reconcile-sweep/node/reconcile-sweep-triggers';

/**
 * User-initiated conversation deletion (ADR 0006): against a reachable host the
 * removal verb runs in the foreground — kill any live session, delete the host index
 * row — and the mirror row untracks immediately (today's UX). Against an unreachable
 * host the deletion no longer queues anywhere: the mirror row is marked with a durable
 * deletion tombstone and stays visible as the pending state; the reconcile sweep
 * executes the same verb once the host is reachable.
 */
export async function removeConversationOrTombstone(
  db: AppDb,
  runtimes: ConversationRemovalBroker,
  row: Pick<ConversationRow, 'id' | 'location' | 'sshConnectionId'>
): Promise<'removed' | 'tombstoned'> {
  const host = hostRefFromParts(row.location, row.sshConnectionId);
  const outcome = await executeConversationRemoval(runtimes, host, row.id);
  if (typeof outcome !== 'string') {
    throw new Error(
      `Failed to delete conversation ${row.id} on its host: ${outcome.failed.message}`
    );
  }
  const createdAt = Date.now();
  if (outcome === 'unreachable') {
    db.transaction((tx) =>
      tombstoneConversationForRemoval(tx, { conversationId: row.id, createdAt })
    );
    // Tombstoned-while-reachable trigger (ADR 0006): reachability may have flapped
    // mid-call, so poke the reconcile sweep — a genuinely unreachable host makes the
    // sweep a no-op attempt with no backoff.
    reconcileSweepTriggers.poke(host);
    return 'tombstoned';
  }
  // The RPC's positive success keeps the foreground UX: the row leaves live reads now;
  // the next sync delivery would confirm the same.
  createConversationRegistry(db).untrack([row.id], new Date(createdAt).toISOString());
  return 'removed';
}

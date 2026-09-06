import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import { z } from 'zod';
import { tombstoneTerminalStopSchema } from '@core/primitives/reconcile/api/tombstone-attempts';

// Durable deletion intent on the conversations mirror (ADR 0006, operation-log
// retirement spec §2): a conversation deleted against an unreachable host marks its
// mirror row instead of queueing an operation. The row stays live as the visible
// pending state; the reconcile sweep executes the idempotent removal verb — killing
// any live session is part of the verb — and the sync path purges the tombstone once
// the host index no longer carries the record. Nothing rides an operation log.

const deletionTombstoneV1 = z.object({
  version: z.literal('1'),
  /**
   * The target host record's UUID, frozen at tombstone time (identity-keyed removal):
   * the index delete is id-keyed and no-ops on absent ids, so a record re-created
   * under a new id is never touched by an old tombstone.
   */
  targetRecordId: z.string(),
  /** Epoch-ms write stamp; display only, never an expiry (ADR 0006 keeps no timer). */
  tombstonedAt: z.number(),
  /**
   * Durable attempt epoch: incremented by the Retry affordance; absent reads as 0.
   * See `@core/primitives/reconcile/api/tombstone-attempts` for the stop semantics.
   */
  attemptEpoch: z.number().int().optional(),
  /** Durable desktop-recorded terminal stop, inert once Retry advances the epoch. */
  terminalStop: tombstoneTerminalStopSchema.nullable().optional(),
});

export const conversationDeletionTombstone = defineVersionedSchema()
  .initial('1', deletionTombstoneV1)
  .build();
export type ConversationDeletionTombstone = typeof conversationDeletionTombstone.Type;

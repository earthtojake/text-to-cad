import { defineContract, fallible, liveModel, liveState } from '@emdash/wire/rpc';
import { z } from 'zod';
import {
  conversationMutationErrorSchema,
  createConversationErrorSchema,
  deleteConversationErrorSchema,
} from './errors';
import {
  conversationRecordSchema,
  conversationRecordsSchema,
  createConversationInputSchema,
  deleteConversationInputSchema,
  renameConversationInputSchema,
  reportProviderSessionIdInputSchema,
  reportSessionActivityInputSchema,
  reportSessionEndedInputSchema,
  reportSessionStartedInputSchema,
  updateConversationConfigInputSchema,
} from './schemas';

const conversationReportsSubContract = defineContract({
  sessionStarted: fallible({
    input: reportSessionStartedInputSchema,
    data: z.void(),
    error: conversationMutationErrorSchema,
  }),
  providerSessionId: fallible({
    input: reportProviderSessionIdInputSchema,
    data: z.void(),
    error: conversationMutationErrorSchema,
  }),
  sessionActivity: fallible({
    input: reportSessionActivityInputSchema,
    data: z.void(),
    error: conversationMutationErrorSchema,
  }),
  sessionEnded: fallible({
    input: reportSessionEndedInputSchema,
    data: z.void(),
    error: conversationMutationErrorSchema,
  }),
});

/**
 * The host conversation index (spec §4). The `records` live model is the sole read path —
 * durable-backed, so subscribing yields every durable record whether or not a session is
 * live; the initial state on subscribe is the authoritative snapshot. Mutations are the
 * client-facing feeder of the sole-writer index component (conv.sole-writer).
 */
export const conversationsContract = defineContract({
  records: liveModel({
    key: z.void().optional(),
    states: {
      list: liveState({ data: conversationRecordsSchema }),
    },
  }),
  create: fallible({
    input: createConversationInputSchema,
    data: conversationRecordSchema,
    error: createConversationErrorSchema,
  }),
  rename: fallible({
    input: renameConversationInputSchema,
    data: conversationRecordSchema,
    error: conversationMutationErrorSchema,
  }),
  updateConfig: fallible({
    input: updateConversationConfigInputSchema,
    data: conversationRecordSchema,
    error: conversationMutationErrorSchema,
  }),
  delete: fallible({
    input: deleteConversationInputSchema,
    data: z.void(),
    error: deleteConversationErrorSchema,
  }),

  /**
   * Lifecycle-report feeders (spec §3.7, §4.2) — feeder verbs for session runtimes and
   * trusted maintenance flows (e.g. the desktop conversation backfill): one-way, idempotent
   * liveness-metadata updates into the sole-writer index. The index stamps observation times
   * with its own clock. Reports never create records: a report against a deleted record is a
   * not-found error the feeder logs.
   *
   * Resume-outcome mapping at the report boundary: the tui runtime's per-call resume result
   * maps to the durable index enum as `resumed` → `loaded`, `fresh-fallback` →
   * `replaced-by-new`; an `attached` result means no session was spawned, so no report is
   * sent and the index is unchanged.
   */
  reports: conversationReportsSubContract,
});

export type ConversationsContract = typeof conversationsContract;

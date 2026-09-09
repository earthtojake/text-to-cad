import { defineContract, fallible } from '@emdash/wire/rpc';
import { z } from 'zod';
import {
  conversationReportErrorSchema,
  reportProviderSessionIdInputSchema,
  reportSessionActivityInputSchema,
  reportSessionEndedInputSchema,
  reportSessionStartedInputSchema,
} from './schemas';

/**
 * The lifecycle-report subset of the conversations index contract (spec §3.7, §4.2): the
 * surface session runtimes depend on to report facts into the sole-writer index. The four
 * feeder verbs live under the `reports` sub-contract — feeder verbs for session runtimes and
 * trusted maintenance flows; one-way, idempotent liveness-metadata updates. Structurally a
 * subset of `conversationsContract`, so the full conversations client satisfies it — the
 * session-start-contract pattern.
 *
 * Resume-outcome mapping at the report boundary: the tui runtime's per-call resume result
 * maps to the durable index enum as `resumed` → `loaded`, `fresh-fallback` →
 * `replaced-by-new`; an `attached` result means no session was spawned, so no report is
 * sent and the index is unchanged.
 */
export const conversationReportsContract = defineContract({
  reports: defineContract({
    sessionStarted: fallible({
      input: reportSessionStartedInputSchema,
      data: z.void(),
      error: conversationReportErrorSchema,
    }),
    providerSessionId: fallible({
      input: reportProviderSessionIdInputSchema,
      data: z.void(),
      error: conversationReportErrorSchema,
    }),
    sessionActivity: fallible({
      input: reportSessionActivityInputSchema,
      data: z.void(),
      error: conversationReportErrorSchema,
    }),
    sessionEnded: fallible({
      input: reportSessionEndedInputSchema,
      data: z.void(),
      error: conversationReportErrorSchema,
    }),
  }),
});

export type ConversationReportsContract = typeof conversationReportsContract;

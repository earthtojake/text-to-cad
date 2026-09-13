import { z } from 'zod';

// Service-local copies of the lifecycle-report shapes from the conversations runtime
// contract (spec §3.3). Core module boundaries forbid services -> runtimes imports, so —
// like services/session-start — this subset duplicates the schemas; structural typing at
// the gateway wiring keeps them compatible with `conversationsContract`.

/**
 * Lifecycle report from a session runtime: session started. `resumeOutcome` is null for a
 * fresh start (no resume was attempted); 'loaded' when the provider replayed the prior
 * session; 'replaced-by-new' when resume fell back to a new session (spec §7.4).
 */
export const reportSessionStartedInputSchema = z.object({
  conversationId: z.string().min(1),
  providerSessionId: z.string().nullable(),
  resumeOutcome: z.enum(['loaded', 'replaced-by-new']).nullable(),
});
export type ReportSessionStartedInput = z.infer<typeof reportSessionStartedInputSchema>;

/** Mid-session provider-id rebind or late hook-driven capture. */
export const reportProviderSessionIdInputSchema = z.object({
  conversationId: z.string().min(1),
  providerSessionId: z.string().min(1),
});
export type ReportProviderSessionIdInput = z.infer<typeof reportProviderSessionIdInputSchema>;

export const reportSessionActivityInputSchema = z.object({
  conversationId: z.string().min(1),
});
export type ReportSessionActivityInput = z.infer<typeof reportSessionActivityInputSchema>;

export const reportSessionEndedInputSchema = z.object({
  conversationId: z.string().min(1),
});
export type ReportSessionEndedInput = z.infer<typeof reportSessionEndedInputSchema>;

export const conversationReportErrorSchema = z.object({
  type: z.literal('conversation-not-found'),
  conversationId: z.string(),
  message: z.string(),
});
export type ConversationReportError = z.infer<typeof conversationReportErrorSchema>;

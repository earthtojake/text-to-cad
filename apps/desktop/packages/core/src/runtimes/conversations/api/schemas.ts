import { z } from 'zod';

export const conversationTypeSchema = z.enum(['pty', 'acp']);
export type ConversationType = z.infer<typeof conversationTypeSchema>;

/**
 * How the provider session id is managed for this conversation (spec §3.1). Immutable at
 * creation. Any stored provider session id is a last-observed resume handle, never the
 * record's identity.
 */
export const conversationIdRegimeSchema = z.enum(['emdash-chosen', 'provider-minted', 'none']);
export type ConversationIdRegime = z.infer<typeof conversationIdRegimeSchema>;

/**
 * Outcome of the last resume attempt (spec §7.4) — the honest "history could not be
 * restored" signal, recorded at the moment a resume happens rather than by scanning
 * provider storage.
 */
export const conversationResumeOutcomeSchema = z.enum([
  'loaded',
  'replaced-by-new',
  'never-resumed',
]);
export type ConversationResumeOutcome = z.infer<typeof conversationResumeOutcomeSchema>;

/**
 * Session start/resume payload, including any queued prompt. Opaque to the index: the host
 * stores and serves it without interpreting it; its inner shape is client business.
 */
export const conversationConfigSchema = z.record(z.string(), z.unknown());
export type ConversationConfig = z.infer<typeof conversationConfigSchema>;

/** One host conversation record (spec §3.2). */
export const conversationRecordSchema = z.object({
  /** Emdash-minted UUID; primary key; client-supplied on create; never changes, never reused. */
  conversationId: z.string().min(1),
  provider: z.string().min(1),
  type: conversationTypeSchema,
  /** Frozen at creation; part of the resume key. Distinct from workspacePath even when equal. */
  cwd: z.string().min(1),
  /** Association value, not a foreign key; may dangle. No host-id prefix on the host's own records. */
  workspacePath: z.string().min(1),
  idRegime: conversationIdRegimeSchema,
  createdAt: z.number(),
  title: z.string(),
  config: conversationConfigSchema,
  /** Last-observed resume handle; null for never-captured and stateless providers. */
  providerSessionId: z.string().nullable(),
  /** When the provider session id was last observed by a session runtime. */
  providerSessionIdObservedAt: z.number().nullable(),
  lastSessionActivityAt: z.number().nullable(),
  lastSpawnedAt: z.number().nullable(),
  lastResumeOutcome: conversationResumeOutcomeSchema,
  updatedAt: z.number(),
});
export type ConversationRecord = z.infer<typeof conversationRecordSchema>;

export const conversationRecordsSchema = z.record(z.string(), conversationRecordSchema);
export type ConversationRecords = z.infer<typeof conversationRecordsSchema>;

export const createConversationInputSchema = z.object({
  conversationId: z.string().min(1),
  provider: z.string().min(1),
  type: conversationTypeSchema,
  cwd: z.string().min(1),
  workspacePath: z.string().min(1),
  idRegime: conversationIdRegimeSchema,
  createdAt: z.number(),
  title: z.string(),
  config: conversationConfigSchema,
});
export type CreateConversationInput = z.infer<typeof createConversationInputSchema>;

export const renameConversationInputSchema = z.object({
  conversationId: z.string().min(1),
  title: z.string(),
});
export type RenameConversationInput = z.infer<typeof renameConversationInputSchema>;

export const updateConversationConfigInputSchema = z.object({
  conversationId: z.string().min(1),
  config: conversationConfigSchema,
});
export type UpdateConversationConfigInput = z.infer<typeof updateConversationConfigInputSchema>;

export const deleteConversationInputSchema = z.object({
  conversationId: z.string().min(1),
});
export type DeleteConversationInput = z.infer<typeof deleteConversationInputSchema>;

/**
 * Lifecycle report from a session runtime (spec §3.3): session started. `resumeOutcome` is
 * null for a fresh start (no resume was attempted); 'loaded' when the provider replayed the
 * prior session; 'replaced-by-new' when resume fell back to a new session (spec §7.4).
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

import { z } from 'zod';

// Service-local copies of the create surface of the conversations runtime contract
// (spec §4.1). Core module boundaries forbid services -> runtimes imports, so — like
// services/conversation-reports — this subset duplicates the schemas; structural typing
// at the gateway wiring keeps them compatible with `conversationsContract`.

export const conversationIndexTypeSchema = z.enum(['pty', 'acp']);

export const conversationIndexIdRegimeSchema = z.enum(['emdash-chosen', 'provider-minted', 'none']);

export const conversationIndexConfigSchema = z.record(z.string(), z.unknown());

/** One host conversation record (spec §3.2); mirror of the runtime's record schema. */
export const conversationIndexRecordSchema = z.object({
  conversationId: z.string().min(1),
  provider: z.string().min(1),
  type: conversationIndexTypeSchema,
  cwd: z.string().min(1),
  workspacePath: z.string().min(1),
  idRegime: conversationIndexIdRegimeSchema,
  createdAt: z.number(),
  title: z.string(),
  config: conversationIndexConfigSchema,
  providerSessionId: z.string().nullable(),
  providerSessionIdObservedAt: z.number().nullable(),
  lastSessionActivityAt: z.number().nullable(),
  lastSpawnedAt: z.number().nullable(),
  lastResumeOutcome: z.enum(['loaded', 'replaced-by-new', 'never-resumed']),
  updatedAt: z.number(),
});
export type ConversationIndexRecord = z.infer<typeof conversationIndexRecordSchema>;

export const createConversationIndexRecordInputSchema = z.object({
  conversationId: z.string().min(1),
  provider: z.string().min(1),
  type: conversationIndexTypeSchema,
  cwd: z.string().min(1),
  workspacePath: z.string().min(1),
  idRegime: conversationIndexIdRegimeSchema,
  createdAt: z.number(),
  title: z.string(),
  config: conversationIndexConfigSchema,
});
export type CreateConversationIndexRecordInput = z.infer<
  typeof createConversationIndexRecordInputSchema
>;

export const createConversationIndexRecordErrorSchema = z.object({
  type: z.literal('immutable-field-mismatch'),
  conversationId: z.string(),
  fields: z.array(z.string()),
  message: z.string(),
});
export type CreateConversationIndexRecordError = z.infer<
  typeof createConversationIndexRecordErrorSchema
>;

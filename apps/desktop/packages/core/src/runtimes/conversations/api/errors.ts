import { z } from 'zod';

/**
 * Replaying `create` with an existing id is a no-op success only when the immutable field
 * set is identical; any divergence is a hard error — ids are never reused (conv.identity).
 */
export const conversationImmutableFieldMismatchErrorSchema = z.object({
  type: z.literal('immutable-field-mismatch'),
  conversationId: z.string(),
  fields: z.array(z.string()),
  message: z.string(),
});
export type ConversationImmutableFieldMismatchError = z.infer<
  typeof conversationImmutableFieldMismatchErrorSchema
>;

export const conversationNotFoundErrorSchema = z.object({
  type: z.literal('conversation-not-found'),
  conversationId: z.string(),
  message: z.string(),
});
export type ConversationNotFoundError = z.infer<typeof conversationNotFoundErrorSchema>;

export const createConversationErrorSchema = conversationImmutableFieldMismatchErrorSchema;
export type CreateConversationError = z.infer<typeof createConversationErrorSchema>;

export const conversationMutationErrorSchema = conversationNotFoundErrorSchema;
export type ConversationMutationError = z.infer<typeof conversationMutationErrorSchema>;

/** Delete is idempotent: deleting an absent record succeeds (Outbox retries replay it). */
export const deleteConversationErrorSchema = z.never();
export type DeleteConversationError = z.infer<typeof deleteConversationErrorSchema>;

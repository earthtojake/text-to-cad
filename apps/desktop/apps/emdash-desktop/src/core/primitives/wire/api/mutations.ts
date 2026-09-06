import z from 'zod';

/**
 * Shared wire shapes for lifecycle mutations (delete/archive/reprovision): success
 * carries no payload — resulting state arrives through live models — and failures
 * are a typed message.
 */
export const mutationAckSchema = z.object({});

export const mutationErrorSchema = z.object({
  type: z.string(),
  message: z.string(),
});

export type MutationAck = z.infer<typeof mutationAckSchema>;
export type MutationError = z.infer<typeof mutationErrorSchema>;

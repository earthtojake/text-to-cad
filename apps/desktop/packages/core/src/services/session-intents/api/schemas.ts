import type { Serializable } from '@emdash/shared';
import { z } from 'zod';

export const serializableValueSchema: z.ZodType<Serializable> = z.lazy(() =>
  z.union([
    z.string(),
    z.number(),
    z.boolean(),
    z.null(),
    z.array(serializableValueSchema),
    z.record(z.string(), serializableValueSchema),
  ])
);

export const sessionIntentScopeSchema = z.enum(['acp', 'tui-agents']);

export type SessionIntentScope = z.infer<typeof sessionIntentScopeSchema>;

export const sessionIntentStatusSchema = z.enum(['active', 'suspended']);

export type SessionIntentStatus = z.infer<typeof sessionIntentStatusSchema>;

export const sessionIntentSchema = z.object({
  conversationId: z.string().min(1),
  status: sessionIntentStatusSchema,
  suspendedCause: z.string().min(1).optional(),
  payload: serializableValueSchema,
  sessionId: z.string().nullable().optional(),
  updatedAt: z.number().int(),
});

export type SessionIntent = z.infer<typeof sessionIntentSchema>;

export const sessionIntentErrorSchema = z.object({
  type: z.enum(['io', 'decode']),
  message: z.string(),
  key: z.string().optional(),
});

export type SessionIntentError = z.infer<typeof sessionIntentErrorSchema>;

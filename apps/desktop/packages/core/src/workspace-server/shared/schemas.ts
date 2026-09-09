import { resultSchema } from '@emdash/shared';
import { z } from 'zod';

/**
 * Wraps a Result<T,E> on the wire as a discriminated union.
 * Domain outcomes use this helper; transport-level failures use oRPC .errors().
 */
export const result = resultSchema;

export const runtimeUnavailableErrorSchema = z.object({
  type: z.literal('runtime-unavailable'),
  message: z.string(),
});

export type RuntimeUnavailableError = z.infer<typeof runtimeUnavailableErrorSchema>;

import type { SerializedError } from '@emdash/shared';
import { z } from 'zod';
import type { Patch } from '../state/immer-setup';

export type { Patch };

export const liveLogDeltaSchema = z.object({
  chunk: z.string(),
});

export type LiveLogDelta = z.infer<typeof liveLogDeltaSchema>;

export const eventStreamDeltaSchema = z.object({
  event: z.unknown(),
});

export type EventStreamDelta = z.infer<typeof eventStreamDeltaSchema>;

export const serializedErrorSchema = z.object({
  name: z.string(),
  message: z.string(),
  stack: z.string().optional(),
});

export function liveJobStateSchema<
  P extends z.ZodTypeAny,
  R extends z.ZodTypeAny,
  E extends z.ZodTypeAny,
>(progress: P, result: R, error: E) {
  return z.discriminatedUnion('status', [
    z.object({
      status: z.literal('running'),
      startedAt: z.number().int().nonnegative(),
      progress: z.array(progress),
      progressCount: z.number().int().nonnegative(),
    }),
    z.object({
      status: z.literal('succeeded'),
      startedAt: z.number().int().nonnegative(),
      finishedAt: z.number().int().nonnegative(),
      progress: z.array(progress),
      result,
    }),
    z.object({
      status: z.literal('failed'),
      startedAt: z.number().int().nonnegative(),
      finishedAt: z.number().int().nonnegative(),
      progress: z.array(progress),
      error: error.optional(),
      cause: serializedErrorSchema.optional(),
    }),
    z.object({
      status: z.literal('cancelled'),
      startedAt: z.number().int().nonnegative(),
      finishedAt: z.number().int().nonnegative(),
      progress: z.array(progress),
    }),
  ]);
}

export type LiveJobState<P, R, E> =
  | {
      status: 'running';
      startedAt: number;
      progress: P[];
      progressCount: number;
    }
  | {
      status: 'succeeded';
      startedAt: number;
      finishedAt: number;
      progress: P[];
      result: R;
    }
  | {
      status: 'failed';
      startedAt: number;
      finishedAt: number;
      progress: P[];
      error?: E;
      cause?: SerializedError;
    }
  | {
      status: 'cancelled';
      startedAt: number;
      finishedAt: number;
      progress: P[];
    };

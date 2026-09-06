import { z } from 'zod';

export const mementoModelKeySchema = z.object({
  mementoId: z.string().min(1),
  kind: z.string().min(1),
  key: z.string(),
});

export const mementoRowSchema = z.object({
  version: z.string().min(1),
  data: z.string(),
  updatedAt: z.number().int().nonnegative(),
});

export const mementoMutationErrorSchema = z.object({
  code: z.literal('persistence'),
  message: z.string(),
});

export type MementoModelKey = z.infer<typeof mementoModelKeySchema>;
export type MementoRow = z.infer<typeof mementoRowSchema>;
export type MementoMutationError = z.infer<typeof mementoMutationErrorSchema>;

export function mementoKeyId(key: MementoModelKey): string {
  return JSON.stringify([key.mementoId, key.kind, key.key]);
}

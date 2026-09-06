import { z } from 'zod';

export const fsErrorSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('not-found'), path: z.string() }),
  z.object({ type: z.literal('permission-denied'), path: z.string() }),
  z.object({ type: z.literal('already-exists'), path: z.string() }),
  z.object({ type: z.literal('not-a-directory'), path: z.string() }),
  z.object({ type: z.literal('is-a-directory'), path: z.string() }),
  z.object({
    type: z.literal('etag-mismatch'),
    path: z.string(),
    expected: z.string(),
    actual: z.string(),
  }),
  z.object({ type: z.literal('invalid-path'), path: z.string(), message: z.string() }),
  z.object({ type: z.literal('io'), path: z.string(), message: z.string() }),
]);

export type FsError = z.infer<typeof fsErrorSchema>;

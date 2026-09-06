import { defineContract, resourcedStream } from '@emdash/wire/rpc';
import { z } from 'zod';

export const watchKeySchema = z.object({
  root: z.string(),
  ignore: z.array(z.string()),
});

export const watchEventSchema = z.object({
  kind: z.enum(['create', 'update', 'delete']),
  path: z.string(),
});

export const watchEventsBatchSchema = z.object({
  kind: z.literal('events'),
  events: z.array(watchEventSchema),
});

export const watchResyncSchema = z.object({
  kind: z.literal('resync'),
});

export const fsWatchContract = defineContract({
  events: resourcedStream({
    key: watchKeySchema,
    event: z.union([watchEventsBatchSchema, watchResyncSchema]),
  }),
});

export type FsWatchKey = z.infer<typeof watchKeySchema>;
export type FsWatchEvent = z.infer<typeof watchEventSchema>;
export type FsWatchStreamEvent =
  | z.infer<typeof watchEventsBatchSchema>
  | z.infer<typeof watchResyncSchema>;

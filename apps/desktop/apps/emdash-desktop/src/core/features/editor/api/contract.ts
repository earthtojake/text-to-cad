import { resourceUriSchema } from '@emdash/core/primitives/path/api';
import { defineContract, procedure } from '@emdash/wire/rpc';
import { z } from 'zod';

const editorBufferKeySchema = z.object({ uri: resourceUriSchema });

export const editorDomain = 'editor' as const;

// The crash-recovery buffer store is the editor domain's only wire surface;
// file content, fs one-shots, trees, and mutations live in the `files` domain
// keyed by ResourceUri (spec §8).
export const editorContract = defineContract({
  saveBuffer: procedure({
    input: editorBufferKeySchema.extend({ content: z.string() }),
    output: z.void(),
  }),
  clearBuffer: procedure({
    input: editorBufferKeySchema,
    output: z.void(),
  }),
  // Recovery enumeration: `root` scopes to buffers under that root ResourceUri
  // prefix; omitting it lists every buffer, including files outside any root.
  listBuffers: procedure({
    input: z.object({ root: resourceUriSchema.optional() }),
    output: z.array(z.object({ uri: resourceUriSchema, content: z.string() })),
  }),
});

export type EditorContract = typeof editorContract;

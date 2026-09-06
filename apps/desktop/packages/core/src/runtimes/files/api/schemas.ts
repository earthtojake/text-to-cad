import { z } from 'zod';
import { hostAbsolutePathSchema, portableRelativePathSchema } from '#primitives/path/api';

export const rootKeySchema = z.object({ root: hostAbsolutePathSchema });
export const pathKeySchema = rootKeySchema.extend({ relative: portableRelativePathSchema });
// `fs` endpoints and the `content` live model are keyed by a bare
// host-absolute path (spec §3.4); workspace/root resolution happens at the
// desktop edge.
export const absolutePathKeySchema = z.object({ path: hostAbsolutePathSchema });
// Two-endpoint mutations (`rename`/`move`/`copy`) address source and target as
// absolute paths; rename and move stay distinct verbs taking a target identity.
export const fromToKeySchema = z.object({
  from: hostAbsolutePathSchema,
  to: hostAbsolutePathSchema,
});
export const exclusionPatternsSchema = z.array(z.string()).optional();
export const treeKeySchema = rootKeySchema.extend({
  sessionId: z.string(),
  exclusions: exclusionPatternsSchema,
});
export const contentKeySchema = absolutePathKeySchema;

export const fileStatSchema = z.object({
  path: portableRelativePathSchema,
  type: z.enum(['file', 'directory']),
  size: z.number().int().nonnegative(),
  mtimeMs: z.number(),
  ctimeMs: z.number(),
  mode: z.number().int(),
});

export const readFileOptionsSchema = z.object({
  maxBytes: z.number().int().nonnegative().optional(),
});

export const readFileKeySchema = absolutePathKeySchema.extend({
  options: readFileOptionsSchema.optional(),
});

export const readTextResultSchema = z.object({
  content: z.string(),
  truncated: z.boolean(),
  totalSize: z.number().int().nonnegative(),
  etag: z.string(),
});

export const readBytesMetaSchema = z.object({
  name: z.string(),
  mimeType: z.string(),
  size: z.number().nonnegative().optional(),
  lastModified: z.number().optional(),
  truncated: z.boolean(),
  totalSize: z.number().int().nonnegative(),
  etag: z.string(),
});

export const fileEnumerationOptionsSchema = z.object({
  includeSymlinkFiles: z.boolean().optional(),
});

export const pathBatchSchema = z.object({ paths: z.array(portableRelativePathSchema) });
export const pathListSchema = z.object({ paths: z.array(portableRelativePathSchema) });

export const writePreconditionSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('etag'), etag: z.string().min(1) }),
  z.object({ kind: z.literal('overwrite') }),
]);

export const writeContentInputSchema = z.object({
  content: z.string(),
  precondition: writePreconditionSchema,
});

export const uploadFileInputSchema = absolutePathKeySchema.extend({
  overwrite: z.boolean().optional(),
});

export const uploadFileResultSchema = z.object({
  bytesWritten: z.number().int().nonnegative(),
});

export const createFileInputSchema = absolutePathKeySchema;
export const createDirectoryInputSchema = absolutePathKeySchema;
export const deleteInputSchema = absolutePathKeySchema.extend({
  recursive: z.boolean().optional(),
});
export const writeFileInputSchema = absolutePathKeySchema.extend({
  content: z.string(),
  encoding: z.enum(['utf8', 'base64']).optional(),
  precondition: writePreconditionSchema,
});

export type RootKey = z.infer<typeof rootKeySchema>;
export type PathKey = z.infer<typeof pathKeySchema>;
export type AbsolutePathKey = z.infer<typeof absolutePathKeySchema>;
export type FromToKey = z.infer<typeof fromToKeySchema>;
export type ReadFileKey = z.infer<typeof readFileKeySchema>;
export type ExclusionPatterns = z.infer<typeof exclusionPatternsSchema>;
export type TreeKey = z.infer<typeof treeKeySchema>;
export type ContentKey = z.infer<typeof contentKeySchema>;
export type FileStat = z.infer<typeof fileStatSchema>;
export type ReadFileOptions = z.infer<typeof readFileOptionsSchema>;
export type ReadTextResult = z.infer<typeof readTextResultSchema>;
export type ReadBytesMeta = z.infer<typeof readBytesMetaSchema>;
export type FileEnumerationOptions = z.infer<typeof fileEnumerationOptionsSchema>;
export type PathBatch = z.infer<typeof pathBatchSchema>;
export type PathList = z.infer<typeof pathListSchema>;
export type WritePrecondition = z.infer<typeof writePreconditionSchema>;
export type WriteContentInput = z.infer<typeof writeContentInputSchema>;
export type UploadFileInput = z.infer<typeof uploadFileInputSchema>;
export type UploadFileResult = z.infer<typeof uploadFileResultSchema>;
export type CreateFileInput = z.infer<typeof createFileInputSchema>;
export type CreateDirectoryInput = z.infer<typeof createDirectoryInputSchema>;
export type DeleteInput = z.infer<typeof deleteInputSchema>;
export type WriteFileInput = z.infer<typeof writeFileInputSchema>;

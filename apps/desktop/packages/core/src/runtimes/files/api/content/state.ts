import { z } from 'zod';
import { portableRelativePathSchema } from '#primitives/path/api';
import type { FsError } from '#runtimes/files/api/errors';

/**
 * The closed seam-error enum (file-content-stack spec §4): every way file
 * content can fail to be served, as consumers see it. `too-large` and
 * `binary` are distinct content states below; the `unavailable` state
 * carries the remaining codes.
 */
export const contentSeamErrorCodeSchema = z.enum([
  'not-found',
  'no-permissions',
  'too-large',
  'binary',
  'unavailable',
]);
export type ContentSeamErrorCode = z.infer<typeof contentSeamErrorCodeSchema>;

/** The seam-error codes the `unavailable` content state can carry. */
export const contentUnavailableCodeSchema = contentSeamErrorCodeSchema.exclude([
  'too-large',
  'binary',
]);
export type ContentUnavailableCode = z.infer<typeof contentUnavailableCodeSchema>;

/** Maps a filesystem error onto the closed seam-error enum. */
export function contentUnavailableCode(error: FsError): ContentUnavailableCode {
  switch (error.type) {
    case 'not-found':
      return 'not-found';
    case 'permission-denied':
      return 'no-permissions';
    default:
      return 'unavailable';
  }
}

const fileContentBaseSchema = z.object({
  path: portableRelativePathSchema,
  etag: z.string(),
  byteSize: z.number().int().nonnegative(),
  readonly: z.boolean(),
});

export const fileContentModelSchema = z.discriminatedUnion('kind', [
  fileContentBaseSchema.extend({
    kind: z.literal('text'),
    content: z.string(),
    eol: z.enum(['lf', 'crlf']),
  }),
  fileContentBaseSchema.extend({
    kind: z.literal('binary'),
    mimeType: z.string().optional(),
  }),
  // Over-limit files classify as too-large instead of truncating silently (spec §3).
  z.object({
    kind: z.literal('too-large'),
    path: portableRelativePathSchema,
    byteSize: z.number().int().nonnegative(),
    limit: z.number().int().nonnegative(),
  }),
  z.object({
    kind: z.literal('unavailable'),
    path: portableRelativePathSchema,
    code: contentUnavailableCodeSchema,
  }),
]);

export type FileContentModel = z.infer<typeof fileContentModelSchema>;

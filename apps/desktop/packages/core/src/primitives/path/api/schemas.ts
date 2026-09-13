import { z } from 'zod';
import { hostRefSchema } from '#primitives/host/api';
import { parseAbsolute, type ParseAbsoluteOptions } from './absolute';
import type { PathError } from './errors';
import { parsePortableRelativePath, type ParseRelativeOptions } from './relative';
import { decodeResourceUri } from './resource-uri';
import { validateSegment } from './segments';
import type { HostAbsolutePath, HostFileRef, ResourceKey, ResourceUri } from './types';

export function resultTransform<Input, Output>(
  parse: (input: Input) => { success: true; data: Output } | { success: false; error: PathError }
): (input: Input, ctx: z.RefinementCtx) => Output {
  return (input, ctx) => {
    const result = parse(input);
    if (result.success) return result.data;
    ctx.addIssue({ code: 'custom', message: result.error.message });
    return z.NEVER;
  };
}

export function resultRefine<Input>(
  parse: (input: Input) => { success: true } | { success: false; error: PathError }
): (input: Input, ctx: z.RefinementCtx) => void {
  return (input, ctx) => {
    const result = parse(input);
    if (result.success) return;
    ctx.addIssue({ code: 'custom', message: result.error.message });
  };
}

export function portableRelativePathInputSchema(options: ParseRelativeOptions = {}) {
  return z
    .string()
    .transform(resultTransform((value) => parsePortableRelativePath(value, options)));
}

export const portableRelativePathSchema = portableRelativePathInputSchema();

export function absolutePathInputSchema(options: ParseAbsoluteOptions = {}) {
  return z.string().transform(resultTransform((value) => parseAbsolute(value, options)));
}

export const pathProfileSchema = z.object({
  style: z.enum(['posix', 'win32']),
  caseSensitivity: z.enum(['sensitive', 'insensitive']),
  unicodeNormalization: z.enum(['preserve', 'nfc']),
});

export const posixPathRootSchema = z.object({
  kind: z.literal('posix'),
});

export const drivePathRootSchema = z.object({
  kind: z.literal('drive'),
  driveLetter: z.string().regex(/^[A-Z]$/u),
});

export const uncPathRootSchema = z
  .object({
    kind: z.literal('unc'),
    server: z.string(),
    share: z.string(),
  })
  .superRefine((root, ctx) => {
    addSegmentIssue(root.server, 'server', false, ctx);
    addSegmentIssue(root.share, 'share', false, ctx);
  });

export const hostPathRootSchema = z.union([
  posixPathRootSchema,
  drivePathRootSchema,
  uncPathRootSchema,
]);

export const hostAbsolutePathSchema = z
  .object({
    root: hostPathRootSchema,
    segments: z.array(z.string()),
  })
  .superRefine((path, ctx) => {
    const allowBackslash = path.root.kind === 'posix';
    path.segments.forEach((segment, index) => {
      addSegmentIssue(segment, ['segments', index], allowBackslash, ctx);
    });
  })
  .transform((path) => path as HostAbsolutePath);

export const hostFileRefSchema = z
  .object({
    host: hostRefSchema,
    path: hostAbsolutePathSchema,
  })
  .transform((ref) => ref as HostFileRef);

export const scopedPathSchema = z.object({
  root: hostFileRefSchema,
  relative: portableRelativePathSchema,
});

export const resourceUriSchema = z
  .string()
  .superRefine(resultRefine(decodeResourceUri))
  .transform((value) => value as ResourceUri);

export const resourceRefFromUriSchema = z.string().transform(resultTransform(decodeResourceUri));

export const resourceKeySchema = z
  .string()
  .min(1)
  .transform((value) => value as ResourceKey);

export type HostFileRefInput = z.input<typeof hostFileRefSchema>;
export type HostFileRefOutput = z.output<typeof hostFileRefSchema>;
export type ScopedPathInput = z.input<typeof scopedPathSchema>;
export type ScopedPathOutput = z.output<typeof scopedPathSchema>;
export type ResourceUriInput = z.input<typeof resourceUriSchema>;
export type ResourceUriOutput = z.output<typeof resourceUriSchema>;

function addSegmentIssue(
  segment: string,
  path: string | (string | number)[],
  allowBackslash: boolean,
  ctx: z.RefinementCtx
): void {
  const result = validateSegment(segment, segment, {
    normalization: 'preserve',
    allowBackslash,
  });
  if (result.success) return;
  ctx.addIssue({
    code: 'custom',
    message: result.error.message,
    path: Array.isArray(path) ? path : [path],
  });
}

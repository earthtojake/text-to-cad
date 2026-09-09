import { z } from 'zod';
import { portableRelativePathSchema } from '#primitives/path/api';
import { gitBranchRefSchema } from '#runtimes/git/api/repository/states/refs';
import { gitOperationCredentialsSchema } from '#runtimes/git/api/schemas';
import { checkoutSelectorSchema } from '#runtimes/git/api/selectors';

/**
 * Checkout subdomain schemas: the read/diff/history vocabulary and the option
 * shapes for checkout mutations and jobs. Object refs reference the repository's
 * branch model (a checkout resolves refs against its repository).
 */

export const gitChangeStatusSchema = z.enum([
  'added',
  'modified',
  'deleted',
  'renamed',
  'conflicted',
]);
export type GitChangeStatus = z.infer<typeof gitChangeStatusSchema>;

export const gitFilePathSchema = portableRelativePathSchema.refine(
  (path) => path.length > 0,
  'Git file path must not be empty'
);
export type GitFilePath = z.infer<typeof gitFilePathSchema>;

/** Paths within a checkout use the portable, checkout-relative path vocabulary. */
export const fileChangeSchema = z.object({
  path: gitFilePathSchema,
  status: gitChangeStatusSchema,
  additions: z.number().int(),
  deletions: z.number().int(),
  indexOid: z.string().optional(),
});
export type FileChange = z.infer<typeof fileChangeSchema>;

export const gitChangeSchema = fileChangeSchema;
export type GitChange = z.infer<typeof gitChangeSchema>;

export const commitSchema = z.object({
  hash: z.string(),
  parents: z.array(z.string()),
  subject: z.string(),
  body: z.string(),
  author: z.string(),
  /** Author date as epoch milliseconds (convention 4). */
  date: z.number().int(),
  isPushed: z.boolean(),
  tags: z.array(z.string()),
});
export type Commit = z.infer<typeof commitSchema>;

export const commitFileSchema = fileChangeSchema;
export type CommitFile = z.infer<typeof commitFileSchema>;

export const gitLogResultSchema = z.object({
  commits: z.array(commitSchema),
  totalCount: z.number().int().nonnegative(),
});
export type GitLogResult = z.infer<typeof gitLogResultSchema>;

export const blameHunkSchema = z.object({
  oid: z.string(),
  author: z.string(),
  authorEmail: z.string(),
  /** Author date as epoch milliseconds (convention 4). */
  date: z.number().int(),
  summary: z.string(),
  startLine: z.number().int(),
  lineCount: z.number().int(),
});
export type BlameHunk = z.infer<typeof blameHunkSchema>;

export const blameResultSchema = z.object({
  hunks: z.array(blameHunkSchema),
});
export type BlameResult = z.infer<typeof blameResultSchema>;

export const downloadMetaSchema = z.object({
  name: z.string(),
  mimeType: z.string(),
  size: z.number().int().nonnegative(),
});
export type DownloadMeta = z.infer<typeof downloadMetaSchema>;

export const diffModeSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('head') }),
  z.object({ kind: z.literal('staged') }),
  z.object({ kind: z.literal('unstaged') }),
]);
export type DiffMode = z.infer<typeof diffModeSchema>;

export const gitObjectRefSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('branch'), branch: gitBranchRefSchema }),
  z.object({ kind: z.literal('commit'), sha: z.string() }),
  z.object({ kind: z.literal('tag'), name: z.string() }),
]);
export type GitObjectRef = z.infer<typeof gitObjectRefSchema>;

export const gitFileSourceSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('head') }),
  z.object({ kind: z.literal('index') }),
  z.object({ kind: z.literal('revision'), revision: gitObjectRefSchema }),
]);
export type GitFileSource = z.infer<typeof gitFileSourceSchema>;

export const mergeBaseRangeSchema = z.object({
  base: gitObjectRefSchema,
  head: gitObjectRefSchema,
});
export type MergeBaseRange = z.infer<typeof mergeBaseRangeSchema>;

export const diffTargetSchema = z.union([diffModeSchema, gitObjectRefSchema, mergeBaseRangeSchema]);
export type DiffTarget = z.infer<typeof diffTargetSchema>;

export const normalizedDiffTargetSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('working-vs-head') }),
  z.object({ kind: z.literal('working-vs-index') }),
  z.object({ kind: z.literal('staged-vs-head') }),
  z.object({ kind: z.literal('working-vs-ref'), ref: gitObjectRefSchema }),
  z.object({ kind: z.literal('merge-base'), base: gitObjectRefSchema, head: gitObjectRefSchema }),
]);
export type NormalizedDiffTarget = z.infer<typeof normalizedDiffTargetSchema>;

export function normalizeDiffTarget(target: DiffTarget = { kind: 'head' }): NormalizedDiffTarget {
  if ('base' in target) return { kind: 'merge-base', base: target.base, head: target.head };
  if (target.kind === 'head') return { kind: 'working-vs-head' };
  if (target.kind === 'unstaged') return { kind: 'working-vs-index' };
  if (target.kind === 'staged') return { kind: 'staged-vs-head' };
  return { kind: 'working-vs-ref', ref: target };
}

export function denormalizeDiffTarget(target: NormalizedDiffTarget): DiffTarget {
  switch (target.kind) {
    case 'working-vs-head':
      return { kind: 'head' };
    case 'working-vs-index':
      return { kind: 'unstaged' };
    case 'staged-vs-head':
      return { kind: 'staged' };
    case 'working-vs-ref':
      return target.ref;
    case 'merge-base':
      return { base: target.base, head: target.head };
  }
}

export function toRefString(ref: GitObjectRef): string {
  switch (ref.kind) {
    case 'branch':
      return ref.branch.type === 'remote'
        ? `${ref.branch.remote.name}/${ref.branch.branch}`
        : ref.branch.branch;
    case 'commit':
      return ref.sha;
    case 'tag':
      return ref.name;
  }
}

export function toRangeString(range: MergeBaseRange): string {
  return `${toRefString(range.base)}...${toRefString(range.head)}`;
}

// -- Mutation option shapes --

// GitLogOptions.base/head are restricted to GitObjectRef (branch|commit|tag only)
export const gitLogOptionsSchema = z.object({
  limit: z.number().int().optional(),
  skip: z.number().int().optional(),
  base: gitObjectRefSchema.optional(),
  head: gitObjectRefSchema.optional(),
});
export type GitLogOptions = z.infer<typeof gitLogOptionsSchema>;

export const commitOptionsSchema = z.object({
  amend: z.boolean().optional(),
  signoff: z.boolean().optional(),
  noVerify: z.boolean().optional(),
  allowEmpty: z.boolean().optional(),
});
export type CommitOptions = z.infer<typeof commitOptionsSchema>;

export const pushOptionsSchema = z.object({
  remote: z.string().optional(),
  force: z.boolean().optional(),
});
export type PushOptions = z.infer<typeof pushOptionsSchema>;

// -- Job inputs --

export const pushJobInputSchema = checkoutSelectorSchema.extend({
  options: pushOptionsSchema.optional(),
  credentials: gitOperationCredentialsSchema.optional(),
});
export type PushJobInput = z.infer<typeof pushJobInputSchema>;

export const publishJobInputSchema = checkoutSelectorSchema.extend({
  remote: z.string().min(1),
  credentials: gitOperationCredentialsSchema.optional(),
});
export type PublishJobInput = z.infer<typeof publishJobInputSchema>;

export const pullJobInputSchema = checkoutSelectorSchema.extend({
  credentials: gitOperationCredentialsSchema.optional(),
});
export type PullJobInput = z.infer<typeof pullJobInputSchema>;

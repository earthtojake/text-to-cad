import { z } from 'zod';
import { gitCredentialChannelSchema } from '#primitives/git-credentials/api';
import { hostAbsolutePathSchema } from '#primitives/path/api';

/**
 * Operation-scoped emdash credential-helper context for network jobs
 * (spec: github-git-settings §4): a per-operation channel to the desktop
 * credential server plus the normalized HTTPS host it answers for. Carries
 * only the loopback channel — never token material. Absent = native
 * credential behavior.
 */
export const gitOperationCredentialsSchema = gitCredentialChannelSchema.extend({
  host: z.string().min(1),
});
export type GitOperationCredentials = z.infer<typeof gitOperationCredentialsSchema>;

export const ensureRepositoryOptionsSchema = z.object({
  initIfMissing: z.boolean().optional(),
});
export type EnsureRepositoryOptions = z.infer<typeof ensureRepositoryOptionsSchema>;

export const gitRepositoryInfoSchema = z.object({
  kind: z.literal('repository'),
  rootPath: hostAbsolutePathSchema,
  baseRef: z.string(),
});
export type GitRepositoryInfo = z.infer<typeof gitRepositoryInfoSchema>;

// Success data of the fallible `inspectPath`: repository/not-repository are
// answers; a failed inspection is the verb's declared error.
export const gitPathInspectionSchema = z.discriminatedUnion('kind', [
  gitRepositoryInfoSchema,
  z.object({ kind: z.literal('not-repository'), path: hostAbsolutePathSchema }),
]);
export type GitPathInspection = z.infer<typeof gitPathInspectionSchema>;

export const cloneRepositoryJobInputSchema = z.object({
  repositoryUrl: z.string(),
  targetPath: hostAbsolutePathSchema,
  credentials: gitOperationCredentialsSchema.optional(),
});
export type CloneRepositoryJobInput = z.infer<typeof cloneRepositoryJobInputSchema>;

export const transferProgressSchema = z.object({
  phase: z.string(),
  percent: z.number().int().min(0).max(100).optional(),
  objects: z
    .object({
      done: z.number().int().nonnegative(),
      total: z.number().int().nonnegative(),
    })
    .optional(),
  detail: z.string().optional(),
});
export type GitTransferProgress = z.infer<typeof transferProgressSchema>;

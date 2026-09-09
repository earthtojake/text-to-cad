import { z } from 'zod';
import { gitOperationCredentialsSchema } from '#runtimes/git/api/schemas';
import { repositorySelectorSchema } from '#runtimes/git/api/selectors';

/**
 * Repository subdomain schemas: the input shapes for repository-scoped jobs
 * (fetch / fetch-PR). The worktree descriptor (`checkoutInfoSchema`)
 * is cross-cutting and lives in `../api/schemas`.
 */

export const fetchPrForReviewOptionsSchema = z.object({
  prNumber: z.number().int(),
  headRefName: z.string(),
  headRepositoryUrl: z.string(),
  localBranch: z.string(),
  isFork: z.boolean(),
  /**
   * The effective base remote, resolved by the caller (blessed resolver;
   * spec: github-git-settings §2) — this layer never invents one. Unused for
   * fork PRs, which fetch through a dedicated fork remote.
   */
  configuredRemote: z.string(),
});
export type FetchPrForReviewOptions = z.infer<typeof fetchPrForReviewOptionsSchema>;

// -- Job inputs --

export const fetchJobInputSchema = repositorySelectorSchema.extend({
  remote: z.string().optional(),
  refspec: z.string().optional(),
  force: z.boolean().optional(),
  credentials: gitOperationCredentialsSchema.optional(),
});
export type FetchJobInput = z.infer<typeof fetchJobInputSchema>;

export const fetchPrForReviewJobInputSchema = repositorySelectorSchema.extend({
  options: fetchPrForReviewOptionsSchema,
  credentials: gitOperationCredentialsSchema.optional(),
});
export type FetchPrForReviewJobInput = z.infer<typeof fetchPrForReviewJobInputSchema>;

import { err, type Result } from '@emdash/shared';
import { parseRepositoryRef } from '@core/primitives/repository/api';
import type { GitHubAuthError } from '@core/services/pull-requests/api';

export type PullRequestSyncIdentity = { accountId: string };

export type PullRequestSyncIdentityResolver = (
  repositoryUrl: string
) => Promise<Result<PullRequestSyncIdentity, GitHubAuthError>>;

let boundResolver: PullRequestSyncIdentityResolver | undefined;

/**
 * Late-binding seam between the pull-request worker's auth controller (wired
 * at worker spawn, before services boot) and the identity resolution that
 * lives with the desktop registration. Until a resolver is bound, identity
 * requests fail closed — the sync is skipped and retried later, never run as
 * an implicit default account.
 */
export function bindPullRequestSyncIdentityResolver(
  resolver: PullRequestSyncIdentityResolver
): void {
  boundResolver = resolver;
}

export async function resolvePullRequestSyncIdentity(
  repositoryUrl: string
): Promise<Result<PullRequestSyncIdentity, GitHubAuthError>> {
  if (!boundResolver) {
    return err({
      type: 'account_unresolvable',
      host: parseRepositoryRef(repositoryUrl)?.host ?? 'unknown',
      message: 'GitHub identity resolution is not available yet; the desktop is still starting.',
    });
  }
  return await boundResolver(repositoryUrl);
}

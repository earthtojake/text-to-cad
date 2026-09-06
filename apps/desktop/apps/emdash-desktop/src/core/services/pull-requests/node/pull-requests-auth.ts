import { err, ok, type Result } from '@emdash/shared';
import { createController, type Controller } from '@emdash/wire/rpc';
import { parseRepositoryRef } from '@core/primitives/repository/api';
import { githubAuthContract, type GitHubAuthError } from '@core/services/pull-requests/api';
import type { PullRequestSyncIdentityResolver } from './sync-identity';

type GitHubTokenService = {
  getToken(
    host: string,
    context?: { accountId?: string }
  ): Promise<Result<string, GitHubAuthError>>;
};

/**
 * Desktop-side answer to the worker's per-sync identity request (spec:
 * github-git-settings §8): resolve *as whom* through the blessed resolver for
 * the repository, then fetch that account's token. Identity failures pass
 * through fail-closed — the worker skips the sync instead of running as a
 * different account.
 */
export function createPullRequestsGitHubAuthController(
  tokenService: GitHubTokenService,
  apiBaseUrlForHost: (host: string) => string,
  resolveSyncIdentity: PullRequestSyncIdentityResolver
): Controller {
  return createController(githubAuthContract, {
    resolveAuth: async (input) => {
      const repository = parseRepositoryRef(input.repositoryUrl);
      if (!repository) {
        return err({
          type: 'account_unresolvable',
          host: 'unknown',
          message: `Unrecognized repository URL: ${input.repositoryUrl}`,
        });
      }
      const identity = await resolveSyncIdentity(input.repositoryUrl);
      if (!identity.success) return identity;
      const token = await tokenService.getToken(repository.host, {
        accountId: identity.data.accountId,
      });
      if (!token.success) return token;
      return ok({
        token: token.data,
        host: repository.host,
        apiBaseUrl: apiBaseUrlForHost(repository.host),
        accountId: identity.data.accountId,
      });
    },
  });
}

import { err, ok, type Result } from '@emdash/shared';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import { resolveAccountForHost } from '@core/primitives/project-settings/api';
import { normalizeRepositoryHost } from '@core/primitives/repository/api';
import {
  GITHUB_PROVIDER_ID,
  listGitHubAccountSummaries,
  type GitHubAccountStore,
} from '../../../node/accounts/github-accounts';
import {
  githubApiAccountHostMismatch,
  githubApiAccountNotFound,
  githubApiAuthRequired,
  githubApiTokenMissing,
  type GitHubApiAuthError,
} from '../../../node/services/github-api-auth-errors';

export type GitHubApiAuthContext = {
  accountId?: string;
};

type GitHubAccountLookup = Pick<
  GitHubAccountStore,
  'getDefaultAccountId' | 'listAccounts' | 'resolveSecret'
>;

export class GitHubApiAuthService {
  constructor(private readonly accountLookup: GitHubAccountLookup) {}

  async getToken(
    host: string,
    context: GitHubApiAuthContext = {}
  ): Promise<Result<string, GitHubApiAuthError>> {
    const normalizedHost = normalizeRepositoryHost(host);
    const accountId = context.accountId?.trim() || null;
    const account = await this.resolveAccount(normalizedHost, accountId);
    if (!account) return err(githubApiAuthRequired(normalizedHost));
    if (!account.success) return err(account.error);

    const token = await this.accountLookup.resolveSecret(
      GITHUB_PROVIDER_ID,
      account.data.accountId
    );
    if (!token) return err(githubApiTokenMissing(normalizedHost, account.data.accountId));
    return ok(token);
  }

  private async resolveAccount(
    normalizedHost: string,
    accountId: string | null
  ): Promise<Result<GitHubAccountSummary, GitHubApiAuthError> | null> {
    const accounts = await listGitHubAccountSummaries(this.accountLookup);
    if (accountId) {
      // Fail closed on a dangling or host-mismatched pin — never another identity.
      const account = accounts.find((candidate) => candidate.accountId === accountId);
      if (!account) return err(githubApiAccountNotFound(normalizedHost, accountId));

      const accountHost = normalizeRepositoryHost(account.host);
      if (accountHost !== normalizedHost) {
        return err(githubApiAccountHostMismatch(normalizedHost, account.accountId, accountHost));
      }

      return ok(account);
    }

    // No pin: the single blessed "default account for host" inference
    // (spec: github-git-settings §2/§11).
    const inferred = resolveAccountForHost(normalizedHost, accounts);
    return inferred.value ? ok(inferred.value) : null;
  }
}

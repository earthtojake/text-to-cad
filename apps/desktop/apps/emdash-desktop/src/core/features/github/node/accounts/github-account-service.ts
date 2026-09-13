import type {
  GitHubAccountSummary,
  GitHubImportCliAccountsResponse,
} from '@core/primitives/github/api';
import {
  GITHUB_PROVIDER_ID,
  listGitHubAccountSummaries,
  toGitHubAccount,
  type GitHubAccount,
  type GitHubAccountStore,
} from './github-accounts';
import type { GitHubCliAccountImportService } from './github-cli-account-import';

type GitHubAccountServiceStore = Pick<
  GitHubAccountStore,
  'listAccounts' | 'getDefaultAccountId' | 'setDefaultAccount' | 'removeAccount'
>;

type GitHubCliAccountImporter = Pick<GitHubCliAccountImportService, 'importAccounts'>;

export class GitHubAccountService {
  constructor(
    private readonly accountStore: GitHubAccountServiceStore,
    private readonly cliAccountImporter: GitHubCliAccountImporter,
    private readonly clearCachedClients: (host?: string, accountId?: string) => void = () => {}
  ) {}

  async listAccounts(): Promise<GitHubAccountSummary[]> {
    return listGitHubAccountSummaries(this.accountStore);
  }

  async importCliAccounts(): Promise<Extract<GitHubImportCliAccountsResponse, { success: true }>> {
    const imported = await this.cliAccountImporter.importAccounts();
    const importedAccountIds = [...new Set(imported.map((account) => account.accountId))];
    return {
      success: true,
      accounts: await this.listAccounts(),
      importedAccountIds,
    };
  }

  async setDefaultAccount(accountId: string): Promise<GitHubAccountSummary | null> {
    const account = await this.accountStore.setDefaultAccount(GITHUB_PROVIDER_ID, accountId);
    if (!account) return null;
    return this.toAccountSummary(toGitHubAccount(account), account.accountId);
  }

  async removeAccount(accountId: string): Promise<GitHubAccountSummary[] | null> {
    const removed = await this.accountStore.removeAccount(GITHUB_PROVIDER_ID, accountId);
    if (!removed) return null;

    const account = toGitHubAccount(removed);
    this.clearCachedClients(account.host, account.accountId);
    return this.listAccounts();
  }

  private toAccountSummary(
    account: GitHubAccount,
    defaultAccountId: string | null
  ): GitHubAccountSummary {
    return {
      accountId: account.accountId,
      host: account.host,
      login: account.login,
      avatarUrl: account.avatarUrl,
      credentialSource: account.credentialSource,
      isDefault: account.accountId === defaultAccountId,
    };
  }
}

import type { CommandRunner } from '@core/primitives/command-runner/api/command-runner';
import type { GitHubUser } from '@core/primitives/github/api';
import { normalizeRepositoryHost } from '@core/primitives/repository/api';
import {
  upsertGitHubAccount,
  type GitHubAccount,
  type GitHubAccountStore,
} from './github-accounts';

type GitHubIdentityClient = {
  getAuthenticatedUser(token: string, host?: string): Promise<GitHubUser | null>;
};

type GitHubCliAuthStatusEntry = {
  state?: unknown;
  host?: unknown;
  login?: unknown;
  token?: unknown;
};

type GitHubCliAuthStatus = {
  hosts?: unknown;
};

const GITHUB_CLI_AUTH_STATUS_TIMEOUT_MS = 5_000;

function parseCliStatus(raw: string): GitHubCliAuthStatus {
  try {
    const parsed = JSON.parse(raw);
    return typeof parsed === 'object' && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

function cliEntries(status: GitHubCliAuthStatus): GitHubCliAuthStatusEntry[] {
  if (typeof status.hosts !== 'object' || status.hosts === null) return [];
  const entries: GitHubCliAuthStatusEntry[] = [];
  for (const [host, rawHostEntries] of Object.entries(status.hosts)) {
    if (!Array.isArray(rawHostEntries)) continue;
    for (const rawEntry of rawHostEntries) {
      if (typeof rawEntry !== 'object' || rawEntry === null) continue;
      entries.push({ ...(rawEntry as GitHubCliAuthStatusEntry), host });
    }
  }
  return entries;
}

export class GitHubCliAccountImportService {
  constructor(
    private readonly accountStore: Pick<GitHubAccountStore, 'upsertAccount'>,
    private readonly exec: CommandRunner,
    private readonly identityClient: GitHubIdentityClient
  ) {}

  async importAccounts(): Promise<GitHubAccount[]> {
    const stdout = await this.readCliStatus();
    if (!stdout) return [];

    const imported: GitHubAccount[] = [];
    for (const entry of cliEntries(parseCliStatus(stdout))) {
      if (entry.state !== 'success') continue;
      if (typeof entry.token !== 'string' || entry.token.trim().length === 0) continue;
      const host = typeof entry.host === 'string' ? normalizeRepositoryHost(entry.host) : '';
      if (!host) continue;

      const token = entry.token.trim();
      const user = await this.identityClient.getAuthenticatedUser(token, host);
      if (!user) continue;

      const { account } = await upsertGitHubAccount(this.accountStore, {
        accessToken: token,
        credentialSource: 'cli',
        providerAccount: {
          providerId: 'github',
          providerAccountId: String(user.id),
          host,
          login: user.login,
          avatarUrl: user.avatar_url,
        },
      });
      imported.push(account);
    }
    return imported;
  }

  private async readCliStatus(): Promise<string | null> {
    try {
      const { stdout } = await this.exec(
        'gh',
        ['auth', 'status', '--json', 'hosts', '--show-token'],
        { timeout: GITHUB_CLI_AUTH_STATUS_TIMEOUT_MS }
      );
      return stdout;
    } catch {
      return null;
    }
  }
}

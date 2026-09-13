import type { GitHubTokenSource } from '@core/primitives/github/api';

export const GITHUB_TOKEN_SECRET_KEY = 'emdash-github-token';

type LegacyTokenSource = Exclude<GitHubTokenSource, null>;

type LegacySecretStore = {
  getSecret(key: string): Promise<string | null>;
  deleteSecret(key: string): Promise<void>;
};

type LegacyTokenSourceStore = {
  getTokenSource(): Promise<unknown>;
  clearTokenSource(): Promise<void>;
};

function parseTokenSource(raw: unknown): LegacyTokenSource | null {
  return raw === 'cli' ||
    raw === 'secure_storage' ||
    raw === 'emdash_oauth' ||
    raw === 'device_flow'
    ? raw
    : null;
}

export class LegacyGitHubTokenMigrationStore {
  constructor(
    private readonly secretStore: LegacySecretStore,
    private readonly tokenSourceStore: LegacyTokenSourceStore
  ) {}

  async getStoredTokenRecord(): Promise<{
    token: string;
    source: LegacyTokenSource | null;
  } | null> {
    const token = await this.secretStore.getSecret(GITHUB_TOKEN_SECRET_KEY);
    if (!token) return null;
    return {
      token,
      source: parseTokenSource(await this.tokenSourceStore.getTokenSource()),
    };
  }

  async clearStoredToken(): Promise<void> {
    await Promise.all([
      this.secretStore.deleteSecret(GITHUB_TOKEN_SECRET_KEY),
      this.tokenSourceStore.clearTokenSource(),
    ]);
  }
}

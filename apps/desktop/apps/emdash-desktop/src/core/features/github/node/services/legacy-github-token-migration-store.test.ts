import { describe, expect, it } from 'vitest';
import { LegacyGitHubTokenMigrationStore } from './legacy-github-token-migration-store';

class InMemorySecretStore {
  secrets = new Map<string, string>();

  async getSecret(key: string) {
    return this.secrets.get(key) ?? null;
  }

  async deleteSecret(key: string) {
    this.secrets.delete(key);
  }
}

class InMemoryTokenSourceStore {
  source: unknown = null;
  deleted = false;

  async getTokenSource() {
    return this.source;
  }

  async clearTokenSource() {
    this.deleted = true;
    this.source = null;
  }
}

describe('LegacyGitHubTokenMigrationStore', () => {
  it('reads a legacy token record and parses valid token sources', async () => {
    const secrets = new InMemorySecretStore();
    const tokenSources = new InMemoryTokenSourceStore();
    secrets.secrets.set('emdash-github-token', 'gho_legacy');
    tokenSources.source = 'device_flow';
    const store = new LegacyGitHubTokenMigrationStore(secrets, tokenSources);

    await expect(store.getStoredTokenRecord()).resolves.toEqual({
      token: 'gho_legacy',
      source: 'device_flow',
    });
  });

  it('treats invalid token sources as secure storage', async () => {
    const secrets = new InMemorySecretStore();
    const tokenSources = new InMemoryTokenSourceStore();
    secrets.secrets.set('emdash-github-token', 'gho_legacy');
    tokenSources.source = 'unknown';
    const store = new LegacyGitHubTokenMigrationStore(secrets, tokenSources);

    await expect(store.getStoredTokenRecord()).resolves.toEqual({
      token: 'gho_legacy',
      source: null,
    });
  });

  it('clears the legacy token and token source after migration', async () => {
    const secrets = new InMemorySecretStore();
    const tokenSources = new InMemoryTokenSourceStore();
    secrets.secrets.set('emdash-github-token', 'gho_legacy');
    tokenSources.source = 'cli';
    const store = new LegacyGitHubTokenMigrationStore(secrets, tokenSources);

    await store.clearStoredToken();

    await expect(secrets.getSecret('emdash-github-token')).resolves.toBeNull();
    expect(tokenSources.deleted).toBe(true);
  });
});

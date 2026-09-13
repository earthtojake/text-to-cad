import { openRegistryFixture, type RegistryFixture } from '@tooling/utils/provider-accounts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { GitHubTokenSource, GitHubUser } from '@core/primitives/github/api';
import { GITHUB_PROVIDER_ID, upsertGitHubAccount } from './github-accounts';
import { GitHubLegacyTokenImportStep } from './github-legacy-token-import-step';

const FLAG_KEY = 'github-legacy-token-import:completedAt';

class LegacyGitHubConnection {
  token: string | null = 'gho_monalisa';
  source: Exclude<GitHubTokenSource, null> | null = 'secure_storage';
  getStoredTokenRecord = vi.fn(async () =>
    this.token === null ? null : { token: this.token, source: this.source }
  );
  clearStoredToken = vi.fn(async () => {
    this.token = null;
  });
}

class GitHubIdentityClient {
  user: GitHubUser | null = {
    id: 42,
    login: 'monalisa',
    name: 'Mona Lisa',
    email: 'mona@example.com',
    avatar_url: 'https://avatars.githubusercontent.com/u/42',
  };

  getAuthenticatedUser = vi.fn(async () => this.user);
}

describe('GitHubLegacyTokenImportStep', () => {
  let fixture: RegistryFixture;
  let legacyConnection: LegacyGitHubConnection;
  let identityClient: GitHubIdentityClient;
  let step: GitHubLegacyTokenImportStep;

  beforeEach(async () => {
    fixture = await openRegistryFixture('empty');
    legacyConnection = new LegacyGitHubConnection();
    identityClient = new GitHubIdentityClient();
    step = new GitHubLegacyTokenImportStep(
      fixture.db,
      fixture.registry,
      legacyConnection,
      identityClient
    );
  });

  afterEach(() => {
    fixture?.close();
  });

  function storedFlag(): string | undefined {
    const row = fixture.sqlite.prepare(`SELECT value FROM kv WHERE key = ?`).get(FLAG_KEY) as
      | { value: string }
      | undefined;
    return row?.value;
  }

  it('imports the legacy token into an account, clears it, and sets the done-flag', async () => {
    const result = await step.run();

    expect(result).toMatchObject({
      status: 'imported',
      account: {
        accountId: 'github.com:42',
        login: 'monalisa',
        credentialSource: 'secure_storage',
      },
    });
    await expect(fixture.registry.resolveSecret(GITHUB_PROVIDER_ID, 'github.com:42')).resolves.toBe(
      'gho_monalisa'
    );
    await expect(fixture.registry.getDefaultAccountId(GITHUB_PROVIDER_ID)).resolves.toBe(
      'github.com:42'
    );
    expect(legacyConnection.clearStoredToken).toHaveBeenCalled();
    expect(storedFlag()).toBeDefined();
  });

  it('never probes secret storage again once the flag is set', async () => {
    await expect(step.run()).resolves.toMatchObject({ status: 'imported' });

    legacyConnection.getStoredTokenRecord.mockClear();
    await expect(step.run()).resolves.toEqual({ status: 'already-completed' });
    expect(legacyConnection.getStoredTokenRecord).not.toHaveBeenCalled();
  });

  it('completes immediately on a fresh install with no legacy token', async () => {
    legacyConnection.token = null;

    await expect(step.run()).resolves.toEqual({ status: 'no-legacy-token' });
    expect(identityClient.getAuthenticatedUser).not.toHaveBeenCalled();
    await expect(fixture.registry.listAccounts(GITHUB_PROVIDER_ID)).resolves.toEqual([]);
    expect(storedFlag()).toBeDefined();

    await expect(step.run()).resolves.toEqual({ status: 'already-completed' });
  });

  it('leaves the flag unset when the identity lookup fails, so the next launch retries', async () => {
    identityClient.user = null;

    await expect(step.run()).resolves.toEqual({ status: 'retry' });
    expect(legacyConnection.clearStoredToken).not.toHaveBeenCalled();
    await expect(fixture.registry.listAccounts(GITHUB_PROVIDER_ID)).resolves.toEqual([]);
    expect(storedFlag()).toBeUndefined();

    identityClient.user = {
      id: 42,
      login: 'monalisa',
      name: 'Mona Lisa',
      email: 'mona@example.com',
      avatar_url: 'https://avatars.githubusercontent.com/u/42',
    };
    await expect(step.run()).resolves.toMatchObject({ status: 'imported' });
    expect(storedFlag()).toBeDefined();
  });

  it('does not replace an existing default account', async () => {
    const { account: existing } = await upsertGitHubAccount(fixture.registry, {
      accessToken: 'gho_octocat',
      credentialSource: 'emdash_oauth',
      providerAccount: {
        providerId: 'github',
        providerAccountId: '84',
        host: 'github.com',
        login: 'octocat',
        avatarUrl: '',
      },
    });

    await expect(step.run()).resolves.toMatchObject({
      status: 'imported',
      account: { accountId: 'github.com:42' },
    });
    await expect(fixture.registry.getDefaultAccountId(GITHUB_PROVIDER_ID)).resolves.toBe(
      existing.accountId
    );
  });

  it('uses CLI as the credential source when the legacy token came from GitHub CLI', async () => {
    legacyConnection.source = 'cli';

    await expect(step.run()).resolves.toMatchObject({
      status: 'imported',
      account: { credentialSource: 'cli' },
    });
  });
});

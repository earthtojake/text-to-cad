import { openRegistryFixture, type RegistryFixture } from '@tooling/utils/provider-accounts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GitHubAccountService } from './github-account-service';
import { GITHUB_PROVIDER_ID, upsertGitHubAccount, type GitHubAccount } from './github-accounts';

describe('GitHubAccountService', () => {
  let fixture: RegistryFixture;
  let service: GitHubAccountService;
  let importCliAccounts: () => Promise<GitHubAccount[]>;
  let clearOctokitCache: (host?: string, accountId?: string) => void;

  beforeEach(async () => {
    fixture = await openRegistryFixture('empty');
    importCliAccounts = async () => [];
    clearOctokitCache = vi.fn();
    service = new GitHubAccountService(
      fixture.registry,
      {
        importAccounts: () => importCliAccounts(),
      },
      clearOctokitCache
    );
  });

  afterEach(() => {
    fixture?.close();
  });

  async function upsertAccount(login: string, providerAccountId: string, host = 'github.com') {
    return (
      await upsertGitHubAccount(fixture.registry, {
        accessToken: `token-${host}-${providerAccountId}`,
        credentialSource: host === 'github.com' ? 'emdash_oauth' : 'cli',
        providerAccount: {
          providerId: 'github',
          providerAccountId,
          host,
          login,
          avatarUrl: `https://${host}/avatars/${providerAccountId}`,
        },
      })
    ).account;
  }

  it('lists linked accounts with exactly one default account marker', async () => {
    const first = await upsertAccount('monalisa', '42');
    const second = await upsertAccount('enterprise-monalisa', '42', 'ghe.example.com');
    await fixture.registry.setDefaultAccount(GITHUB_PROVIDER_ID, second.accountId);

    await expect(service.listAccounts()).resolves.toEqual([
      {
        accountId: first.accountId,
        host: 'github.com',
        login: 'monalisa',
        avatarUrl: 'https://github.com/avatars/42',
        credentialSource: 'emdash_oauth',
        isDefault: false,
      },
      {
        accountId: second.accountId,
        host: 'ghe.example.com',
        login: 'enterprise-monalisa',
        avatarUrl: 'https://ghe.example.com/avatars/42',
        credentialSource: 'cli',
        isDefault: true,
      },
    ]);
  });

  it('returns null instead of changing the default for an unknown account id', async () => {
    const account = await upsertAccount('monalisa', '42');

    await expect(service.setDefaultAccount('github.com:missing')).resolves.toBeNull();
    await expect(fixture.registry.getDefaultAccountId(GITHUB_PROVIDER_ID)).resolves.toBe(
      account.accountId
    );
  });

  it('marks the new default account in the returned summary', async () => {
    await upsertAccount('monalisa', '42');
    const second = await upsertAccount('octocat', '84');

    await expect(service.setDefaultAccount(second.accountId)).resolves.toMatchObject({
      accountId: second.accountId,
      isDefault: true,
    });
  });

  it('imports CLI accounts and returns the refreshed account list', async () => {
    const existing = await upsertAccount('monalisa', '42');
    importCliAccounts = async () => [await upsertAccount('enterprise', '168', 'ghe.example.com')];

    const result = await service.importCliAccounts();

    expect(result.importedAccountIds).toEqual(['ghe.example.com:168']);
    expect(result.accounts).toMatchObject([
      { accountId: existing.accountId, login: 'monalisa', isDefault: true },
      { accountId: 'ghe.example.com:168', login: 'enterprise', isDefault: false },
    ]);
    await expect(
      fixture.registry.resolveSecret(GITHUB_PROVIDER_ID, 'ghe.example.com:168')
    ).resolves.toBe('token-ghe.example.com-168');
  });

  it('deduplicates imported account ids returned by the CLI importer', async () => {
    importCliAccounts = async () => {
      const account = await upsertAccount('monalisa', '42');
      return [account, account];
    };

    const result = await service.importCliAccounts();

    expect(result.importedAccountIds).toEqual(['github.com:42']);
  });

  it('returns the fallback default when removing the default account', async () => {
    const first = await upsertAccount('monalisa', '42');
    const second = await upsertAccount('octocat', '84');
    await fixture.registry.setDefaultAccount(GITHUB_PROVIDER_ID, second.accountId);

    const accounts = await service.removeAccount(second.accountId);

    expect(accounts).toMatchObject([{ accountId: first.accountId, isDefault: true }]);
    await expect(
      fixture.registry.resolveSecret(GITHUB_PROVIDER_ID, second.accountId)
    ).resolves.toBeNull();
    expect(clearOctokitCache).toHaveBeenCalledWith('github.com', second.accountId);
  });

  it('returns null when removing an unknown account id', async () => {
    await upsertAccount('monalisa', '42');

    await expect(service.removeAccount('github.com:missing')).resolves.toBeNull();
    await expect(service.listAccounts()).resolves.toHaveLength(1);
  });
});

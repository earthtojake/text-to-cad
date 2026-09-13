import { openRegistryFixture, type RegistryFixture } from '@tooling/utils/provider-accounts';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { GITHUB_PROVIDER_ID, toGitHubAccount, upsertGitHubAccount } from './github-accounts';

describe('github account helpers', () => {
  let fixture: RegistryFixture;

  beforeEach(async () => {
    fixture = await openRegistryFixture('empty');
  });

  afterEach(() => {
    fixture?.close();
  });

  async function upsert(login: string, providerAccountId: string, host = 'github.com') {
    return upsertGitHubAccount(fixture.registry, {
      accessToken: `gho_${login}`,
      credentialSource: 'emdash_oauth',
      providerAccount: {
        providerId: 'github',
        providerAccountId,
        host,
        login,
        avatarUrl: `https://avatars.githubusercontent.com/u/${providerAccountId}`,
      },
    });
  }

  it('stores identity metadata in the row and the token behind the credentialRef', async () => {
    const { account, status } = await upsert('monalisa', '42');

    expect(status).toBe('created');
    expect(account).toMatchObject({
      accountId: 'github.com:42',
      providerAccountId: '42',
      host: 'github.com',
      login: 'monalisa',
      avatarUrl: 'https://avatars.githubusercontent.com/u/42',
      credentialSource: 'emdash_oauth',
    });
    await expect(fixture.registry.resolveSecret(GITHUB_PROVIDER_ID, 'github.com:42')).resolves.toBe(
      'gho_monalisa'
    );
  });

  it('updates an existing account instead of duplicating it', async () => {
    await upsert('monalisa', '42');
    const { account, status } = await upsert('mona', '42');

    expect(status).toBe('updated');
    expect(account).toMatchObject({ accountId: 'github.com:42', login: 'mona' });
    await expect(fixture.registry.listAccounts(GITHUB_PROVIDER_ID)).resolves.toHaveLength(1);
    await expect(fixture.registry.resolveSecret(GITHUB_PROVIDER_ID, 'github.com:42')).resolves.toBe(
      'gho_mona'
    );
  });

  it('normalizes www.github.com account hosts to github.com', async () => {
    const { account } = await upsert('monalisa', '42', 'www.github.com');

    expect(account.accountId).toBe('github.com:42');
    expect(account.host).toBe('github.com');
  });

  it('keeps accounts with the same provider account id on different hosts separate', async () => {
    const dotCom = await upsert('monalisa', '42', 'github.com');
    const enterprise = await upsert('enterprise-monalisa', '42', 'ghe.example.com');

    expect(dotCom.account.accountId).toBe('github.com:42');
    expect(enterprise.account.accountId).toBe('ghe.example.com:42');
    await expect(fixture.registry.listAccounts(GITHUB_PROVIDER_ID)).resolves.toHaveLength(2);
  });

  it('maps generic rows back to the flat GitHub shape', async () => {
    await upsert('monalisa', '42');

    const [row] = await fixture.registry.listAccounts(GITHUB_PROVIDER_ID);
    expect(toGitHubAccount(row)).toEqual({
      accountId: 'github.com:42',
      providerAccountId: '42',
      host: 'github.com',
      login: 'monalisa',
      avatarUrl: 'https://avatars.githubusercontent.com/u/42',
      credentialSource: 'emdash_oauth',
      connectedAt: row.createdAt,
      updatedAt: row.updatedAt,
    });
  });

  it('falls back to the account id convention when meta is missing', () => {
    expect(
      toGitHubAccount({
        providerId: 'github',
        accountId: 'ghe.example.com:42',
        credentialRef: 'ref',
        isDefault: false,
        meta: null,
        createdAt: 1,
        updatedAt: 2,
      })
    ).toEqual({
      accountId: 'ghe.example.com:42',
      providerAccountId: '42',
      host: 'ghe.example.com',
      login: '',
      avatarUrl: '',
      credentialSource: 'secure_storage',
      connectedAt: 1,
      updatedAt: 2,
    });
  });
});

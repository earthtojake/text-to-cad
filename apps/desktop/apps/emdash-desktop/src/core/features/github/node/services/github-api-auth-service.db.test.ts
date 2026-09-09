import { err, ok } from '@emdash/shared';
import { openRegistryFixture, type RegistryFixture } from '@tooling/utils/provider-accounts';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { GitHubApiAuthService } from '@core/features/github/api/node/services/github-api-auth-service';
import { upsertGitHubAccount } from '../accounts/github-accounts';

describe('GitHubApiAuthService', () => {
  let fixture: RegistryFixture;
  let service: GitHubApiAuthService;

  beforeEach(async () => {
    fixture = await openRegistryFixture('empty');
    service = new GitHubApiAuthService(fixture.registry);
  });

  afterEach(() => {
    fixture?.close();
  });

  async function upsertAccount({
    host = 'github.com',
    providerAccountId = '42',
    login = 'monalisa',
    token = `token-${providerAccountId}`,
  }: {
    host?: string;
    providerAccountId?: string;
    login?: string;
    token?: string;
  } = {}) {
    return (
      await upsertGitHubAccount(fixture.registry, {
        accessToken: token,
        credentialSource: 'emdash_oauth',
        providerAccount: {
          providerId: 'github',
          providerAccountId,
          host,
          login,
          avatarUrl: '',
        },
      })
    ).account;
  }

  it('uses the selected GitHub.com account token when an account id is provided', async () => {
    await upsertAccount({ providerAccountId: '42', token: 'selected-account-token' });

    await expect(service.getToken('github.com', { accountId: 'github.com:42' })).resolves.toEqual(
      ok('selected-account-token')
    );
  });

  it('uses the selected GitHub Enterprise account token when an account id is provided', async () => {
    await upsertAccount({
      host: 'ghe.example.com',
      providerAccountId: '168',
      login: 'enterprise',
      token: 'selected-ghes-account-token',
    });

    await expect(
      service.getToken('GHE.EXAMPLE.COM', {
        accountId: 'ghe.example.com:168',
      })
    ).resolves.toEqual(ok('selected-ghes-account-token'));
  });

  it('returns account not found when the selected account is missing', async () => {
    await upsertAccount({ providerAccountId: '84' });

    await expect(service.getToken('github.com', { accountId: 'github.com:42' })).resolves.toEqual(
      err({
        type: 'account_not_found',
        host: 'github.com',
        accountId: 'github.com:42',
        message: 'Selected GitHub account is no longer connected: github.com:42.',
        hint: 'Connect GitHub from account settings.',
      })
    );
  });

  it('returns account host mismatch when the selected account host does not match the requested host', async () => {
    await upsertAccount({ providerAccountId: '42' });

    await expect(
      service.getToken('ghe.example.com', { accountId: 'github.com:42' })
    ).resolves.toEqual(
      err({
        type: 'account_host_mismatch',
        host: 'ghe.example.com',
        accountId: 'github.com:42',
        accountHost: 'github.com',
        message:
          'Selected GitHub account github.com:42 is for github.com, but this repository uses ghe.example.com.',
        hint: 'Run: gh auth login --hostname ghe.example.com',
      })
    );
  });

  it('returns token missing when the selected account token is missing', async () => {
    await upsertAccount({ providerAccountId: '42' });
    fixture.secretStore.secrets.clear();

    await expect(service.getToken('github.com', { accountId: 'github.com:42' })).resolves.toEqual(
      err({
        type: 'token_missing',
        host: 'github.com',
        accountId: 'github.com:42',
        message: 'Selected GitHub account github.com:42 is missing a saved token.',
        hint: 'Connect GitHub from account settings.',
      })
    );
  });

  it('uses the default account when no account id is provided and the default host matches', async () => {
    await upsertAccount({ providerAccountId: '42', token: 'default-account-token' });

    await expect(service.getToken('www.github.com')).resolves.toEqual(ok('default-account-token'));
  });

  it('uses a default GitHub Enterprise account when no account id is provided and the host matches', async () => {
    await upsertAccount({
      host: 'ghe.example.com',
      providerAccountId: '168',
      login: 'enterprise',
      token: 'default-ghes-token',
    });

    await expect(service.getToken('ghe.example.com')).resolves.toEqual(ok('default-ghes-token'));
  });

  it('does not use the default account when no account id is provided and the host differs', async () => {
    await upsertAccount({ providerAccountId: '42' });

    await expect(service.getToken('ghe.example.com')).resolves.toEqual(
      err({
        type: 'auth_required',
        host: 'ghe.example.com',
        message:
          'GitHub Enterprise authentication required for ghe.example.com. Run: gh auth login --hostname ghe.example.com',
        hint: 'Run: gh auth login --hostname ghe.example.com',
      })
    );
  });

  it('returns a GHES login hint when no account is selected for an enterprise host', async () => {
    await expect(service.getToken('ghe.example.com')).resolves.toEqual(
      err({
        type: 'auth_required',
        host: 'ghe.example.com',
        message:
          'GitHub Enterprise authentication required for ghe.example.com. Run: gh auth login --hostname ghe.example.com',
        hint: 'Run: gh auth login --hostname ghe.example.com',
      })
    );
  });
});

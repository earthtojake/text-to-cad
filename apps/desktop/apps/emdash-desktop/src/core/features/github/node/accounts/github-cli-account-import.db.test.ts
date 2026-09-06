import { openRegistryFixture, type RegistryFixture } from '@tooling/utils/provider-accounts';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CommandRunner } from '@core/primitives/command-runner/api/command-runner';
import type { GitHubUser } from '@core/primitives/github/api';
import { GITHUB_PROVIDER_ID, upsertGitHubAccount } from './github-accounts';
import { GitHubCliAccountImportService } from './github-cli-account-import';

function makeGitHubUser(id: number, login: string): GitHubUser {
  return {
    id,
    login,
    name: login,
    email: '',
    avatar_url: `https://avatars.githubusercontent.com/u/${id}`,
  };
}

function makeExec(stdout: string): CommandRunner {
  return vi.fn().mockResolvedValue({ stdout, stderr: '' });
}

describe('GitHubCliAccountImportService', () => {
  let fixture: RegistryFixture;
  let usersByToken: Map<string, GitHubUser>;
  let getAuthenticatedUser: ReturnType<
    typeof vi.fn<(token: string, host?: string) => Promise<GitHubUser | null>>
  >;

  beforeEach(async () => {
    fixture = await openRegistryFixture('empty');
    usersByToken = new Map([
      ['gho_monalisa', makeGitHubUser(42, 'monalisa')],
      ['gho_octocat', makeGitHubUser(84, 'octocat')],
      ['ghes_enterprise', makeGitHubUser(168, 'enterprise')],
    ]);
    getAuthenticatedUser = vi.fn<(token: string, host?: string) => Promise<GitHubUser | null>>(
      async (token: string) => usersByToken.get(token) ?? null
    );
  });

  afterEach(() => {
    fixture?.close();
  });

  function makeService(stdout: string) {
    return new GitHubCliAccountImportService(fixture.registry, makeExec(stdout), {
      getAuthenticatedUser,
    });
  }

  it('imports every GitHub.com account reported by GitHub CLI as linked accounts', async () => {
    const service = makeService(
      JSON.stringify({
        hosts: {
          'github.com': [
            {
              state: 'success',
              active: true,
              host: 'github.com',
              login: 'monalisa',
              token: 'gho_monalisa',
            },
            {
              state: 'success',
              active: false,
              host: 'github.com',
              login: 'octocat',
              token: 'gho_octocat',
            },
          ],
        },
      })
    );

    const imported = await service.importAccounts();

    expect(imported.map((account) => account.accountId)).toEqual([
      'github.com:42',
      'github.com:84',
    ]);
    await expect(fixture.registry.resolveSecret(GITHUB_PROVIDER_ID, 'github.com:42')).resolves.toBe(
      'gho_monalisa'
    );
    await expect(fixture.registry.resolveSecret(GITHUB_PROVIDER_ID, 'github.com:84')).resolves.toBe(
      'gho_octocat'
    );
    await expect(fixture.registry.getDefaultAccountId(GITHUB_PROVIDER_ID)).resolves.toBe(
      'github.com:42'
    );
  });

  it('bounds the GitHub CLI status call so startup cannot hang indefinitely', async () => {
    const exec = makeExec(JSON.stringify({ hosts: {} }));
    const service = new GitHubCliAccountImportService(fixture.registry, exec, {
      getAuthenticatedUser,
    });

    await service.importAccounts();

    expect(exec).toHaveBeenCalledWith('gh', ['auth', 'status', '--json', 'hosts', '--show-token'], {
      timeout: 5_000,
    });
  });

  it('keeps existing linked accounts that are no longer reported by GitHub CLI', async () => {
    await upsertGitHubAccount(fixture.registry, {
      accessToken: 'gho_existing',
      credentialSource: 'cli',
      providerAccount: {
        providerId: 'github',
        providerAccountId: '168',
        host: 'github.com',
        login: 'hubot',
        avatarUrl: '',
      },
    });

    const service = makeService(
      JSON.stringify({
        hosts: {
          'github.com': [
            {
              state: 'success',
              active: true,
              host: 'github.com',
              login: 'monalisa',
              token: 'gho_monalisa',
            },
          ],
        },
      })
    );

    await service.importAccounts();

    await expect(fixture.registry.listAccounts(GITHUB_PROVIDER_ID)).resolves.toHaveLength(2);
    await expect(
      fixture.registry.resolveSecret(GITHUB_PROVIDER_ID, 'github.com:168')
    ).resolves.toBe('gho_existing');
  });

  it('ignores CLI entries that cannot be resolved to a GitHub user', async () => {
    usersByToken.delete('gho_octocat');
    const service = makeService(
      JSON.stringify({
        hosts: {
          'github.com': [
            {
              state: 'success',
              active: true,
              host: 'github.com',
              login: 'monalisa',
              token: 'gho_monalisa',
            },
            {
              state: 'success',
              active: false,
              host: 'github.com',
              login: 'octocat',
              token: 'gho_octocat',
            },
          ],
        },
      })
    );

    const imported = await service.importAccounts();

    expect(imported.map((account) => account.accountId)).toEqual(['github.com:42']);
    await expect(fixture.registry.listAccounts(GITHUB_PROVIDER_ID)).resolves.toHaveLength(1);
  });

  it('imports GitHub Enterprise accounts reported by GitHub CLI', async () => {
    const service = makeService(
      JSON.stringify({
        hosts: {
          'ghe.example.com': [
            {
              state: 'success',
              active: true,
              host: 'ghe.example.com',
              login: 'enterprise',
              token: 'ghes_enterprise',
            },
          ],
        },
      })
    );

    const imported = await service.importAccounts();

    expect(imported.map((account) => account.accountId)).toEqual(['ghe.example.com:168']);
    expect(getAuthenticatedUser).toHaveBeenCalledWith('ghes_enterprise', 'ghe.example.com');
    await expect(
      fixture.registry.resolveSecret(GITHUB_PROVIDER_ID, 'ghe.example.com:168')
    ).resolves.toBe('ghes_enterprise');
  });

  it('uses the CLI hosts map key as the authoritative account host', async () => {
    const service = makeService(
      JSON.stringify({
        hosts: {
          'ghe.example.com': [
            {
              state: 'success',
              active: true,
              host: 'github.com',
              login: 'enterprise',
              token: 'ghes_enterprise',
            },
          ],
        },
      })
    );

    const imported = await service.importAccounts();

    expect(imported.map((account) => account.accountId)).toEqual(['ghe.example.com:168']);
    expect(getAuthenticatedUser).toHaveBeenCalledWith('ghes_enterprise', 'ghe.example.com');
  });

  it('re-imports previously removed CLI accounts that are still logged in to gh', async () => {
    const { account } = await upsertGitHubAccount(fixture.registry, {
      accessToken: 'gho_monalisa',
      credentialSource: 'cli',
      providerAccount: {
        providerId: 'github',
        providerAccountId: '42',
        host: 'github.com',
        login: 'monalisa',
        avatarUrl: '',
      },
    });
    await fixture.registry.removeAccount(GITHUB_PROVIDER_ID, account.accountId);
    const service = makeService(
      JSON.stringify({
        hosts: {
          'github.com': [
            {
              state: 'success',
              active: true,
              host: 'github.com',
              login: 'monalisa',
              token: 'gho_monalisa',
            },
          ],
        },
      })
    );

    await expect(service.importAccounts()).resolves.toMatchObject([
      { accountId: 'github.com:42', credentialSource: 'cli' },
    ]);
    await expect(fixture.registry.listAccounts(GITHUB_PROVIDER_ID)).resolves.toHaveLength(1);
  });
});

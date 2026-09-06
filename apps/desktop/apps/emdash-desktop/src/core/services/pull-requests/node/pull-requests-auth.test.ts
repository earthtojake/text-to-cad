import { err, ok } from '@emdash/shared';
import { describe, expect, it, vi } from 'vitest';
import { createPullRequestsGitHubAuthController } from '@core/services/pull-requests/node/pull-requests-auth';

const apiBaseUrlForHost = (host: string) =>
  host === 'github.com' ? 'https://api.github.com' : `https://${host}/api/v3`;

describe('pull requests GitHub auth controller', () => {
  it('resolves identity per request, then the matching token', async () => {
    const getToken = vi.fn(async () => ok('secret-token'));
    const resolveSyncIdentity = vi.fn(async () => ok({ accountId: 'account-1' }));
    const controller = createPullRequestsGitHubAuthController(
      { getToken },
      apiBaseUrlForHost,
      resolveSyncIdentity
    );

    await expect(
      controller.call('resolveAuth', {
        repositoryUrl: 'https://GitHub.COM/emdash/emdash',
      })
    ).resolves.toEqual(
      ok({
        token: 'secret-token',
        host: 'github.com',
        apiBaseUrl: 'https://api.github.com',
        accountId: 'account-1',
      })
    );
    expect(resolveSyncIdentity).toHaveBeenCalledWith('https://GitHub.COM/emdash/emdash');
    expect(getToken).toHaveBeenCalledWith('github.com', { accountId: 'account-1' });
  });

  it('fails closed when identity resolution fails, without fetching a token', async () => {
    const error = {
      type: 'account_unresolvable' as const,
      host: 'github.com',
      message: 'The pinned GitHub account no longer exists.',
    };
    const getToken = vi.fn(async () => ok('secret-token'));
    const controller = createPullRequestsGitHubAuthController(
      { getToken },
      apiBaseUrlForHost,
      vi.fn(async () => err(error))
    );

    await expect(
      controller.call('resolveAuth', {
        repositoryUrl: 'https://github.com/emdash/emdash',
      })
    ).resolves.toEqual(err(error));
    expect(getToken).not.toHaveBeenCalled();
  });

  it('preserves typed authentication failures', async () => {
    const error = {
      type: 'account_not_found' as const,
      host: 'github.example.com',
      accountId: 'missing',
      message: 'Account not found',
      hint: 'Reconnect the account',
    };
    const controller = createPullRequestsGitHubAuthController(
      {
        getToken: vi.fn(async () => err(error)),
      },
      apiBaseUrlForHost,
      vi.fn(async () => ok({ accountId: 'missing' }))
    );

    await expect(
      controller.call('resolveAuth', {
        repositoryUrl: 'https://github.example.com/emdash/emdash',
      })
    ).resolves.toEqual(err(error));
  });
});

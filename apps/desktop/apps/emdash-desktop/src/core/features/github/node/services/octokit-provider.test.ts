import { err, ok } from '@emdash/shared';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clearOctokitCache, getOctokit } from './octokit-provider';

const mockOctokit = vi.hoisted(() => vi.fn());

vi.mock('@octokit/rest', () => ({
  Octokit: mockOctokit,
}));

const mockGetToken = vi.fn();
const authService = { getToken: mockGetToken } as never;

describe('getOctokit', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearOctokitCache();
    mockOctokit.mockImplementation(function (options) {
      return { options };
    });
  });

  it('uses api.github.com for github.com', async () => {
    mockGetToken.mockResolvedValue(ok('github-token'));

    await expect(getOctokit(authService, 'github.com')).resolves.toMatchObject({ success: true });
    expect(mockOctokit).toHaveBeenCalledWith(
      expect.objectContaining({
        auth: 'github-token',
        baseUrl: 'https://api.github.com',
        log: expect.objectContaining({ error: expect.any(Function) }),
      })
    );
  });

  it('passes the selected account context to token resolution', async () => {
    mockGetToken.mockResolvedValue(ok('selected-account-token'));

    await expect(
      getOctokit(authService, 'github.com', { accountId: 'github.com:42' })
    ).resolves.toMatchObject({
      success: true,
    });

    expect(mockGetToken).toHaveBeenCalledWith('github.com', { accountId: 'github.com:42' });
    expect(mockOctokit).toHaveBeenCalledWith(
      expect.objectContaining({
        auth: 'selected-account-token',
      })
    );
  });

  it('caches separate GitHub.com clients for separate selected accounts', async () => {
    mockGetToken
      .mockResolvedValueOnce(ok('token-a'))
      .mockResolvedValueOnce(ok('token-b'))
      .mockResolvedValueOnce(ok('token-a'));

    await getOctokit(authService, 'github.com', { accountId: 'github.com:42' });
    await getOctokit(authService, 'github.com', { accountId: 'github.com:84' });
    await getOctokit(authService, 'github.com', { accountId: 'github.com:42' });

    expect(mockOctokit).toHaveBeenCalledTimes(2);
  });

  it('clears cached clients for one selected account without evicting other accounts', async () => {
    mockGetToken
      .mockResolvedValueOnce(ok('token-a'))
      .mockResolvedValueOnce(ok('token-b'))
      .mockResolvedValueOnce(ok('token-a'))
      .mockResolvedValueOnce(ok('token-b'));

    await getOctokit(authService, 'github.com', { accountId: 'github.com:42' });
    await getOctokit(authService, 'github.com', { accountId: 'github.com:84' });
    clearOctokitCache('github.com', 'github.com:42');
    await getOctokit(authService, 'github.com', { accountId: 'github.com:42' });
    await getOctokit(authService, 'github.com', { accountId: 'github.com:84' });

    expect(mockOctokit).toHaveBeenCalledTimes(3);
  });

  it('uses the enterprise API base URL for GHES hosts', async () => {
    mockGetToken.mockResolvedValue(ok('ghes-token'));

    await expect(getOctokit(authService, 'ghe.example.com')).resolves.toMatchObject({
      success: true,
    });
    expect(mockOctokit).toHaveBeenCalledWith(
      expect.objectContaining({
        auth: 'ghes-token',
        baseUrl: 'https://ghe.example.com/api/v3',
        log: expect.objectContaining({ error: expect.any(Function) }),
      })
    );
  });

  it('forwards typed auth errors', async () => {
    mockGetToken.mockResolvedValue(
      err({ type: 'auth_required', host: 'ghe.example.com', message: 'auth required' })
    );

    await expect(getOctokit(authService, 'ghe.example.com')).resolves.toEqual({
      success: false,
      error: { type: 'auth_required', host: 'ghe.example.com', message: 'auth required' },
    });
  });
});

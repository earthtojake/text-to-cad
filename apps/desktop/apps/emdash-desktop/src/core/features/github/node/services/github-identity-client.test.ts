import { describe, expect, it, vi } from 'vitest';
import { GitHubIdentityClient } from './github-identity-client';

describe('GitHubIdentityClient', () => {
  it('reads the authenticated user with a bounded request timeout', async () => {
    const getAuthenticated = vi.fn().mockResolvedValue({
      data: {
        id: 42,
        login: 'monalisa',
        name: 'Mona Lisa',
        email: null,
        avatar_url: 'https://avatars.githubusercontent.com/u/42',
      },
    });
    const client = new GitHubIdentityClient({
      timeoutMs: 1234,
      createOctokit: () => ({
        rest: {
          users: {
            getAuthenticated,
          },
        },
      }),
    });

    await expect(client.getAuthenticatedUser('gho_token', 'ghe.example.com')).resolves.toEqual({
      id: 42,
      login: 'monalisa',
      name: 'Mona Lisa',
      email: '',
      avatar_url: 'https://avatars.githubusercontent.com/u/42',
    });
    expect(getAuthenticated).toHaveBeenCalledWith({ request: { timeout: 1234 } });
  });

  it('returns null when the token cannot identify a GitHub user', async () => {
    const client = new GitHubIdentityClient({
      createOctokit: () => ({
        rest: {
          users: {
            getAuthenticated: vi.fn().mockRejectedValue(new Error('bad credentials')),
          },
        },
      }),
    });

    await expect(client.getAuthenticatedUser('bad-token')).resolves.toBeNull();
  });
});

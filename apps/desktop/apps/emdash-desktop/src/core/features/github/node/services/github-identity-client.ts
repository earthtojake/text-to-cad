import { Octokit } from '@octokit/rest';
import { githubApiBaseUrlForHost } from '@core/features/github/api/node/services/github-api-base-url';
import type { GitHubUser } from '@core/primitives/github/api';

type OctokitUserClient = {
  rest: {
    users: {
      getAuthenticated(options: { request: { timeout: number } }): Promise<{
        data: {
          id: number;
          login: string;
          name?: string | null;
          email?: string | null;
          avatar_url: string;
        };
      }>;
    };
  };
};

type GitHubIdentityClientOptions = {
  timeoutMs?: number;
  createOctokit?: (token: string, host: string) => OctokitUserClient;
};

const DEFAULT_TIMEOUT_MS = 10_000;

export class GitHubIdentityClient {
  private readonly timeoutMs: number;
  private readonly createOctokit: (token: string, host: string) => OctokitUserClient;

  constructor(options: GitHubIdentityClientOptions = {}) {
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.createOctokit =
      options.createOctokit ??
      ((token, host) => new Octokit({ auth: token, baseUrl: githubApiBaseUrlForHost(host) }));
  }

  async getAuthenticatedUser(token: string, host = 'github.com'): Promise<GitHubUser | null> {
    try {
      const octokit = this.createOctokit(token, host);
      const { data } = await octokit.rest.users.getAuthenticated({
        request: { timeout: this.timeoutMs },
      });
      return {
        id: data.id,
        login: data.login,
        name: data.name ?? '',
        email: data.email ?? '',
        avatar_url: data.avatar_url,
      };
    } catch {
      return null;
    }
  }
}

export const githubIdentityClient = new GitHubIdentityClient();

import { err, ok, type Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import { Octokit } from '@octokit/rest';
import type {
  GitHubApiAuthContext,
  GitHubApiAuthService,
} from '@core/features/github/api/node/services/github-api-auth-service';
import { githubApiBaseUrlForHost } from '@core/features/github/api/node/services/github-api-base-url';
import { normalizeRepositoryHost } from '@core/primitives/repository/api';
import type { GitHubApiAuthError } from './github-api-auth-errors';
import { getCachedOctokit, setCachedOctokit } from './octokit-cache';

export { clearOctokitCache } from './octokit-cache';

const octokitLog = {
  debug: (...input: unknown[]) => log.debug('Octokit', { args: input }),
  info: (...input: unknown[]) => log.debug('Octokit', { args: input }),
  warn: (...input: unknown[]) => log.warn('Octokit', { args: input }),
  error: (...input: unknown[]) => log.debug('Octokit request failed', { args: input }),
};

export class GitHubApiAuthErrorException extends Error {
  constructor(readonly authError: GitHubApiAuthError) {
    super(authError.message);
    this.name = 'GitHubApiAuthErrorException';
  }
}

export async function getOctokit(
  authService: GitHubApiAuthService,
  host: string,
  context: GitHubApiAuthContext = {}
): Promise<Result<Octokit, GitHubApiAuthError>> {
  const normalizedHost = normalizeRepositoryHost(host);
  const token = await authService.getToken(normalizedHost, context);
  if (!token.success) return err(token.error);

  const cached = getCachedOctokit(normalizedHost, context);
  if (cached?.token === token.data) return ok(cached.octokit);

  const octokit = new Octokit({
    auth: token.data,
    baseUrl: githubApiBaseUrlForHost(normalizedHost),
    log: octokitLog,
  });

  setCachedOctokit(normalizedHost, context, { octokit, token: token.data });
  return ok(octokit);
}

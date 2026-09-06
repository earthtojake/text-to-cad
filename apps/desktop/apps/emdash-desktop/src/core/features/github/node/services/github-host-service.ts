import { err, ok, type Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import { Octokit } from '@octokit/rest';
import { isGitHubDotComHost, normalizeRepositoryHost } from '@core/primitives/repository/api';

const POSITIVE_TTL_MS = 15 * 60 * 1000;
const NEGATIVE_TTL_MS = 2 * 60 * 1000;
const PROBE_TIMEOUT_MS = 5_000;

export type GitHubHostProbeError =
  | { type: 'not_github'; host: string; reason?: string }
  | { type: 'host_unreachable'; host: string; reason: string }
  | { type: 'host_error'; host: string; reason: string };

export type HostProbeResult = Result<{ host: string }, GitHubHostProbeError>;

type CacheEntry = {
  result: HostProbeResult;
  expiresAt: number;
};

function ttlFor(result: HostProbeResult): number {
  return result.success ? POSITIVE_TTL_MS : NEGATIVE_TTL_MS;
}

function isTlsError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /certificate|cert|tls|ssl|self[- ]signed/i.test(message);
}

export class GitHubHostService {
  private readonly cache = new Map<string, CacheEntry>();
  private readonly inflight = new Map<string, Promise<HostProbeResult>>();

  async probe(host: string): Promise<HostProbeResult> {
    const normalizedHost = normalizeRepositoryHost(host);
    if (isGitHubDotComHost(normalizedHost)) return ok({ host: normalizedHost });

    const cached = this.cache.get(normalizedHost);
    if (cached && cached.expiresAt > Date.now()) return cached.result;

    const existing = this.inflight.get(normalizedHost);
    if (existing) return existing;

    const promise = this.doProbe(normalizedHost).then((result) => {
      this.cache.set(normalizedHost, {
        result,
        expiresAt: Date.now() + ttlFor(result),
      });
      return result;
    });
    this.inflight.set(normalizedHost, promise);
    try {
      return await promise;
    } finally {
      this.inflight.delete(normalizedHost);
    }
  }

  private async doProbe(host: string): Promise<HostProbeResult> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
    try {
      const octokit = new Octokit({ baseUrl: `https://${host}/api/v3` });
      const response = await octokit.rest.meta.get({
        request: { signal: controller.signal },
      });

      const data = response.data as unknown;
      if (data && typeof data === 'object') return ok({ host });
      return err({
        type: 'not_github',
        host,
        reason: 'meta endpoint returned non-JSON response',
      });
    } catch (error) {
      if (error && typeof error === 'object' && 'status' in error) {
        const status = Number((error as { status: unknown }).status);
        if (status === 401 || status === 403) return ok({ host });
        return status === 404
          ? err({ type: 'not_github', host, reason: 'meta endpoint returned 404' })
          : err({ type: 'host_error', host, reason: `meta endpoint returned ${status}` });
      }
      const reason = error instanceof Error ? error.message : String(error);
      const result: HostProbeResult = err({
        type: isTlsError(error) ? 'host_error' : 'host_unreachable',
        host,
        reason,
      });
      log.debug('GitHubHostService: probe failed', { host, result });
      return result;
    } finally {
      clearTimeout(timeout);
    }
  }
}

export const githubHostService = new GitHubHostService();

import type { GitHubAuthError, PullRequestError } from '../../api';

export type PullRequestOperationErrorType =
  | 'sync_failed'
  | 'refresh_failed'
  | 'checks_failed'
  | 'comments_failed'
  | 'create_failed'
  | 'merge_failed'
  | 'mark_ready_failed'
  | 'files_failed';

export function mapAuthError(error: GitHubAuthError): PullRequestError {
  switch (error.type) {
    case 'auth_required':
      return error.host === 'github.com'
        ? {
            type: 'github_auth_required',
            host: error.host,
            hint: error.hint ?? 'Connect GitHub from account settings.',
          }
        : {
            type: 'ghes_auth_required',
            host: error.host,
            hint: error.hint ?? `Run: gh auth login --hostname ${error.host}`,
          };
    case 'account_not_found':
      return {
        type: 'github_account_not_found',
        host: error.host,
        accountId: error.accountId,
        message: error.message,
      };
    case 'account_host_mismatch':
      return {
        type: 'github_account_host_mismatch',
        host: error.host,
        accountId: error.accountId,
        accountHost: error.accountHost,
        message: error.message,
      };
    case 'token_missing':
      return {
        type: 'github_token_missing',
        host: error.host,
        accountId: error.accountId,
        message: error.message,
      };
    // Fail closed (spec: github-git-settings §8): an unresolvable identity skips
    // the operation with a surfaced status — never a fallback identity.
    case 'account_unresolvable':
      return { type: 'github_account_not_found', message: error.message };
    // Explicit "no account" is intent, not an error (§7 reporting matrix); the
    // renderer shows the quiet disabled state, this status only records that
    // the sync did not run.
    case 'github_disabled':
      return { type: 'sync_failed', message: error.message };
  }
}

export function mapApiError(
  error: unknown,
  fallback: string,
  host: string,
  nameWithOwner?: string,
  operationType: PullRequestOperationErrorType = 'sync_failed'
): PullRequestError {
  if (isAbortError(error)) return { type: operationType, message: 'Operation cancelled' };
  const status = readStatus(error);
  const message = error instanceof Error ? error.message : fallback;
  if (status === 401) {
    return host === 'github.com'
      ? { type: 'github_auth_required', host, hint: 'Connect GitHub from account settings.' }
      : {
          type: 'ghes_auth_required',
          host,
          hint: `Run: gh auth login --hostname ${host}`,
        };
  }
  if (status === 404) {
    return {
      type: 'github_not_found_or_no_access',
      host,
      message: nameWithOwner
        ? `Repository ${nameWithOwner} was not found or is not accessible`
        : message,
    };
  }
  if (status === 403) {
    const resetAt = readHeader(error, 'x-ratelimit-reset');
    if (resetAt) {
      const resetTimestamp = Number(resetAt);
      return {
        type: 'github_rate_limited',
        host,
        message,
        resetAt: Number.isFinite(resetTimestamp)
          ? new Date(resetTimestamp * 1_000).toISOString()
          : undefined,
      };
    }
    const ssoUrl = readHeader(error, 'x-github-sso')?.match(/url=([^;,\s]+)/)?.[1];
    if (ssoUrl) return { type: 'github_sso_required', host, message, ssoUrl };
    return { type: 'github_forbidden', host, message };
  }
  if (isNetworkError(error)) return { type: 'host_unreachable', host, reason: message };
  return { type: operationType, message: message || fallback };
}

export function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === 'AbortError') ||
    (error instanceof Error && error.name === 'AbortError')
  );
}

function readStatus(error: unknown): number | undefined {
  return typeof error === 'object' && error !== null && 'status' in error
    ? Number((error as { status?: unknown }).status)
    : undefined;
}

function readHeader(error: unknown, key: string): string | undefined {
  if (typeof error !== 'object' || error === null || !('response' in error)) return undefined;
  const headers = (error as { response?: { headers?: Record<string, string> } }).response?.headers;
  return headers?.[key];
}

export function isNetworkError(error: unknown): boolean {
  const code =
    typeof error === 'object' && error !== null && 'code' in error
      ? String((error as { code?: unknown }).code)
      : '';
  return ['ECONNREFUSED', 'ECONNRESET', 'ENETUNREACH', 'ENOTFOUND', 'ETIMEDOUT'].includes(code);
}

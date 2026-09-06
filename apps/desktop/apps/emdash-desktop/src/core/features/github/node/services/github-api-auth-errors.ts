import { isGitHubDotComHost } from '@core/primitives/repository/api';

export type GitHubApiAuthError =
  | {
      type: 'auth_required';
      host: string;
      message: string;
      hint?: string;
    }
  | {
      type: 'account_not_found';
      host: string;
      accountId: string;
      message: string;
      hint?: string;
    }
  | {
      type: 'account_host_mismatch';
      host: string;
      accountId: string;
      accountHost: string;
      message: string;
      hint?: string;
    }
  | {
      type: 'token_missing';
      host: string;
      accountId: string;
      message: string;
      hint?: string;
    };

function authHint(host: string): string {
  return isGitHubDotComHost(host)
    ? 'Connect GitHub from account settings.'
    : `Run: gh auth login --hostname ${host}`;
}

export function githubApiAuthRequired(host: string): GitHubApiAuthError {
  if (isGitHubDotComHost(host)) {
    return {
      type: 'auth_required',
      host,
      message: 'GitHub authentication required. Connect GitHub from account settings.',
      hint: authHint(host),
    };
  }
  const hint = authHint(host);
  return {
    type: 'auth_required',
    host,
    message: `GitHub Enterprise authentication required for ${host}. ${hint}`,
    hint,
  };
}

export function githubApiAccountNotFound(host: string, accountId: string): GitHubApiAuthError {
  return {
    type: 'account_not_found',
    host,
    accountId,
    message: `Selected GitHub account is no longer connected: ${accountId}.`,
    hint: authHint(host),
  };
}

export function githubApiAccountHostMismatch(
  host: string,
  accountId: string,
  accountHost: string
): GitHubApiAuthError {
  return {
    type: 'account_host_mismatch',
    host,
    accountId,
    accountHost,
    message: `Selected GitHub account ${accountId} is for ${accountHost}, but this repository uses ${host}.`,
    hint: authHint(host),
  };
}

export function githubApiTokenMissing(host: string, accountId: string): GitHubApiAuthError {
  return {
    type: 'token_missing',
    host,
    accountId,
    message: `Selected GitHub account ${accountId} is missing a saved token.`,
    hint: authHint(host),
  };
}

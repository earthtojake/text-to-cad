import type { Err } from '@emdash/shared';
import { gitErr, type GitCommandError, type PushError } from '#runtimes/git/api';
import { ExecError } from '#services/exec/api';

export type GitFailure = Readonly<{
  exitCode: number | null;
  message: string;
  stderr: string;
  stdout: string;
}>;

/** Normalizes an expected Git process failure and rethrows every other exception. */
export function gitFailure(error: unknown): GitFailure {
  if (!(error instanceof ExecError)) throw error;
  return {
    exitCode: error.exitCode,
    message: error.stderr.trim() || error.stdout.trim() || error.message,
    stderr: error.stderr,
    stdout: error.stdout,
  };
}

export function commandFailed(error: unknown): Err<GitCommandError> {
  return commandFailure(gitFailure(error));
}

export function commandFailure(failure: GitFailure): Err<GitCommandError> {
  return gitErr.commandFailed(failure.message, failure.stderr || undefined);
}

export function pushFailed(error: unknown): Err<PushError> {
  const failure = gitFailure(error);
  const message = failure.message.toLowerCase();
  if (message.includes('no upstream')) return gitErr.noUpstream(failure.message);
  if (
    message.includes('no configured push destination') ||
    message.includes('no remote configured') ||
    message.includes('no remote')
  ) {
    return gitErr.noRemote(failure.message);
  }
  if (isAuthRequired(failure)) return gitErr.authRequired(failure.message);
  if (isAuthFailed(failure)) return gitErr.authFailed(failure.message);
  if (isNetworkFailure(failure)) return gitErr.networkError(failure.message);
  if (
    message.includes('repository not found') ||
    message.includes('does not appear to be a git repository')
  ) {
    return gitErr.remoteNotFound(failure.message);
  }
  if (message.includes('hook declined') || message.includes('pre-receive hook')) {
    return gitErr.hookRejected(failure.message);
  }
  if (message.includes('rejected') || message.includes('non-fast-forward')) {
    return gitErr.rejected(failure.message);
  }
  return commandFailure(failure);
}

export function isAuthRequired(failure: GitFailure): boolean {
  const message = failure.message.toLowerCase();
  return (
    message.includes('could not read username') ||
    message.includes('authentication failed') ||
    message.includes('permission denied (publickey') ||
    message.includes('terminal prompts disabled') ||
    message.includes('the requested url returned error: 401') ||
    message.includes('the requested url returned error: 403') ||
    /\bhttp\s+(401|403)\b/.test(message)
  );
}

export function isAuthFailed(failure: GitFailure): boolean {
  const message = failure.message.toLowerCase();
  return message.includes('authentication') || message.includes('permission denied');
}

export function isNetworkFailure(failure: GitFailure): boolean {
  const message = failure.message.toLowerCase();
  return (
    message.includes('could not resolve host') ||
    message.includes('network is unreachable') ||
    message.includes('connection refused') ||
    message.includes('connection timed out') ||
    message.includes('no route to host') ||
    message.includes('network is down') ||
    message.includes('could not resolve hostname') ||
    message.includes('temporary failure in name resolution') ||
    message.includes('name or service not known') ||
    message.includes('ssh: connect to host') ||
    message.includes('unable to connect')
  );
}

export function isMissingObject(failure: GitFailure): boolean {
  if (failure.exitCode !== 128) return false;
  const message = failure.message.toLowerCase();
  return (
    message.includes('does not exist in') ||
    message.includes('does not exist (neither on disk nor in the index)') ||
    message.includes('invalid object name') ||
    message.includes('not a valid object name')
  );
}

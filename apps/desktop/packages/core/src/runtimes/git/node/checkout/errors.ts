import type { Err } from '@emdash/shared';
import type { PortableRelativePath } from '#primitives/path/api';
import { gitErr, type CommitError, type GitCommandError, type PullError } from '#runtimes/git/api';
import {
  commandFailed,
  commandFailure,
  gitFailure,
  isAuthFailed,
  isAuthRequired,
  isNetworkFailure,
} from '#runtimes/git/node/exec/errors';

export class InvalidCheckoutPathError extends Error {
  override readonly name = 'InvalidCheckoutPathError';

  constructor(readonly filePath: string) {
    super(`Path is outside checkout: ${filePath}`);
  }
}

export const checkoutFailures = {
  command(error: unknown): Err<GitCommandError> {
    if (error instanceof InvalidCheckoutPathError) {
      return gitErr.commandFailed(error.message);
    }
    return commandFailed(error);
  },

  commit(error: unknown): Err<CommitError> {
    const failure = gitFailure(error);
    const message = failure.message.toLowerCase();
    if (message.includes('nothing to commit')) return gitErr.nothingToCommit(failure.message);
    if (message.includes('empty commit message')) return gitErr.emptyMessage(failure.message);
    if (message.includes('hook')) return gitErr.hookFailed(failure.message);
    return commandFailure(failure);
  },

  pull(error: unknown, conflictedFiles?: PortableRelativePath[]): Err<PullError> {
    const failure = gitFailure(error);
    const message = failure.message.toLowerCase();
    if (message.includes('conflict')) return gitErr.conflict(failure.message, conflictedFiles);
    if (
      message.includes('there is no tracking information') ||
      message.includes('no tracking information') ||
      message.includes('has no upstream branch') ||
      message.includes('no upstream configured')
    ) {
      return gitErr.noUpstream(failure.message);
    }
    if (
      message.includes('need to specify how to reconcile') ||
      message.includes('you have divergent branches')
    ) {
      return gitErr.diverged(failure.message);
    }
    if (isAuthRequired(failure)) return gitErr.authRequired(failure.message);
    if (isAuthFailed(failure)) return gitErr.authFailed(failure.message);
    if (isNetworkFailure(failure)) return gitErr.networkError(failure.message);
    return commandFailure(failure);
  },

  isUnbornHead(error: unknown): boolean {
    const message = gitFailure(error).message.toLowerCase();
    return (
      message.includes("ambiguous argument 'head'") ||
      message.includes('unknown revision') ||
      message.includes('needed a single revision') ||
      message.includes('does not have any commits yet')
    );
  },

  isDetachedHead(error: unknown): boolean {
    const failure = gitFailure(error);
    return (
      failure.exitCode === 128 &&
      failure.message.toLowerCase().includes('ref head is not a symbolic ref')
    );
  },

  isUnknownRevision(error: unknown): boolean {
    const failure = gitFailure(error);
    if (failure.exitCode !== 128) return false;
    const message = failure.message.toLowerCase();
    return (
      message.includes('ambiguous argument') ||
      message.includes('unknown revision') ||
      message.includes('bad object') ||
      message.includes('not a valid object name')
    );
  },

  isPathNotMatched(error: unknown): boolean {
    return gitFailure(error).message.includes('did not match any files');
  },

  isMissingIndexEntry(error: unknown): boolean {
    const failure = gitFailure(error);
    return (
      failure.exitCode === 128 &&
      failure.message.toLowerCase().includes('does not exist (neither on disk nor in the index)')
    );
  },
} as const;

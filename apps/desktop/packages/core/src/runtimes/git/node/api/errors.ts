import { gitErr, type GitCommandError } from '#runtimes/git/api';
import { GitResolutionException } from '#runtimes/git/node/allocation/allocation-graph';
import { InvalidCheckoutPathError } from '#runtimes/git/node/checkout/errors';
import { commandFailed } from '#runtimes/git/node/exec/errors';
import { ExecError } from '#services/exec/api';

/** Converts only failures that the Git contract explicitly treats as operational errors. */
export function expectedGitCommandError(error: unknown): GitCommandError | undefined {
  if (error instanceof GitResolutionException) {
    return gitErr.resolutionFailed(error.resolution.path, error.resolution.message).error;
  }
  if (error instanceof InvalidCheckoutPathError) {
    return gitErr.commandFailed(error.message).error;
  }
  if (error instanceof ExecError) return commandFailed(error).error;
  return undefined;
}

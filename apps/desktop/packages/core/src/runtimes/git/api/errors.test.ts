import { describe, expect, it } from 'vitest';
import { parseAbsolute } from '#primitives/path/api';
import {
  fetchPrForReviewErrorSchema,
  gitCommandErrorSchema,
  gitResolutionErrorSchema,
} from '#runtimes/git/api/errors';
import { gitErr } from './errors';

describe('gitErr', () => {
  it('constructs command failures accepted by the public schema', () => {
    const result = gitErr.commandFailed('command failed', 'fatal: command failed');

    expect(result).toEqual({
      success: false,
      error: {
        type: 'git_error',
        message: 'command failed',
        stderr: 'fatal: command failed',
      },
    });
    expect(gitCommandErrorSchema.parse(result.error)).toEqual(result.error);
  });

  it('constructs stale ref updates as typed Git execution failures', () => {
    const result = gitErr.staleRefUpdate(
      "cannot lock ref 'refs/remotes/origin/main': is at bbbb but expected aaaa"
    );

    expect(result).toEqual({
      success: false,
      error: {
        type: 'git_error',
        code: 'stale_ref_update',
        message: "cannot lock ref 'refs/remotes/origin/main': is at bbbb but expected aaaa",
      },
    });
    expect(gitCommandErrorSchema.parse(result.error)).toEqual(result.error);
  });

  it('constructs operation-specific not-found failures without conflating their shapes', () => {
    const pullRequest = gitErr.prNotFound(42, 'pull request not found').error;

    expect(fetchPrForReviewErrorSchema.parse(pullRequest)).toEqual(pullRequest);
  });

  it('keeps selector resolution failures distinct from Git process failures', () => {
    const path = parseAbsolute('/workspace');
    if (!path.success) throw new Error(path.error.message);
    const result = gitErr.resolutionFailed(path.data, 'not a Git checkout');

    expect(gitResolutionErrorSchema.parse(result.error)).toEqual(result.error);
    expect(gitCommandErrorSchema.parse(result.error)).toEqual(result.error);
  });
});

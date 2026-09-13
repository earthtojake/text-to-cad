import { describe, expect, it } from 'vitest';
import { hostPath } from '#runtimes/git/node/testing/paths';
import { ExecError } from '#services/exec/api';
import { repositoryFailures } from './errors';

function execError(stderr: string, exitCode = 128): ExecError {
  return new ExecError('git', ['test'], exitCode, '', stderr);
}

describe('repository failures', () => {
  it('maps repository operation failures to their declared variants', () => {
    expect(
      repositoryFailures.clone(
        execError("fatal: destination path 'repo' already exists and is not an empty directory."),
        hostPath('/tmp/repo')
      )
    ).toMatchObject({
      success: false,
      error: { type: 'target_exists', path: hostPath('/tmp/repo') },
    });

    expect(
      repositoryFailures.fetch(
        execError('fatal: unable to access: Could not resolve host'),
        'origin'
      )
    ).toMatchObject({ success: false, error: { type: 'network_error' } });

    expect(
      repositoryFailures.clone(
        execError('fatal: unable to access: Could not resolve host'),
        hostPath('/tmp/repo')
      )
    ).toMatchObject({ success: false, error: { type: 'network_error' } });

    expect(
      repositoryFailures.clone(
        execError(
          "fatal: could not read Username for 'https://github.com': terminal prompts disabled"
        ),
        hostPath('/tmp/repo')
      )
    ).toMatchObject({ success: false, error: { type: 'auth_required' } });

    expect(
      repositoryFailures.clone(
        execError("fatal: repository 'https://github.com/acme/missing.git/' not found"),
        hostPath('/tmp/repo')
      )
    ).toMatchObject({ success: false, error: { type: 'remote_not_found' } });

    expect(
      repositoryFailures.fetchPrForReview(
        execError("fatal: couldn't find remote ref refs/pull/42/head"),
        42
      )
    ).toMatchObject({ success: false, error: { type: 'not_found', prNumber: 42 } });
  });

  it.each([
    'error: fetching ref refs/remotes/origin/main failed: incorrect old value provided',
    "cannot lock ref 'refs/remotes/origin/main': is at bbbb but expected aaaa",
  ])('classifies stale ref updates at the Git process boundary: %s', (stderr) => {
    expect(repositoryFailures.fetch(execError(stderr), 'origin')).toEqual({
      success: false,
      error: {
        type: 'git_error',
        code: 'stale_ref_update',
        message: stderr,
        stderr,
      },
    });
  });

  it('keeps unrelated lock-file failures as generic Git errors', () => {
    const stderr =
      "cannot lock ref 'refs/remotes/origin/main': Unable to create 'main.lock': File exists";

    expect(repositoryFailures.fetch(execError(stderr), 'origin')).toEqual({
      success: false,
      error: {
        type: 'git_error',
        message: stderr,
        stderr,
      },
    });
  });

  it('rethrows failures that did not come from Git execution', () => {
    const bug = new TypeError('classifier bug');
    expect(() => repositoryFailures.fetch(bug, 'origin')).toThrow(bug);
  });
});

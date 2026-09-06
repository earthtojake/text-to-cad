import { describe, expect, it } from 'vitest';
import { ExecError } from '#services/exec/api';
import { gitFailure, isMissingObject, pushFailed } from './errors';

function execError(stderr: string, exitCode = 128, stdout = ''): ExecError {
  return new ExecError('git', ['test'], exitCode, stdout, stderr);
}

describe('Git execution errors', () => {
  it('normalizes only process failures', () => {
    expect(gitFailure(execError('fatal: failed', 1, 'fallback'))).toEqual({
      exitCode: 1,
      message: 'fatal: failed',
      stderr: 'fatal: failed',
      stdout: 'fallback',
    });

    const bug = new TypeError('executor bug');
    expect(() => gitFailure(bug)).toThrow(bug);
  });

  it.each([
    'fatal: could not read Username for https://github.com: terminal prompts disabled',
    'git@github.com: Permission denied (publickey).',
    'fatal: unable to access url: The requested URL returned error: 401',
    'fatal: unable to access url: The requested URL returned error: 403',
  ])('maps credential failures to auth_required: %s', (message) => {
    expect(pushFailed(execError(message))).toMatchObject({
      success: false,
      error: { type: 'auth_required' },
    });
  });

  it('distinguishes missing objects from other command failures', () => {
    expect(
      isMissingObject(gitFailure(execError("fatal: path 'file' does not exist in 'HEAD'")))
    ).toBe(true);
    expect(isMissingObject(gitFailure(execError("fatal: invalid object name 'missing'.")))).toBe(
      true
    );
    expect(isMissingObject(gitFailure(execError('fatal: Not a valid object name HEAD:file')))).toBe(
      true
    );
    expect(isMissingObject(gitFailure(execError('fatal: permission denied')))).toBe(false);
    expect(
      isMissingObject(gitFailure(execError("fatal: path 'file' does not exist in 'HEAD'", 1)))
    ).toBe(false);
  });

  it('preserves hook rejection as the more specific push failure', () => {
    expect(pushFailed(execError('remote rejected: pre-receive hook declined'))).toMatchObject({
      success: false,
      error: { type: 'hook_rejected' },
    });
  });

  it('maps missing push repositories at the Git process boundary', () => {
    expect(
      pushFailed(
        execError(
          "remote: Repository not found.\nfatal: repository 'https://github.com/x/y' not found"
        )
      )
    ).toMatchObject({
      success: false,
      error: { type: 'remote_not_found' },
    });
  });
});

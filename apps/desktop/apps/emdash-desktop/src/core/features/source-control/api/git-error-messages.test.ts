import { describe, expect, it } from 'vitest';
import { hostPathFromNative } from '@core/primitives/desktop-runtime/api';
import {
  formatCloneErrorDetail,
  formatFetchErrorDetail,
  formatPullErrorDetail,
  formatPushErrorDetail,
} from './git-error-messages';

describe('formatCloneErrorDetail', () => {
  it('formats authentication failures on an SSH host', () => {
    expect(
      formatCloneErrorDetail(
        {
          type: 'auth_required',
          message:
            "fatal: could not read Username for 'https://github.com': terminal prompts disabled",
        },
        { isSshProject: true }
      )
    ).toBe('Git is not authenticated on the remote.');
  });

  it('formats clone destination paths', () => {
    expect(
      formatCloneErrorDetail({
        type: 'target_exists',
        path: hostPathFromNative('/remote/repo'),
        message: 'fatal: destination path already exists',
      })
    ).toBe('Clone destination is not empty: /remote/repo');
  });
});

describe('formatFetchErrorDetail', () => {
  it('formats missing local authentication', () => {
    expect(formatFetchErrorDetail({ type: 'auth_required', message: 'auth required' })).toBe(
      'Git is not authenticated.'
    );
  });

  it('formats failed authentication on an SSH host', () => {
    expect(
      formatFetchErrorDetail(
        { type: 'auth_failed', message: 'git@github.com: Permission denied (publickey).' },
        { isSshProject: true }
      )
    ).toBe('Git authentication failed on the remote.');
  });

  it('formats network and repository access failures', () => {
    expect(
      formatFetchErrorDetail(
        { type: 'network_error', message: 'fatal: could not resolve host' },
        { isSshProject: true }
      )
    ).toBe('Cannot reach the repository from the remote.');
    expect(
      formatFetchErrorDetail({ type: 'remote_not_found', message: 'repository not found' })
    ).toBe('Repository not found or inaccessible.');
  });
});

describe('formatPushErrorDetail', () => {
  it('formats typed repository and authentication failures', () => {
    expect(
      formatPushErrorDetail({ type: 'remote_not_found', message: 'repository not found' })
    ).toBe('Repository not found or inaccessible.');
    expect(formatPushErrorDetail({ type: 'auth_required', message: 'auth required' })).toBe(
      'Git is not authenticated.'
    );
  });

  it('preserves unrelated Git errors', () => {
    const message = 'Updates were rejected because the remote contains work.';
    expect(formatPushErrorDetail({ type: 'rejected', message })).toBe(message);
  });
});

describe('formatPullErrorDetail', () => {
  it('formats typed pull failures', () => {
    expect(formatPullErrorDetail({ type: 'no_upstream', message: 'no upstream' })).toBe(
      'No upstream branch is configured.'
    );
    expect(formatPullErrorDetail({ type: 'diverged', message: 'branches diverged' })).toBe(
      'Local and remote branches have diverged.'
    );
  });
});

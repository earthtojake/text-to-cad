import { describe, expect, it } from 'vitest';
import type { GitBranchRef } from './types';
import { resolveBaseRefFromRemoteDefault } from './utils';

const origin = { name: 'origin', url: 'git@github.com:example/repo.git' };
const fork = { name: 'fork', url: 'git@github.com:user/repo.git' };

const branches: GitBranchRef[] = [
  { type: 'local', branch: 'feature/current' },
  { type: 'local', branch: 'develop' },
  { type: 'remote', branch: 'main', remote: origin },
  { type: 'remote', branch: 'develop', remote: origin },
  { type: 'remote', branch: 'main', remote: fork },
];

describe('resolveBaseRefFromRemoteDefault', () => {
  it('replaces a detected feature baseRef with the remote default when it exists', () => {
    expect(
      resolveBaseRefFromRemoteDefault({
        detectedBaseRef: 'origin/feature/current',
        gitDefaultBranch: 'main',
        branches,
      })
    ).toBe('origin/main');
  });

  it('keeps the detected baseRef when the remote default does not exist', () => {
    expect(
      resolveBaseRefFromRemoteDefault({
        detectedBaseRef: 'origin/feature/current',
        gitDefaultBranch: 'release',
        branches,
      })
    ).toBe('origin/feature/current');
  });

  it('keeps the detected baseRef when no remote default is known', () => {
    expect(
      resolveBaseRefFromRemoteDefault({
        detectedBaseRef: 'origin/feature/current',
        branches,
      })
    ).toBe('origin/feature/current');
  });
});

import type { GitBranchRef } from '@emdash/core/runtimes/git/api';
import { describe, expect, it } from 'vitest';
import { resolveInitialBaseBranch, toShortBranchName } from './base-branch';

const originRemote = { name: 'origin', url: 'git@github.com:owner/repo.git' };
const upstreamRemote = { name: 'upstream', url: 'git@github.com:upstream/repo.git' };

describe('toShortBranchName', () => {
  it('keeps exact branch names unchanged', () => {
    const branches: GitBranchRef[] = [{ type: 'local', branch: 'feature/api-cleanup' }];

    expect(toShortBranchName('feature/api-cleanup', branches)).toBe('feature/api-cleanup');
  });

  it('strips known remote prefixes from base refs', () => {
    const branches: GitBranchRef[] = [
      { type: 'remote', remote: originRemote, branch: 'main' },
      { type: 'local', branch: 'main' },
    ];

    expect(toShortBranchName('origin/main', branches)).toBe('main');
  });
});

describe('resolveInitialBaseBranch', () => {
  it('prefers the task source branch when it exists', () => {
    const branches: GitBranchRef[] = [
      { type: 'remote', remote: originRemote, branch: 'main' },
      { type: 'local', branch: 'release/v2' },
      { type: 'local', branch: 'main' },
    ];
    const defaultBranch: GitBranchRef = { type: 'local', branch: 'main' };

    expect(
      resolveInitialBaseBranch(
        branches,
        { type: 'local', branch: 'release/v2' },
        defaultBranch,
        'origin'
      )
    ).toEqual({
      type: 'local',
      branch: 'release/v2',
    });
  });

  it('preserves the source branch remote when multiple remotes share the branch name', () => {
    const branches: GitBranchRef[] = [
      { type: 'remote', remote: originRemote, branch: 'main' },
      { type: 'remote', remote: upstreamRemote, branch: 'main' },
    ];
    const defaultBranch: GitBranchRef = { type: 'remote', remote: originRemote, branch: 'main' };

    expect(
      resolveInitialBaseBranch(
        branches,
        { type: 'remote', remote: upstreamRemote, branch: 'main' },
        defaultBranch,
        'upstream'
      )
    ).toEqual({
      type: 'remote',
      remote: upstreamRemote,
      branch: 'main',
    });
  });

  it('falls back to repository default branch when preferred branch is unavailable', () => {
    const branches: GitBranchRef[] = [{ type: 'remote', remote: originRemote, branch: 'main' }];
    const defaultBranch: GitBranchRef = { type: 'remote', remote: originRemote, branch: 'main' };

    expect(
      resolveInitialBaseBranch(
        branches,
        { type: 'local', branch: 'release/v2' },
        defaultBranch,
        'origin'
      )
    ).toEqual({
      type: 'remote',
      remote: originRemote,
      branch: 'main',
    });
  });

  it('returns undefined when no preferred branch and no default branch', () => {
    const branches: GitBranchRef[] = [{ type: 'remote', remote: originRemote, branch: 'main' }];

    expect(resolveInitialBaseBranch(branches, undefined, undefined, 'origin')).toBeUndefined();
  });
});

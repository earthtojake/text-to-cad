import { describe, expect, it } from 'vitest';
import type { GitBranchRef } from '@core/primitives/git/api';
import { filterBranchesForPicker, prioritizeExactBranchMatches } from './branch-selector-utils';

const origin = { name: 'origin', url: 'git@github.com:example/repo.git' };
const upstream = { name: 'upstream', url: 'git@github.com:example/upstream.git' };

const branches: GitBranchRef[] = [
  { type: 'local', branch: 'main' },
  { type: 'local', branch: 'feature/local' },
  { type: 'remote', branch: 'main', remote: origin },
  { type: 'remote', branch: 'feature/origin', remote: origin },
  { type: 'remote', branch: 'main', remote: upstream },
  { type: 'remote', branch: 'feature/upstream', remote: upstream },
];

describe('filterBranchesForPicker', () => {
  it('returns local branches without applying a remote filter', () => {
    expect(filterBranchesForPicker(branches, 'local', 'upstream')).toEqual([
      { type: 'local', branch: 'main' },
      { type: 'local', branch: 'feature/local' },
    ]);
  });

  it('filters remote branches to the selected remote', () => {
    expect(filterBranchesForPicker(branches, 'remote', 'upstream')).toEqual([
      { type: 'remote', branch: 'main', remote: upstream },
      { type: 'remote', branch: 'feature/upstream', remote: upstream },
    ]);
  });

  it('keeps all remote branches when no remote filter is provided', () => {
    expect(filterBranchesForPicker(branches, 'remote')).toEqual([
      { type: 'remote', branch: 'main', remote: origin },
      { type: 'remote', branch: 'feature/origin', remote: origin },
      { type: 'remote', branch: 'main', remote: upstream },
      { type: 'remote', branch: 'feature/upstream', remote: upstream },
    ]);
  });
});

describe('prioritizeExactBranchMatches', () => {
  it('moves exact branch-name matches before partial matches', () => {
    const matchingBranches: GitBranchRef[] = [
      { type: 'local', branch: 'feature/main' },
      { type: 'local', branch: 'main' },
      { type: 'local', branch: 'maintenance/main' },
    ];

    expect(prioritizeExactBranchMatches(matchingBranches, 'main')).toEqual([
      { type: 'local', branch: 'main' },
      { type: 'local', branch: 'feature/main' },
      { type: 'local', branch: 'maintenance/main' },
    ]);
  });

  it('treats remote branch names as exact matches even when labels include the remote', () => {
    const matchingBranches: GitBranchRef[] = [
      { type: 'remote', branch: 'feature/main', remote: origin },
      { type: 'remote', branch: 'main', remote: origin },
    ];

    expect(prioritizeExactBranchMatches(matchingBranches, 'main')).toEqual([
      { type: 'remote', branch: 'main', remote: origin },
      { type: 'remote', branch: 'feature/main', remote: origin },
    ]);
  });

  it('moves exact remote-label matches before partial matches', () => {
    const matchingBranches: GitBranchRef[] = [
      { type: 'remote', branch: 'feature/origin-main', remote: origin },
      { type: 'remote', branch: 'main', remote: origin },
    ];

    expect(prioritizeExactBranchMatches(matchingBranches, 'origin/main')).toEqual([
      { type: 'remote', branch: 'main', remote: origin },
      { type: 'remote', branch: 'feature/origin-main', remote: origin },
    ]);
  });

  it('preserves branch order when there is no search query', () => {
    expect(prioritizeExactBranchMatches(branches, '  ')).toEqual(branches);
  });
});

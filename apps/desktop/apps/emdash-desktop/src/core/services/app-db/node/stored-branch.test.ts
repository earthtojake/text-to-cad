import { describe, expect, it } from 'vitest';
import type { GitBranchRef } from '@core/primitives/git/api';
import { fromStoredBranch, toStoredBranch } from './stored-branch';

describe('stored-branch', () => {
  it('serializes and deserializes local branches', () => {
    const branch: GitBranchRef = { type: 'local', branch: 'main' };
    const persisted = toStoredBranch(branch);
    expect(persisted).toBe(JSON.stringify({ type: 'local', branch: 'main' }));
    expect(fromStoredBranch(persisted)).toEqual(branch);
  });

  it('serializes and deserializes remote branches', () => {
    const branch: GitBranchRef = {
      type: 'remote',
      branch: 'main',
      remote: { name: 'origin', url: 'git@github.com:owner/repo.git' },
    };
    const persisted = toStoredBranch(branch);
    expect(persisted).toBe(
      JSON.stringify({
        type: 'remote',
        branch: 'main',
        remote: { name: 'origin', url: 'git@github.com:owner/repo.git' },
      })
    );
    expect(fromStoredBranch(persisted)).toEqual(branch);
  });

  it('deserializes historical raw branch strings', () => {
    expect(fromStoredBranch('main')).toEqual({ type: 'local', branch: 'main' });
    expect(fromStoredBranch('felix/edu-2408-videos-added-to-lessons-dont-work-in-app')).toEqual({
      type: 'local',
      branch: 'felix/edu-2408-videos-added-to-lessons-dont-work-in-app',
    });
  });

  it('deserializes historical JSON string branch values', () => {
    expect(fromStoredBranch('"main"')).toEqual({ type: 'local', branch: 'main' });
  });

  it('treats valid JSON primitives as historical raw branch strings', () => {
    expect(fromStoredBranch('123')).toEqual({ type: 'local', branch: '123' });
  });

  it('returns undefined for null, undefined, and empty string', () => {
    expect(fromStoredBranch(null)).toBeUndefined();
    expect(fromStoredBranch(undefined)).toBeUndefined();
    expect(fromStoredBranch('')).toBeUndefined();
  });

  it('returns undefined for literal JSON null', () => {
    expect(fromStoredBranch('null')).toBeUndefined();
  });
});

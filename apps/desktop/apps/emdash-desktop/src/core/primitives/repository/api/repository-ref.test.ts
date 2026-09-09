import { describe, expect, it } from 'vitest';
import {
  isGitHubDotComHost,
  parseRepositoryRef,
  parseRepositoryRefResult,
  splitNameWithOwner,
} from './repository-ref';

describe('parseRepositoryRef', () => {
  it('parses bare owner/repo only with an explicit default host', () => {
    expect(parseRepositoryRef('owner/repo')).toBeNull();
    expect(parseRepositoryRef('owner/repo', { defaultHost: 'github.com' })).toEqual({
      host: 'github.com',
      owner: 'owner',
      repo: 'repo',
      nameWithOwner: 'owner/repo',
      repositoryUrl: 'https://github.com/owner/repo',
    });
  });

  it('parses GitHub remotes to a canonical HTTPS URL', () => {
    const expected = {
      host: 'github.com',
      owner: 'owner',
      repo: 'repo',
      nameWithOwner: 'owner/repo',
      repositoryUrl: 'https://github.com/owner/repo',
    };

    expect(parseRepositoryRef('https://github.com/owner/repo')).toEqual(expected);
    expect(parseRepositoryRef('https://www.github.com/owner/repo.git')).toEqual(expected);
    expect(parseRepositoryRef('git@github.com:owner/repo.git')).toEqual(expected);
  });

  it('parses non-GitHub remotes structurally without asserting provider compatibility', () => {
    expect(parseRepositoryRef('git@gitlab.com:owner/repo.git')).toEqual({
      host: 'gitlab.com',
      owner: 'owner',
      repo: 'repo',
      nameWithOwner: 'owner/repo',
      repositoryUrl: 'https://gitlab.com/owner/repo',
    });
  });

  it('preserves HTTPS ports and ignores SSH ports for canonical URLs', () => {
    expect(parseRepositoryRef('https://ghe.example.com:8443/owner/repo.git')).toEqual({
      host: 'ghe.example.com:8443',
      owner: 'owner',
      repo: 'repo',
      nameWithOwner: 'owner/repo',
      repositoryUrl: 'https://ghe.example.com:8443/owner/repo',
    });

    expect(parseRepositoryRef('ssh://git@ghe.example.com:2222/owner/repo.git')).toEqual({
      host: 'ghe.example.com',
      owner: 'owner',
      repo: 'repo',
      nameWithOwner: 'owner/repo',
      repositoryUrl: 'https://ghe.example.com/owner/repo',
    });
  });

  it('preserves www prefixes for non-github.com hosts', () => {
    expect(parseRepositoryRef('https://www.ghe.example.com/owner/repo')?.host).toBe(
      'www.ghe.example.com'
    );
  });

  it('supports nested owners for non-GitHub forges', () => {
    expect(parseRepositoryRef('https://gitlab.com/group/subgroup/repo.git')).toEqual({
      host: 'gitlab.com',
      owner: 'group/subgroup',
      repo: 'repo',
      nameWithOwner: 'group/subgroup/repo',
      repositoryUrl: 'https://gitlab.com/group/subgroup/repo',
    });
  });

  it('returns null for malformed values', () => {
    expect(parseRepositoryRef('owner')).toBeNull();
    expect(parseRepositoryRef('')).toBeNull();
  });
});

describe('isGitHubDotComHost', () => {
  it('normalizes github.com host aliases', () => {
    expect(isGitHubDotComHost('github.com')).toBe(true);
    expect(isGitHubDotComHost('www.github.com')).toBe(true);
    expect(isGitHubDotComHost('ghe.example.com')).toBe(false);
  });
});

describe('splitNameWithOwner', () => {
  it('splits canonical owner/repo', () => {
    expect(splitNameWithOwner('owner/repo')).toEqual({ owner: 'owner', repo: 'repo' });
  });

  it('rejects URLs because callers must pass canonical owner/repo', () => {
    expect(() => splitNameWithOwner('https://github.com/owner/repo')).toThrow(
      'Invalid nameWithOwner'
    );
  });
});

describe('parseRepositoryRefResult', () => {
  it('returns a typed result for valid and invalid inputs', () => {
    expect(parseRepositoryRefResult('https://github.com/owner/repo')).toEqual({
      success: true,
      data: {
        host: 'github.com',
        owner: 'owner',
        repo: 'repo',
        nameWithOwner: 'owner/repo',
        repositoryUrl: 'https://github.com/owner/repo',
      },
    });

    expect(parseRepositoryRefResult('owner/repo')).toEqual({
      success: false,
      error: {
        type: 'invalid-repository-ref',
        input: 'owner/repo',
      },
    });
  });
});

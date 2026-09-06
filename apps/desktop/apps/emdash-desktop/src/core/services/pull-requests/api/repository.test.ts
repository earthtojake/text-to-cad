import { describe, expect, it } from 'vitest';
import { recognizePullRequestUrl } from './repository';

describe('recognizePullRequestUrl', () => {
  it('recognizes the gh CLI convention (refs/pull/N/head + https remote)', () => {
    expect(
      recognizePullRequestUrl({
        mergeRef: 'refs/pull/123/head',
        remoteUrl: 'https://github.com/emdash/emdash.git',
      })
    ).toBe('https://github.com/emdash/emdash/pull/123');
  });

  it('normalizes scp-style ssh remotes to the canonical repository URL', () => {
    expect(
      recognizePullRequestUrl({
        mergeRef: 'refs/pull/7/head',
        remoteUrl: 'git@github.com:emdash/emdash.git',
      })
    ).toBe('https://github.com/emdash/emdash/pull/7');
  });

  it('returns null for ordinary branch mergeRefs', () => {
    expect(
      recognizePullRequestUrl({
        mergeRef: 'refs/heads/feature',
        remoteUrl: 'https://github.com/emdash/emdash',
      })
    ).toBeNull();
  });

  it('returns null for merge-request style refs it does not recognize', () => {
    expect(
      recognizePullRequestUrl({
        mergeRef: 'refs/merge-requests/9/head',
        remoteUrl: 'https://gitlab.com/emdash/emdash',
      })
    ).toBeNull();
  });

  it('returns null without a resolvable remote URL', () => {
    expect(recognizePullRequestUrl({ mergeRef: 'refs/pull/1/head', remoteUrl: null })).toBeNull();
    expect(
      recognizePullRequestUrl({ mergeRef: 'refs/pull/1/head', remoteUrl: 'not a remote' })
    ).toBeNull();
    expect(recognizePullRequestUrl(null)).toBeNull();
  });

  it('rejects malformed pull numbers', () => {
    expect(
      recognizePullRequestUrl({
        mergeRef: 'refs/pull/12x/head',
        remoteUrl: 'https://github.com/emdash/emdash',
      })
    ).toBeNull();
  });
});

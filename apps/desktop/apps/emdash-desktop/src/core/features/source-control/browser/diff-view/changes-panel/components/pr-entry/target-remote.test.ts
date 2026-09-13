import type { GitRemote } from '@emdash/core/runtimes/git/api';
import { describe, expect, it } from 'vitest';
import { getTargetRemotes, resolveCreatePrTargetRemote } from './target-remote';

const remotes: GitRemote[] = [
  { name: 'origin', url: 'git@github.com:user/repo.git' },
  { name: 'upstream', url: 'git@github.com:org/repo.git' },
  { name: 'gitlab', url: 'git@gitlab.com:user/repo.git' },
];

describe('getTargetRemotes', () => {
  it('returns structurally parseable remotes matching the requested host', () => {
    expect(
      getTargetRemotes(remotes, { host: 'github.com' }).map((option) => option.remote.name)
    ).toEqual(['origin', 'upstream']);
  });
});

describe('resolveCreatePrTargetRemote', () => {
  const options = getTargetRemotes(remotes, { host: 'github.com' });

  it('defaults to the project remote when it is a GitHub remote', () => {
    expect(
      resolveCreatePrTargetRemote({
        options,
        projectRemoteName: 'upstream',
      })?.remote.name
    ).toBe('upstream');
  });

  it('uses the selected modal target when provided', () => {
    expect(
      resolveCreatePrTargetRemote({
        options,
        projectRemoteName: 'upstream',
        selectedRemoteName: 'origin',
      })?.remote.name
    ).toBe('origin');
  });

  it('falls back to the repository URL when the project remote is not GitHub', () => {
    expect(
      resolveCreatePrTargetRemote({
        options,
        projectRemoteName: 'gitlab',
        fallbackRepositoryUrl: 'https://github.com/org/repo',
      })?.remote.name
    ).toBe('upstream');
  });
});

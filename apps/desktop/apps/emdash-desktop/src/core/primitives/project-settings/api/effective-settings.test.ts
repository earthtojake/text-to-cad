import { describe, expect, it } from 'vitest';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import {
  resolveEffectiveGitSettings,
  resolveEffectiveSettings,
  resolveTmux,
  type RepoFacts,
  type StoredSettings,
} from './effective-settings';

function facts(overrides: Partial<RepoFacts> = {}): RepoFacts {
  return { remotes: [], localBranches: [], ...overrides };
}

function remote(
  name: string,
  overrides: Partial<Omit<RepoFacts['remotes'][number], 'name'>> = {}
): RepoFacts['remotes'][number] {
  return { name, host: 'github.com', headBranch: null, branches: [], ...overrides };
}

function stored(
  project: StoredSettings['project'] = {},
  overrides: Partial<Omit<StoredSettings, 'project'>> = {}
): StoredSettings {
  return {
    project,
    hostWorktreeRoot: null,
    builtInWorktreeRoot: '/home/me/.emdash/worktrees',
    ...overrides,
  };
}

function account(
  accountId: string,
  overrides: Partial<GitHubAccountSummary> = {}
): GitHubAccountSummary {
  return {
    accountId,
    host: 'github.com',
    login: accountId,
    avatarUrl: '',
    credentialSource: 'emdash_oauth',
    isDefault: false,
    ...overrides,
  };
}

describe('resolveEffectiveSettings', () => {
  describe('base remote', () => {
    it('returns a stored remote that exists as set', () => {
      const result = resolveEffectiveSettings(
        stored({ baseRemote: 'upstream' }),
        facts({ remotes: [remote('origin'), remote('upstream')] }),
        []
      );
      expect(result.baseRemote).toEqual({ value: 'upstream', provenance: { kind: 'set' } });
    });

    it('degrades a stored remote that no longer exists to broken-setting with the inferred fallback', () => {
      const result = resolveEffectiveSettings(
        stored({ baseRemote: 'upstream' }),
        facts({ remotes: [remote('origin')] }),
        []
      );
      expect(result.baseRemote).toEqual({
        value: 'origin',
        provenance: { kind: 'broken-setting', staleValue: 'upstream' },
      });
    });

    it('degrades a stored remote to a null fallback when no remotes exist', () => {
      const result = resolveEffectiveSettings(stored({ baseRemote: 'upstream' }), facts(), []);
      expect(result.baseRemote).toEqual({
        value: null,
        provenance: { kind: 'broken-setting', staleValue: 'upstream' },
      });
    });

    it('infers origin when it exists', () => {
      const result = resolveEffectiveSettings(
        stored(),
        facts({ remotes: [remote('upstream'), remote('origin')] }),
        []
      );
      expect(result.baseRemote).toEqual({
        value: 'origin',
        provenance: { kind: 'inferred', from: 'origin remote' },
      });
    });

    it('infers the sole remote when origin does not exist', () => {
      const result = resolveEffectiveSettings(
        stored(),
        facts({ remotes: [remote('upstream')] }),
        []
      );
      expect(result.baseRemote).toEqual({
        value: 'upstream',
        provenance: { kind: 'inferred', from: 'sole remote' },
      });
    });

    it('infers the first remote alphabetically when several exist without origin', () => {
      const result = resolveEffectiveSettings(
        stored(),
        facts({ remotes: [remote('upstream'), remote('fork')] }),
        []
      );
      expect(result.baseRemote).toEqual({
        value: 'fork',
        provenance: { kind: 'inferred', from: 'first remote alphabetically' },
      });
    });

    it('is unresolvable with zero remotes', () => {
      const result = resolveEffectiveSettings(stored(), facts(), []);
      expect(result.baseRemote).toEqual({ value: null, provenance: { kind: 'unresolvable' } });
    });
  });

  describe('push remote', () => {
    it('returns a stored remote that exists as set', () => {
      const result = resolveEffectiveSettings(
        stored({ pushRemote: 'fork' }),
        facts({ remotes: [remote('origin'), remote('fork')] }),
        []
      );
      expect(result.pushRemote).toEqual({ value: 'fork', provenance: { kind: 'set' } });
    });

    it('degrades a stored remote that no longer exists to the effective base remote', () => {
      const result = resolveEffectiveSettings(
        stored({ pushRemote: 'fork' }),
        facts({ remotes: [remote('origin')] }),
        []
      );
      expect(result.pushRemote).toEqual({
        value: 'origin',
        provenance: { kind: 'broken-setting', staleValue: 'fork' },
      });
    });

    it('infers the effective base remote when unset', () => {
      const result = resolveEffectiveSettings(
        stored({ baseRemote: 'upstream' }),
        facts({ remotes: [remote('upstream')] }),
        []
      );
      expect(result.pushRemote).toEqual({
        value: 'upstream',
        provenance: { kind: 'inferred', from: 'base remote' },
      });
    });

    it('is unresolvable when the base remote is unresolvable', () => {
      const result = resolveEffectiveSettings(stored(), facts(), []);
      expect(result.pushRemote).toEqual({ value: null, provenance: { kind: 'unresolvable' } });
    });
  });

  describe('default branch', () => {
    it('returns a stored remote branch that exists as set', () => {
      const result = resolveEffectiveSettings(
        stored({ defaultBranch: { remote: 'origin', branch: 'develop' } }),
        facts({ remotes: [remote('origin', { branches: ['main', 'develop'] })] }),
        []
      );
      expect(result.defaultBranch).toEqual({
        value: { remote: 'origin', branch: 'develop' },
        provenance: { kind: 'set' },
      });
    });

    it('returns a stored local branch that exists as set', () => {
      const result = resolveEffectiveSettings(
        stored({ defaultBranch: { remote: null, branch: 'work' } }),
        facts({ localBranches: ['work'] }),
        []
      );
      expect(result.defaultBranch).toEqual({
        value: { remote: null, branch: 'work' },
        provenance: { kind: 'set' },
      });
    });

    it('degrades a stored branch whose remote is gone to broken-setting with the inferred fallback', () => {
      const result = resolveEffectiveSettings(
        stored({ defaultBranch: { remote: 'upstream', branch: 'main' } }),
        facts({ remotes: [remote('origin', { headBranch: 'main' })] }),
        []
      );
      expect(result.defaultBranch).toEqual({
        value: { remote: 'origin', branch: 'main' },
        provenance: { kind: 'broken-setting', staleValue: 'upstream/main' },
      });
    });

    it('degrades a stored remote branch that no longer exists on the remote', () => {
      const result = resolveEffectiveSettings(
        stored({ defaultBranch: { remote: 'origin', branch: 'gone' } }),
        facts({ remotes: [remote('origin', { headBranch: 'main', branches: ['main'] })] }),
        []
      );
      expect(result.defaultBranch).toEqual({
        value: { remote: 'origin', branch: 'main' },
        provenance: { kind: 'broken-setting', staleValue: 'origin/gone' },
      });
    });

    it('degrades a stored local branch that no longer exists', () => {
      const result = resolveEffectiveSettings(
        stored({ defaultBranch: { remote: null, branch: 'gone' } }),
        facts({ localBranches: ['main'] }),
        []
      );
      expect(result.defaultBranch).toEqual({
        value: { remote: null, branch: 'main' },
        provenance: { kind: 'broken-setting', staleValue: 'gone' },
      });
    });

    it('infers the remote HEAD of the effective base remote', () => {
      const result = resolveEffectiveSettings(
        stored(),
        facts({ remotes: [remote('origin', { headBranch: 'trunk' })] }),
        []
      );
      expect(result.defaultBranch).toEqual({
        value: { remote: 'origin', branch: 'trunk' },
        provenance: { kind: 'inferred', from: 'remote HEAD' },
      });
    });

    it('infers the first well-known branch on the base remote when HEAD is unknown', () => {
      const result = resolveEffectiveSettings(
        stored(),
        facts({ remotes: [remote('origin', { branches: ['develop', 'master'] })] }),
        []
      );
      expect(result.defaultBranch).toEqual({
        value: { remote: 'origin', branch: 'master' },
        provenance: { kind: 'inferred', from: 'well-known remote branch' },
      });
    });

    it('falls back to well-known local branches when the remote has no candidates', () => {
      const result = resolveEffectiveSettings(
        stored(),
        facts({ remotes: [remote('origin')], localBranches: ['trunk'] }),
        []
      );
      expect(result.defaultBranch).toEqual({
        value: { remote: null, branch: 'trunk' },
        provenance: { kind: 'inferred', from: 'well-known local branch' },
      });
    });

    it('infers locally with zero remotes', () => {
      const result = resolveEffectiveSettings(
        stored(),
        facts({ localBranches: ['main', 'feature/x'] }),
        []
      );
      expect(result.defaultBranch).toEqual({
        value: { remote: null, branch: 'main' },
        provenance: { kind: 'inferred', from: 'well-known local branch' },
      });
    });

    it('is unresolvable when no candidates exist anywhere', () => {
      const result = resolveEffectiveSettings(
        stored(),
        facts({ remotes: [remote('origin')], localBranches: ['feature/x'] }),
        []
      );
      expect(result.defaultBranch).toEqual({ value: null, provenance: { kind: 'unresolvable' } });
    });
  });

  describe('github account', () => {
    it('returns explicit none as a set null', () => {
      const result = resolveEffectiveSettings(
        stored({ githubAccount: { kind: 'none' } }),
        facts({ remotes: [remote('origin')] }),
        [account('a1', { isDefault: true })]
      );
      expect(result.githubAccount).toEqual({ value: null, provenance: { kind: 'set' } });
    });

    it('returns a pinned account whose host matches the base remote as set', () => {
      const pinned = account('a1');
      const result = resolveEffectiveSettings(
        stored({ githubAccount: { kind: 'account', accountId: 'a1' } }),
        facts({ remotes: [remote('origin', { host: 'github.com' })] }),
        [pinned, account('a2', { isDefault: true })]
      );
      expect(result.githubAccount).toEqual({ value: pinned, provenance: { kind: 'set' } });
    });

    it('fails closed on a dangling pin instead of resolving another account', () => {
      const result = resolveEffectiveSettings(
        stored({ githubAccount: { kind: 'account', accountId: 'gone' } }),
        facts({ remotes: [remote('origin')] }),
        [account('a1', { isDefault: true })]
      );
      expect(result.githubAccount).toEqual({ value: null, provenance: { kind: 'unresolvable' } });
    });

    it('fails closed on a host-mismatched pin', () => {
      const result = resolveEffectiveSettings(
        stored({ githubAccount: { kind: 'account', accountId: 'a1' } }),
        facts({ remotes: [remote('origin', { host: 'ghe.example.com' })] }),
        [account('a1', { host: 'github.com' })]
      );
      expect(result.githubAccount).toEqual({ value: null, provenance: { kind: 'unresolvable' } });
    });

    it('keeps a pinned account when the repository host is unknown', () => {
      const pinned = account('a1');
      const result = resolveEffectiveSettings(
        stored({ githubAccount: { kind: 'account', accountId: 'a1' } }),
        facts({ remotes: [remote('origin', { host: null })] }),
        [pinned]
      );
      expect(result.githubAccount).toEqual({ value: pinned, provenance: { kind: 'set' } });
    });

    it('infers the provider default account when its host matches the base remote', () => {
      const preferred = account('a2', { isDefault: true });
      const result = resolveEffectiveSettings(
        stored(),
        facts({ remotes: [remote('origin', { host: 'github.com' })] }),
        [account('a1'), preferred]
      );
      expect(result.githubAccount).toEqual({
        value: preferred,
        provenance: { kind: 'inferred', from: 'default account' },
      });
    });

    it('infers the only host-matching account when the default does not match', () => {
      const matching = account('a1', { host: 'ghe.example.com' });
      const result = resolveEffectiveSettings(
        stored(),
        facts({ remotes: [remote('origin', { host: 'ghe.example.com' })] }),
        [matching, account('a2', { isDefault: true })]
      );
      expect(result.githubAccount).toEqual({
        value: matching,
        provenance: { kind: 'inferred', from: 'only host-matching account' },
      });
    });

    it('infers none when several non-default accounts match the host', () => {
      const result = resolveEffectiveSettings(
        stored(),
        facts({ remotes: [remote('origin', { host: 'github.com' })] }),
        [account('a1'), account('a2')]
      );
      expect(result.githubAccount).toEqual({
        value: null,
        provenance: { kind: 'inferred', from: 'no host-matching account' },
      });
    });

    it('infers none with zero accounts', () => {
      const result = resolveEffectiveSettings(stored(), facts({ remotes: [remote('origin')] }), []);
      expect(result.githubAccount).toEqual({
        value: null,
        provenance: { kind: 'inferred', from: 'no host-matching account' },
      });
    });

    it('infers none when there is no base remote host to match against', () => {
      const result = resolveEffectiveSettings(stored(), facts(), [
        account('a1', { isDefault: true }),
      ]);
      expect(result.githubAccount).toEqual({
        value: null,
        provenance: { kind: 'inferred', from: 'no host-matching account' },
      });
    });

    it('normalizes hosts when matching accounts against the base remote', () => {
      const preferred = account('a1', { host: 'www.github.com', isDefault: true });
      const result = resolveEffectiveSettings(
        stored(),
        facts({ remotes: [remote('origin', { host: 'github.com' })] }),
        [preferred]
      );
      expect(result.githubAccount).toEqual({
        value: preferred,
        provenance: { kind: 'inferred', from: 'default account' },
      });
    });
  });

  describe('worktree root', () => {
    it('returns the per-project override as set', () => {
      const result = resolveEffectiveSettings(
        stored({ worktreeRoot: '/custom/worktrees' }, { hostWorktreeRoot: '/host/worktrees' }),
        facts(),
        []
      );
      expect(result.worktreeRoot).toEqual({
        value: '/custom/worktrees',
        provenance: { kind: 'set' },
      });
    });

    it('inherits the per-host default when the project has no override', () => {
      const result = resolveEffectiveSettings(
        stored({}, { hostWorktreeRoot: '/host/worktrees' }),
        facts(),
        []
      );
      expect(result.worktreeRoot).toEqual({
        value: '/host/worktrees',
        provenance: { kind: 'inferred', from: 'host default' },
      });
    });

    it('inherits the built-in default when nothing is configured', () => {
      const result = resolveEffectiveSettings(stored(), facts(), []);
      expect(result.worktreeRoot).toEqual({
        value: '/home/me/.emdash/worktrees',
        provenance: { kind: 'inferred', from: 'built-in default' },
      });
    });

    describe('with a home directory (validated chain)', () => {
      const home = { homeDirectory: '/home/me' };

      it('expands ~ in the per-project override against the host home', () => {
        const result = resolveEffectiveSettings(
          stored({ worktreeRoot: '~/fast-worktrees' }, home),
          facts(),
          []
        );
        expect(result.worktreeRoot).toEqual({
          value: '/home/me/fast-worktrees',
          provenance: { kind: 'set' },
        });
      });

      it('normalizes redundant path segments in a configured root', () => {
        const result = resolveEffectiveSettings(
          stored({ worktreeRoot: '/tmp//pool/../worktrees/' }, home),
          facts(),
          []
        );
        expect(result.worktreeRoot).toEqual({
          value: '/tmp/worktrees',
          provenance: { kind: 'set' },
        });
      });

      it('degrades an invalid project override to the host default with broken-setting', () => {
        const result = resolveEffectiveSettings(
          stored(
            { worktreeRoot: 'relative/worktrees' },
            { ...home, hostWorktreeRoot: '/host/worktrees' }
          ),
          facts(),
          []
        );
        expect(result.worktreeRoot).toEqual({
          value: '/host/worktrees',
          provenance: { kind: 'broken-setting', staleValue: 'relative/worktrees' },
        });
      });

      it('degrades an invalid host default to the built-in root with broken-setting', () => {
        const result = resolveEffectiveSettings(
          stored({}, { ...home, hostWorktreeRoot: 'not-absolute' }),
          facts(),
          []
        );
        expect(result.worktreeRoot).toEqual({
          value: '/home/me/.emdash/worktrees',
          provenance: { kind: 'broken-setting', staleValue: 'not-absolute' },
        });
      });

      it('carries the first broken layer when several layers are invalid', () => {
        const result = resolveEffectiveSettings(
          stored({ worktreeRoot: 'bad-project' }, { ...home, hostWorktreeRoot: 'bad-host' }),
          facts(),
          []
        );
        expect(result.worktreeRoot).toEqual({
          value: '/home/me/.emdash/worktrees',
          provenance: { kind: 'broken-setting', staleValue: 'bad-project' },
        });
      });
    });
  });
});

describe('resolveTmux', () => {
  it('uses an explicit project choice before host and app defaults', () => {
    expect(resolveTmux({ projectTmux: false, hostTmux: true, appDefaultTmux: true })).toEqual({
      value: false,
      provenance: { kind: 'set' },
    });
  });

  it('inherits the host default when no project choice exists', () => {
    expect(resolveTmux({ hostTmux: true, appDefaultTmux: false })).toEqual({
      value: true,
      provenance: { kind: 'inferred', from: 'host default' },
    });
  });

  it('inherits the app default when the host has no override', () => {
    expect(resolveTmux({ hostTmux: null, appDefaultTmux: true })).toEqual({
      value: true,
      provenance: { kind: 'inferred', from: 'app default' },
    });
  });
});

describe('resolveEffectiveGitSettings', () => {
  it('produces the identical git subset the full resolver produces', () => {
    const project = {
      baseRemote: 'upstream',
      pushRemote: 'gone',
      defaultBranch: { remote: 'upstream', branch: 'develop' },
    };
    const repoFacts = facts({
      remotes: [
        remote('origin', { headBranch: 'main', branches: ['main'] }),
        remote('upstream', { branches: ['develop'] }),
      ],
      localBranches: ['main'],
    });

    const full = resolveEffectiveSettings(stored(project), repoFacts, []);
    const subset = resolveEffectiveGitSettings(project, repoFacts);

    expect(subset).toEqual({
      baseRemote: full.baseRemote,
      pushRemote: full.pushRemote,
      defaultBranch: full.defaultBranch,
    });
  });

  it('answers unresolvable values with zero remotes instead of fabricating origin', () => {
    const result = resolveEffectiveGitSettings({}, facts());
    expect(result.baseRemote).toEqual({ value: null, provenance: { kind: 'unresolvable' } });
    expect(result.pushRemote).toEqual({ value: null, provenance: { kind: 'unresolvable' } });
    expect(result.defaultBranch).toEqual({ value: null, provenance: { kind: 'unresolvable' } });
  });

  it('surfaces a stale push-remote pin as broken-setting instead of a silent substitution', () => {
    const result = resolveEffectiveGitSettings(
      { pushRemote: 'fork' },
      facts({ remotes: [remote('origin')] })
    );
    expect(result.pushRemote).toEqual({
      value: 'origin',
      provenance: { kind: 'broken-setting', staleValue: 'fork' },
    });
  });
});

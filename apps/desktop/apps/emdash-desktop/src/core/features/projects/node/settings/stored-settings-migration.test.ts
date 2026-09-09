import { describe, expect, it } from 'vitest';
import {
  storedBaseProjectSettingsSchema,
  type RepoFacts,
} from '@core/primitives/project-settings/api';
import {
  legacyBaseSettingsToStored,
  migrateStoredBaseProjectSettings,
  toLegacyBaseSettingsView,
} from './migrations/stored-settings';

const facts = (overrides: Partial<RepoFacts> = {}): RepoFacts => ({
  remotes: [
    {
      name: 'origin',
      host: 'github.com',
      headBranch: 'main',
      branches: ['main', 'develop'],
    },
  ],
  localBranches: ['main'],
  ...overrides,
});

describe('storedBaseProjectSettingsSchema', () => {
  it('contains only current DB-owned settings', () => {
    expect(
      storedBaseProjectSettingsSchema.parse({
        worktreeRoot: '/tmp/worktrees',
        tmux: false,
        autoRunSetupScriptOnTaskCreation: false,
        autoRunRunScriptOnTaskCreation: true,
      })
    ).toEqual({
      worktreeRoot: '/tmp/worktrees',
      tmux: false,
    });
  });
});

describe('migrateStoredBaseProjectSettings', () => {
  describe('migration 1: legacy defaultBranch forms', () => {
    it('converts a bare local branch string to { remote: null, branch }', () => {
      const { next, changed } = migrateStoredBaseProjectSettings(
        { defaultBranch: 'develop' },
        null
      );
      expect(next.defaultBranch).toEqual({ remote: null, branch: 'develop' });
      expect(changed).toBe(true);
    });

    it('converts a remote-qualified string using a known remote prefix', () => {
      const { next } = migrateStoredBaseProjectSettings(
        { defaultBranch: 'origin/feature/x', baseRemote: 'upstream' },
        facts()
      );
      expect(next.defaultBranch).toEqual({ remote: 'origin', branch: 'feature/x' });
    });

    it('falls back to a split-at-first-slash remote guess without facts', () => {
      const { next } = migrateStoredBaseProjectSettings({ defaultBranch: 'upstream/main' }, null);
      expect(next.defaultBranch).toEqual({ remote: 'upstream', branch: 'main' });
    });

    it('converts the { name, remote: true } form against the stored base remote', () => {
      const { next } = migrateStoredBaseProjectSettings(
        { defaultBranch: { name: 'main', remote: true }, baseRemote: 'upstream' },
        null
      );
      expect(next.defaultBranch).toEqual({ remote: 'upstream', branch: 'main' });
    });

    it('defaults the { name, remote: true } form to origin without a stored base remote', () => {
      const { next } = migrateStoredBaseProjectSettings(
        { defaultBranch: { name: 'develop', remote: true } },
        null
      );
      expect(next.defaultBranch).toEqual({ remote: 'origin', branch: 'develop' });
    });

    it('keeps an already-structured defaultBranch as-is', () => {
      const { next, changed } = migrateStoredBaseProjectSettings(
        { defaultBranch: { remote: 'upstream', branch: 'dev' }, baseRemote: 'upstream' },
        null
      );
      expect(next.defaultBranch).toEqual({ remote: 'upstream', branch: 'dev' });
      expect(changed).toBe(false);
    });
  });

  describe('migration 2: legacy githubAccountId', () => {
    it('converts a legacy string to an account ref', () => {
      const { next, changed } = migrateStoredBaseProjectSettings(
        { githubAccountId: 'github.com:42' },
        null
      );
      expect(next.githubAccount).toEqual({ kind: 'account', accountId: 'github.com:42' });
      expect(changed).toBe(true);
      expect(next).not.toHaveProperty('githubAccountId');
    });

    it('drops a legacy null to absent (infer), not explicit none', () => {
      const { next, changed } = migrateStoredBaseProjectSettings({ githubAccountId: null }, null);
      expect(next).not.toHaveProperty('githubAccount');
      expect(next).not.toHaveProperty('githubAccountId');
      expect(changed).toBe(true);
    });

    it('keeps an already-migrated githubAccount over a lingering legacy key', () => {
      const { next } = migrateStoredBaseProjectSettings(
        { githubAccount: { kind: 'none' }, githubAccountId: 'github.com:42' },
        null
      );
      expect(next.githubAccount).toEqual({ kind: 'none' });
    });
  });

  describe('migration 3: demote-if-matches-inference', () => {
    it('clears a baseRemote equal to the inferred base remote', () => {
      const { next, changed } = migrateStoredBaseProjectSettings({ baseRemote: 'origin' }, facts());
      expect(next).not.toHaveProperty('baseRemote');
      expect(changed).toBe(true);
    });

    it('keeps a divergent baseRemote pinned', () => {
      const withUpstream = facts({
        remotes: [
          { name: 'origin', host: 'github.com', headBranch: 'main', branches: ['main'] },
          { name: 'upstream', host: 'github.com', headBranch: 'main', branches: ['main'] },
        ],
      });
      const { next } = migrateStoredBaseProjectSettings({ baseRemote: 'upstream' }, withUpstream);
      expect(next.baseRemote).toBe('upstream');
    });

    it('clears a defaultBranch equal to the inferred default branch', () => {
      const { next } = migrateStoredBaseProjectSettings({ defaultBranch: 'origin/main' }, facts());
      expect(next).not.toHaveProperty('defaultBranch');
    });

    it('keeps a divergent defaultBranch pinned', () => {
      const { next } = migrateStoredBaseProjectSettings(
        { defaultBranch: 'origin/develop' },
        facts()
      );
      expect(next.defaultBranch).toEqual({ remote: 'origin', branch: 'develop' });
    });

    it('demotes both seeded values of a typical legacy row at once', () => {
      const { next } = migrateStoredBaseProjectSettings(
        { defaultBranch: 'origin/main', baseRemote: 'origin', tmux: true },
        facts()
      );
      expect(next).toEqual({ tmux: true });
    });

    it('skips demotion without repo facts and keeps values pinned', () => {
      const { next } = migrateStoredBaseProjectSettings(
        { defaultBranch: { remote: 'origin', branch: 'main' }, baseRemote: 'origin' },
        null
      );
      expect(next.baseRemote).toBe('origin');
      expect(next.defaultBranch).toEqual({ remote: 'origin', branch: 'main' });
    });

    it('does not demote when the inference is unresolvable', () => {
      const empty = facts({ remotes: [], localBranches: [] });
      const { next } = migrateStoredBaseProjectSettings(
        { baseRemote: 'origin', defaultBranch: 'origin/main' },
        empty
      );
      expect(next.baseRemote).toBe('origin');
      expect(next.defaultBranch).toEqual({ remote: 'origin', branch: 'main' });
    });
  });

  describe('migration 4: worktreeDirectory rename', () => {
    it('renames worktreeDirectory to worktreeRoot', () => {
      const { next, changed } = migrateStoredBaseProjectSettings(
        { worktreeDirectory: '/tmp/worktrees' },
        null
      );
      expect(next.worktreeRoot).toBe('/tmp/worktrees');
      expect(next).not.toHaveProperty('worktreeDirectory');
      expect(changed).toBe(true);
    });

    it('prefers an already-migrated worktreeRoot over a lingering legacy key', () => {
      const { next } = migrateStoredBaseProjectSettings(
        { worktreeRoot: '/new', worktreeDirectory: '/old' },
        null
      );
      expect(next.worktreeRoot).toBe('/new');
    });
  });

  it('reports changed: false for an already-migrated row', () => {
    const { changed } = migrateStoredBaseProjectSettings(
      {
        worktreeRoot: '/tmp/worktrees',
        defaultBranch: { remote: 'upstream', branch: 'dev' },
        baseRemote: 'upstream',
        githubAccount: { kind: 'account', accountId: 'github.com:42' },
        tmux: true,
      },
      facts({
        remotes: [
          { name: 'origin', host: 'github.com', headBranch: 'main', branches: ['main'] },
          { name: 'upstream', host: 'github.com', headBranch: 'main', branches: ['main', 'dev'] },
        ],
      })
    );
    expect(changed).toBe(false);
  });

  it('migrates a row with every legacy form at once', () => {
    const { next, changed } = migrateStoredBaseProjectSettings(
      {
        defaultBranch: 'origin/main',
        baseRemote: 'origin',
        githubAccountId: 'github.com:42',
        worktreeDirectory: '/tmp/worktrees',
        tmux: true,
      },
      facts()
    );
    expect(next).toEqual({
      githubAccount: { kind: 'account', accountId: 'github.com:42' },
      worktreeRoot: '/tmp/worktrees',
      tmux: true,
    });
    expect(changed).toBe(true);
  });
});

describe('toLegacyBaseSettingsView', () => {
  it('formats a remote-qualified stored defaultBranch as a string', () => {
    expect(
      toLegacyBaseSettingsView({ defaultBranch: { remote: 'origin', branch: 'main' } })
    ).toEqual({ defaultBranch: 'origin/main' });
  });

  it('formats a local stored defaultBranch as a bare string', () => {
    expect(toLegacyBaseSettingsView({ defaultBranch: { remote: null, branch: 'dev' } })).toEqual({
      defaultBranch: 'dev',
    });
  });

  it('maps worktreeRoot back to worktreeDirectory', () => {
    expect(toLegacyBaseSettingsView({ worktreeRoot: '/tmp/w' })).toEqual({
      worktreeDirectory: '/tmp/w',
    });
  });

  it('maps githubAccount refs to githubAccountId and explicit none to null', () => {
    expect(
      toLegacyBaseSettingsView({ githubAccount: { kind: 'account', accountId: 'a-1' } })
    ).toEqual({ githubAccountId: 'a-1' });
    expect(toLegacyBaseSettingsView({ githubAccount: { kind: 'none' } })).toEqual({
      githubAccountId: null,
    });
  });

  it('leaves an absent githubAccount absent (infer)', () => {
    expect(toLegacyBaseSettingsView({})).not.toHaveProperty('githubAccountId');
  });
});

describe('legacyBaseSettingsToStored', () => {
  it('round-trips through the legacy view', () => {
    const stored = {
      worktreeRoot: '/tmp/w',
      defaultBranch: { remote: 'origin', branch: 'main' },
      baseRemote: 'upstream',
      pushRemote: 'fork',
      githubAccount: { kind: 'account' as const, accountId: 'a-1' },
      tmux: true,
    };
    expect(legacyBaseSettingsToStored(toLegacyBaseSettingsView(stored))).toEqual(stored);
  });

  it('maps explicit null githubAccountId to explicit none', () => {
    expect(legacyBaseSettingsToStored({ githubAccountId: null })).toEqual({
      githubAccount: { kind: 'none' },
    });
  });

  it('keeps an absent githubAccountId absent', () => {
    expect(legacyBaseSettingsToStored({})).toEqual({});
  });
});

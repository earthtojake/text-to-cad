import type * as SharedLogger from '@emdash/shared/logger';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RepoFacts } from '@core/primitives/project-settings/api';
import { resolveProjectEffectiveSettings } from './effective-settings';

const mocks = vi.hoisted(() => ({
  warn: vi.fn(),
}));

vi.mock('@emdash/shared/logger', async (importOriginal) => {
  const original = await importOriginal<typeof SharedLogger>();
  return {
    ...original,
    log: { ...original.log, warn: mocks.warn },
  };
});

const FACTS: RepoFacts = {
  remotes: [{ name: 'origin', host: 'github.com', headBranch: 'main', branches: ['main'] }],
  localBranches: ['main'],
};

function makeSettingsSource(stored: Record<string, unknown>) {
  return {
    getStoredGitSettings: vi.fn().mockResolvedValue(stored),
    getPlacementContext: vi.fn().mockResolvedValue({
      hostWorktreeRoot: null,
      builtInWorktreeRoot: '/home/me/emdash/worktrees',
      homeDirectory: '/home/me',
      hostTmux: null,
      appDefaultTmux: false,
    }),
  };
}

function makeRepoFactsSource(facts: RepoFacts | null) {
  return { get: vi.fn().mockResolvedValue(facts), dispose: vi.fn() };
}

describe('resolveProjectEffectiveSettings', () => {
  beforeEach(() => {
    mocks.warn.mockReset();
  });

  it('degrades a stale baseRemote to the inferred fallback and logs a warning', async () => {
    const effective = await resolveProjectEffectiveSettings({
      settings: makeSettingsSource({ baseRemote: 'gone' }),
      repoFacts: makeRepoFactsSource(FACTS),
      projectId: 'project-1',
    });

    expect(effective.baseRemote).toEqual({
      value: 'origin',
      provenance: { kind: 'broken-setting', staleValue: 'gone' },
    });
    expect(mocks.warn).toHaveBeenCalledWith(
      'Stale baseRemote setting no longer matches the repository; using inferred fallback',
      { projectId: 'project-1', staleValue: 'gone', fallback: 'origin' }
    );
  });

  it('resolves without warnings when unavailable facts leave nothing to check', async () => {
    const effective = await resolveProjectEffectiveSettings({
      settings: makeSettingsSource({}),
      repoFacts: makeRepoFactsSource(null),
    });

    expect(effective.baseRemote.value).toBeNull();
    expect(effective.defaultBranch.value).toBeNull();
    expect(mocks.warn).not.toHaveBeenCalled();
  });

  it('degrades an unusable worktree root to the next layer and logs a warning', async () => {
    const effective = await resolveProjectEffectiveSettings({
      settings: makeSettingsSource({ worktreeRoot: 'relative/pool' }),
      repoFacts: makeRepoFactsSource(FACTS),
      projectId: 'project-1',
    });

    expect(effective.worktreeRoot).toEqual({
      value: '/home/me/emdash/worktrees',
      provenance: { kind: 'broken-setting', staleValue: 'relative/pool' },
    });
    expect(mocks.warn).toHaveBeenCalledWith(
      'Stale worktreeRoot setting no longer matches the repository; using inferred fallback',
      { projectId: 'project-1', staleValue: 'relative/pool', fallback: '/home/me/emdash/worktrees' }
    );
  });

  it('resolves the default branch from the remote HEAD fact', async () => {
    const effective = await resolveProjectEffectiveSettings({
      settings: makeSettingsSource({}),
      repoFacts: makeRepoFactsSource(FACTS),
    });

    expect(effective.defaultBranch).toEqual({
      value: { remote: 'origin', branch: 'main' },
      provenance: { kind: 'inferred', from: 'remote HEAD' },
    });
  });
});

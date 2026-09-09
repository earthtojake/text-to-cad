import type {
  CheckoutHeadState,
  CheckoutStatusState,
  GitRefsState,
  GitRemotesState,
} from '@emdash/core/runtimes/git/api';
import { localBranchRefSchema, remoteBranchRefSchema } from '@emdash/core/runtimes/git/api';
import { ok } from '@emdash/shared';
import { createManualClock, type ManualClock } from '@emdash/shared/testing';
import { cell, expose, flushStateTurn } from '@emdash/wire/state';
import { createTestWire } from '@emdash/wire/testing';
import { observable } from 'mobx';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  ProjectHostAccess,
  ProjectHostAccessState,
} from '@core/features/projects/api/browser/stores/project-context';
import type { ProjectSettingsStore } from '@core/features/projects/api/browser/stores/project-settings-store';
import type * as SourceControlClientModule from '@core/features/source-control/api/browser/client';
import type { StoredProjectGitSettings } from '@core/primitives/project-settings/api';
import { sourceControlContract } from '../..';
import { GitRepositoryStore } from './git-repository-store';

const mocks = vi.hoisted(() => ({
  getDefaultBranch: vi.fn(),
  fetchRun: vi.fn(),
  resolveProvider: vi.fn(),
}));

let refsState: ReturnType<typeof cell<GitRefsState>>;
let remotesState: ReturnType<typeof cell<GitRemotesState>>;
let wire: ReturnType<typeof createSourceControlWire> | undefined;

vi.mock('@core/features/source-control/api/browser/client', async (importOriginal) => {
  const actual = await importOriginal<typeof SourceControlClientModule>();
  return {
    ...actual,
    getSourceControlClient: async () => wire!.client,
  };
});

vi.mock('@core/features/repository/api/client', () => ({
  getRepositoryClient: async () => ({ resolveProvider: mocks.resolveProvider }),
}));

const origin = { name: 'origin', url: 'https://github.com/example/repo.git' };

function refs(overrides: Partial<GitRefsState> = {}): GitRefsState {
  return { branches: [], tags: [], remoteHeads: [], ...overrides };
}

function localBranch(name: string, oid: string) {
  return { type: 'local' as const, ref: localBranchRefSchema.parse(`refs/heads/${name}`), oid };
}

function remoteBranch(remote: typeof origin, name: string, oid: string) {
  return {
    type: 'remote' as const,
    ref: remoteBranchRefSchema.parse(`refs/remotes/${remote.name}/${name}`),
    remote,
    oid,
  };
}

function settingsStore(storedGitSettings: StoredProjectGitSettings | null): ProjectSettingsStore {
  return {
    domains: {
      gitIdentity: { stored: storedGitSettings ?? {} },
    },
  } as unknown as ProjectSettingsStore;
}

async function startStore(stored: StoredProjectGitSettings | null = null, clock?: ManualClock) {
  const store = new GitRepositoryStore(
    'project-1',
    settingsStore(stored),
    projectHostAccess({ kind: 'ready', hostGeneration: 1 }).host,
    clock
  );
  store.start();
  await waitFor(() => !store.loading);
  return store;
}

function projectHostAccess(initial: ProjectHostAccessState) {
  const state = observable.box(initial, { deep: false });
  const host: ProjectHostAccess = {
    get state() {
      return state.get();
    },
    get liveAction() {
      const current = state.get();
      return current.kind === 'ready'
        ? { kind: 'enabled' as const }
        : { kind: 'disabled' as const, state: current };
    },
    observe(observation) {
      if (observation.kind === 'never-observed') return { kind: 'unavailable' };
      return state.get().kind === 'ready'
        ? { kind: 'fresh', value: observation.value, observedAt: observation.observedAt }
        : { kind: 'stale', value: observation.value, observedAt: observation.observedAt };
    },
    requireLive: vi.fn(),
    recover: vi.fn(),
  };
  return { host, state };
}

describe('GitRepositoryStore', () => {
  beforeEach(() => {
    refsState = cell(refs());
    remotesState = cell({ remotes: [] });
    mocks.getDefaultBranch.mockResolvedValue(ok({ branch: null }));
    mocks.resolveProvider.mockResolvedValue({ success: false, error: { type: 'no_remote' } });
    wire = createSourceControlWire();
  });

  afterEach(async () => {
    await wire?.dispose();
    wire = undefined;
    vi.clearAllMocks();
  });

  it('timestamps Git observations through the injected clock', async () => {
    const store = await startStore(null, createManualClock(1_786_000_000_000));

    expect(store.refsObservation).toMatchObject({ observedAt: 1_786_000_000_000 });
    expect(store.remotesObservation).toMatchObject({ observedAt: 1_786_000_000_000 });
    store.dispose();
  });

  describe('with zero remotes', () => {
    it('answers null remotes with unresolvable provenance instead of fabricating origin', async () => {
      const store = await startStore();

      expect(store.baseRemote).toBeNull();
      expect(store.pushRemote).toBeNull();
      expect(store.effectiveGitSettings.baseRemote).toEqual({
        value: null,
        provenance: { kind: 'unresolvable' },
      });
      expect(store.effectiveGitSettings.pushRemote).toEqual({
        value: null,
        provenance: { kind: 'unresolvable' },
      });
      expect(store.canonicalRepositoryUrl).toBeNull();
      store.dispose();
    });

    it('refuses fetch with an honest no_remote error instead of a raw git failure', async () => {
      const store = await startStore();

      const fetchResult = await store.fetchRemote();
      expect(fetchResult.success).toBe(false);
      if (!fetchResult.success) expect(fetchResult.error.type).toBe('no_remote');

      expect(mocks.fetchRun).not.toHaveBeenCalled();
      store.dispose();
    });

    it('still resolves a default branch from well-known local branches', async () => {
      refsState.set(refs({ branches: [localBranch('main', 'a')] }));
      const store = await startStore();

      expect(store.defaultBranch).toEqual({
        type: 'local',
        ref: 'refs/heads/main',
        oid: 'a',
      });
      expect(store.defaultBranchRef).toEqual({ type: 'local', branch: 'main' });
      expect(store.effectiveGitSettings.defaultBranch.provenance).toEqual({
        kind: 'inferred',
        from: 'well-known local branch',
      });
      store.dispose();
    });
  });

  it('surfaces a stale push-remote pin as broken-setting instead of silently substituting', async () => {
    remotesState.set({ remotes: [origin] });
    const store = await startStore({ pushRemote: 'fork' });

    expect(store.pushRemote).toEqual(origin);
    expect(store.effectiveGitSettings.pushRemote).toEqual({
      value: 'origin',
      provenance: { kind: 'broken-setting', staleValue: 'fork' },
    });
    store.dispose();
  });

  it('maps the default branch from the refs-state remote HEAD onto the live branch objects', async () => {
    remotesState.set({ remotes: [origin] });
    refsState.set(
      refs({
        branches: [remoteBranch(origin, 'develop', 'b'), remoteBranch(origin, 'main', 'c')],
        remoteHeads: [
          { remote: 'origin', ref: remoteBranchRefSchema.parse('refs/remotes/origin/develop') },
        ],
      })
    );
    const store = await startStore();

    expect(store.defaultBranch).toEqual({
      type: 'remote',
      ref: 'refs/remotes/origin/develop',
      remote: origin,
      oid: 'b',
    });
    expect(store.defaultBranchRef).toEqual({ type: 'remote', branch: 'develop', remote: origin });
    expect(store.effectiveGitSettings.defaultBranch.provenance).toEqual({
      kind: 'inferred',
      from: 'remote HEAD',
    });
    store.dispose();
  });

  it('fills the base remote HEAD fact from the async lookup when refs do not know it', async () => {
    mocks.getDefaultBranch.mockResolvedValue(ok({ branch: 'develop' }));
    remotesState.set({ remotes: [origin] });
    refsState.set(
      refs({
        branches: [remoteBranch(origin, 'develop', 'b'), remoteBranch(origin, 'main', 'c')],
      })
    );
    const store = await startStore();

    await store.gitDefaultBranchInfo.load();
    await waitFor(() => store.repoFacts.remotes[0]?.headBranch === 'develop');

    expect(mocks.getDefaultBranch.mock.calls.at(0)?.[0]).toMatchObject({ remote: 'origin' });
    expect(store.defaultBranch).toEqual({
      type: 'remote',
      ref: 'refs/remotes/origin/develop',
      remote: origin,
      oid: 'b',
    });
    store.dispose();
  });

  it('retains Git and provider observations through degradation and retry', async () => {
    refsState.set(refs({ branches: [localBranch('main', 'a')] }));
    remotesState.set({ remotes: [origin] });
    mocks.resolveProvider.mockResolvedValue(
      ok({
        provider: 'github',
        host: 'github.com',
        repositoryUrl: 'https://github.com/example/repo',
        nameWithOwner: 'example/repo',
        capabilities: { pullRequests: true, issues: true },
      })
    );
    const access = projectHostAccess({ kind: 'ready', hostGeneration: 1 });
    const store = new GitRepositoryStore('project-1', settingsStore(null), access.host);

    expect(store.refsObservation).toEqual({ kind: 'unavailable' });
    expect(store.remotesObservation).toEqual({ kind: 'unavailable' });
    store.start();
    await waitFor(() => !store.loading);
    await store.providerRepositoryInfo.load();
    expect(store.refsObservation).toMatchObject({
      kind: 'fresh',
      value: { branches: [{ ref: 'refs/heads/main' }] },
    });
    expect(store.providerRepositoryObservation).toMatchObject({
      kind: 'fresh',
      value: { success: true },
    });

    access.state.set({
      kind: 'degraded',
      situation: 'offline',
      recovery: 'automatic',
    });
    expect(store.refsObservation).toMatchObject({
      kind: 'stale',
      value: { branches: [{ ref: 'refs/heads/main' }] },
    });
    expect(store.remotesObservation).toMatchObject({
      kind: 'stale',
      value: { remotes: [origin] },
    });
    expect(store.providerRepositoryObservation).toMatchObject({
      kind: 'stale',
      value: { success: true },
    });

    await store.retry();
    expect(store.refsObservation).toMatchObject({
      kind: 'stale',
      value: { branches: [{ ref: 'refs/heads/main' }] },
    });
    expect(store.remotesObservation).toMatchObject({
      kind: 'stale',
      value: { remotes: [origin] },
    });

    access.state.set({ kind: 'ready', hostGeneration: 2 });
    await waitFor(() => store.refsObservation.kind === 'fresh');
    expect(store.refsObservation).toMatchObject({
      kind: 'fresh',
      value: { branches: [{ ref: 'refs/heads/main' }] },
    });
    store.dispose();
  });
});

function createSourceControlWire() {
  const repositoryProvider = expose(sourceControlContract.repository.model, {
    refs: refsState,
    remotes: remotesState,
  });
  const checkoutProvider = expose(sourceControlContract.checkout.model, {
    status: cell<CheckoutStatusState>({
      kind: 'ok',
      entries: {},
      summary: { staged: 0, unstaged: 0, conflicted: 0, untracked: 0 },
      operation: 'none',
    }),
    head: cell<CheckoutHeadState>({
      kind: 'branch',
      ref: localBranchRefSchema.parse('refs/heads/main'),
      oid: '1234567890123456789012345678901234567890',
      upstream: { kind: 'none' },
    }),
  });

  return createTestWire(sourceControlContract, {
    repository: {
      model: repositoryProvider,
      listWorktrees: vi.fn(),
      getDefaultBranch: mocks.getDefaultBranch,
      fetch: { run: mocks.fetchRun },
      fetchPrForReview: { run: vi.fn() },
    },
    checkout: {
      model: checkoutProvider,
      getChangedFiles: vi.fn(),
      getFile: vi.fn(),
      download: vi.fn(),
      getLog: vi.fn(),
      getCommit: vi.fn(),
      getCommitFiles: vi.fn(),
      blame: vi.fn(),
      push: { run: vi.fn() },
      publish: { run: vi.fn() },
      pull: { run: vi.fn() },
    },
  } as never);
}

async function waitFor(predicate: () => boolean): Promise<void> {
  for (let index = 0; index < 50; index += 1) {
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    flushStateTurn();
    if (predicate()) return;
  }
  expect(predicate()).toBe(true);
}

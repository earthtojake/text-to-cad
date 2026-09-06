import { describe, expect, it } from 'vitest';
import type {
  PersonalProjectConfig,
  WorkspaceCreation,
  WorkspaceGitObservations,
  WorkspaceLifecycle,
} from '../../api/schemas';
import {
  parseCreationPayload,
  parseGitObservationsPayload,
  parseLifecyclePayload,
  parsePersonalProjectConfigPayload,
  serializeCreationPayload,
  serializeGitObservationsPayload,
  serializeLifecyclePayload,
  serializePersonalProjectConfigPayload,
} from './payload-codecs';

describe('personal project config payload codec', () => {
  it('round-trips only personal settings fields', () => {
    const personalConfig: PersonalProjectConfig = {
      preservePatterns: [],
      scripts: { prepare: 'pnpm install', run: 'pnpm dev' },
      autoRunSetup: false,
      autoRunRun: true,
    };
    expect(
      parsePersonalProjectConfigPayload(serializePersonalProjectConfigPayload(personalConfig))
    ).toEqual(personalConfig);
  });

  it('does not admit migration state into the personal settings document', () => {
    expect(
      parsePersonalProjectConfigPayload(
        JSON.stringify({
          version: '1',
          value: { scripts: { setup: 'setup' }, legacyDesktopSettingsMigrated: true },
        })
      )
    ).toEqual({
      scripts: { setup: 'setup' },
    });
  });
});

describe('git observations payload codec', () => {
  it('round-trips the v2 shape', () => {
    const git: WorkspaceGitObservations = {
      branch: 'feature/x',
      dirty: true,
      diffStats: { added: 3, deleted: 1 },
      ahead: 2,
      behind: 0,
      locked: false,
      prunable: false,
      headOid: 'a'.repeat(40),
      upstream: {
        remote: 'origin',
        mergeRef: 'refs/heads/feature/x',
        remoteUrl: 'https://example.com/acme/app.git',
      },
      prBreadcrumb: 'https://github.com/acme/app/pull/7',
    };
    expect(parseGitObservationsPayload(serializeGitObservationsPayload(git))).toEqual(git);
  });

  it('treats a stored v1 payload as not yet observed (no upcast path)', () => {
    // The exact JSON an old row stored: version '1', none of the v2 fields.
    const v1 = JSON.stringify({
      version: '1',
      value: {
        branch: 'main',
        dirty: false,
        diffStats: null,
        ahead: null,
        behind: null,
        locked: false,
        prunable: false,
      },
    });
    expect(parseGitObservationsPayload(v1)).toBeNull();
  });

  it('degrades corrupt payloads to null instead of throwing', () => {
    expect(parseGitObservationsPayload('not-json')).toBeNull();
    expect(parseGitObservationsPayload(JSON.stringify({ version: '2', value: 42 }))).toBeNull();
  });
});

describe('creation payload codec', () => {
  it('round-trips a creation section carrying gitSetup and a null baseRef', () => {
    const creation: WorkspaceCreation = {
      branch: 'pr/7/fix',
      baseRef: null,
      requestedPath: '/tmp/pr-wt',
      gitSetup: {
        fetchBranch: { remote: 'origin', sourceRef: 'refs/pull/7/head' },
        upstream: { remote: 'origin', mergeRef: 'refs/pull/7/head' },
        breadcrumb: { prUrl: 'https://github.com/acme/repo/pull/7' },
        followRef: true,
      },
    };
    expect(parseCreationPayload(serializeCreationPayload(creation))).toEqual(creation);
  });

  it('parses a pre-gitSetup v1 creation payload unchanged', () => {
    // The exact JSON an old row stored: required baseRef, no gitSetup field.
    const v1 = JSON.stringify({
      version: '1',
      value: { branch: 'feature/x', baseRef: 'main', requestedPath: '/tmp/wt' },
    });
    expect(parseCreationPayload(v1)).toEqual({
      branch: 'feature/x',
      baseRef: 'main',
      requestedPath: '/tmp/wt',
    });
  });
});

describe('lifecycle payload codec', () => {
  it('round-trips the current lifecycle shape', () => {
    const lifecycle: WorkspaceLifecycle = {
      steps: [
        {
          id: 'create-worktree',
          status: 'succeeded',
          startedAt: 1_000,
          finishedAt: 2_000,
          params: { path: '/tmp/wt', branch: 'feature/x', branchCreated: true },
        },
        {
          id: 'push-branch',
          status: 'pending',
          startedAt: null,
          finishedAt: null,
          params: { branch: 'feature/x' },
        },
      ],
      preservePatterns: ['.env'],
    };
    expect(parseLifecyclePayload(serializeLifecyclePayload(lifecycle))).toEqual(lifecycle);
  });

  it('upgrades a v1 background payload into lifecycle steps best-effort', () => {
    // The exact JSON an old row stored: fixed per-step slots, one `at` stamp each.
    const v1 = JSON.stringify({
      version: '1',
      value: {
        steps: {
          cloneArtifacts: { status: 'succeeded', at: 5_000 },
          pushBranch: { status: 'failed', at: 6_000, message: 'no remote' },
          fetchRefs: { status: 'running', at: 7_000 },
        },
        preservePatterns: ['.env', '.envrc'],
      },
    });
    expect(parseLifecyclePayload(v1)).toEqual({
      steps: [
        {
          id: 'copy-artifacts',
          status: 'succeeded',
          startedAt: 5_000,
          finishedAt: 5_000,
          params: {},
        },
        {
          id: 'push-branch',
          status: 'failed',
          startedAt: 6_000,
          finishedAt: 6_000,
          message: 'no remote',
          params: {},
        },
        { id: 'fetch-refs', status: 'running', startedAt: 7_000, finishedAt: null, params: {} },
      ],
      preservePatterns: ['.env', '.envrc'],
    });
  });

  it('maps never-requested v1 slots to absent steps', () => {
    const v1 = JSON.stringify({
      version: '1',
      value: {
        steps: {
          cloneArtifacts: { status: 'pending', at: 5_000 },
          pushBranch: null,
          fetchRefs: null,
        },
        preservePatterns: [],
      },
    });
    expect(parseLifecyclePayload(v1)).toEqual({
      steps: [
        { id: 'copy-artifacts', status: 'pending', startedAt: null, finishedAt: null, params: {} },
      ],
      preservePatterns: [],
    });
  });
});

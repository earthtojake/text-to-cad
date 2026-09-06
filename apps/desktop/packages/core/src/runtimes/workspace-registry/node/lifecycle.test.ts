import { describe, expect, it } from 'vitest';
import type { CreateWorktreeInput } from '../api/schemas';
import { buildCreationLifecycle, withLifecycleStep } from './lifecycle';

const input: CreateWorktreeInput = {
  workspaceId: 'ws-1',
  repositoryId: 'repo-1',
  branch: 'feature/x',
  baseRef: 'origin/main',
  path: '/tmp/wt',
  preservePatterns: ['.env'],
  publish: { remote: 'fork' },
};

describe('buildCreationLifecycle', () => {
  it('a fresh creation with a base fetch yields the full step sequence in order', () => {
    const lifecycle = buildCreationLifecycle(
      input,
      { status: 'succeeded', finalPath: '/tmp/wt', createdWorktree: true, createdBranch: true },
      [
        { stage: 'inspect', at: 100 },
        { stage: 'resolve-base', at: 120 },
        { stage: 'fetch-base', at: 130 },
        { stage: 'add-worktree', at: 400 },
        { stage: 'verify', at: 500 },
      ],
      600
    );
    expect(lifecycle.preservePatterns).toEqual(['.env']);
    expect(lifecycle.steps).toEqual([
      {
        id: 'fetch-remote-base',
        status: 'succeeded',
        startedAt: 130,
        finishedAt: 400,
        params: { base: 'origin/main' },
      },
      {
        id: 'create-worktree',
        status: 'succeeded',
        startedAt: 400,
        finishedAt: 600,
        params: { path: '/tmp/wt', branch: 'feature/x', branchCreated: true },
      },
      { id: 'copy-artifacts', status: 'pending', startedAt: null, finishedAt: null, params: {} },
      {
        id: 'push-branch',
        status: 'pending',
        startedAt: null,
        finishedAt: null,
        params: { branch: 'feature/x', remote: 'fork' },
      },
      {
        id: 'fetch-refs',
        status: 'pending',
        startedAt: null,
        finishedAt: null,
        params: { base: 'origin/main' },
      },
    ]);
  });

  it('a locally-resolvable base yields no fetch-remote-base step', () => {
    const lifecycle = buildCreationLifecycle(
      { ...input, publish: undefined },
      { status: 'succeeded', finalPath: '/tmp/wt', createdWorktree: true, createdBranch: false },
      [
        { stage: 'inspect', at: 100 },
        { stage: 'resolve-base', at: 120 },
        { stage: 'add-worktree', at: 150 },
        { stage: 'verify', at: 200 },
      ],
      250
    );
    expect(lifecycle.steps.map((step) => step.id)).toEqual([
      'create-worktree',
      'copy-artifacts',
      'fetch-refs',
    ]);
  });

  it('no preservePatterns yields no copy-artifacts step at all', () => {
    const lifecycle = buildCreationLifecycle(
      { ...input, preservePatterns: [], publish: undefined },
      { status: 'succeeded', finalPath: '/tmp/wt', createdWorktree: true, createdBranch: true },
      [
        { stage: 'inspect', at: 100 },
        { stage: 'add-worktree', at: 150 },
        { stage: 'verify', at: 200 },
      ],
      250
    );
    expect(lifecycle.steps.map((step) => step.id)).toEqual(['create-worktree', 'fetch-refs']);
  });

  it('adopting an existing worktree yields adopt-worktree and no copy-artifacts', () => {
    const lifecycle = buildCreationLifecycle(
      { ...input, publish: undefined },
      { status: 'succeeded', finalPath: '/tmp/wt', createdWorktree: false, createdBranch: false },
      [
        { stage: 'inspect', at: 100 },
        { stage: 'verify', at: 150 },
      ],
      200
    );
    expect(lifecycle.steps.map((step) => step.id)).toEqual(['adopt-worktree', 'fetch-refs']);
    expect(lifecycle.steps[0]).toMatchObject({
      status: 'succeeded',
      params: { branch: 'feature/x', path: '/tmp/wt' },
    });
  });

  it('a failed add-worktree lands as a failed create-worktree step after a good fetch', () => {
    const lifecycle = buildCreationLifecycle(
      input,
      { status: 'failed', stage: 'add-worktree', message: 'invalid reference' },
      [
        { stage: 'inspect', at: 100 },
        { stage: 'resolve-base', at: 120 },
        { stage: 'fetch-base', at: 130 },
        { stage: 'add-worktree', at: 400 },
      ],
      450
    );
    expect(lifecycle.steps).toEqual([
      {
        id: 'fetch-remote-base',
        status: 'succeeded',
        startedAt: 130,
        finishedAt: 400,
        params: { base: 'origin/main' },
      },
      {
        id: 'create-worktree',
        status: 'failed',
        startedAt: 100,
        finishedAt: 450,
        message: 'invalid reference',
        params: { path: '/tmp/wt', branch: 'feature/x' },
      },
    ]);
  });

  it('a failed fetch lands as a failed fetch-remote-base step', () => {
    const lifecycle = buildCreationLifecycle(
      input,
      { status: 'failed', stage: 'fetch-base', message: 'could not resolve host' },
      [
        { stage: 'inspect', at: 100 },
        { stage: 'resolve-base', at: 120 },
        { stage: 'fetch-base', at: 130 },
      ],
      200
    );
    expect(lifecycle.steps).toEqual([
      {
        id: 'fetch-remote-base',
        status: 'failed',
        startedAt: 120,
        finishedAt: 200,
        message: 'could not resolve host',
        params: { base: 'origin/main' },
      },
    ]);
  });
});

describe('buildCreationLifecycle with gitSetup', () => {
  const gitSetupInput: CreateWorktreeInput = {
    workspaceId: 'ws-2',
    repositoryId: 'repo-1',
    branch: 'pr/7/fix',
    path: '/tmp/pr-wt',
    preservePatterns: [],
    gitSetup: {
      fetchBranch: { remote: 'origin', sourceRef: 'refs/pull/7/head' },
      upstream: { remote: 'origin', mergeRef: 'refs/pull/7/head' },
      breadcrumb: { prUrl: 'https://github.com/acme/repo/pull/7' },
    },
  };

  it('a fresh gitSetup creation yields fetch-branch and configure-branch steps in order', () => {
    const lifecycle = buildCreationLifecycle(
      gitSetupInput,
      {
        status: 'succeeded',
        finalPath: '/tmp/pr-wt',
        createdWorktree: true,
        createdBranch: true,
      },
      [
        { stage: 'inspect', at: 100 },
        { stage: 'fetch-branch', at: 120 },
        { stage: 'add-worktree', at: 300 },
        { stage: 'configure-branch', at: 400 },
        { stage: 'verify', at: 450 },
      ],
      500
    );
    expect(lifecycle.steps).toEqual([
      {
        id: 'fetch-branch',
        status: 'succeeded',
        startedAt: 120,
        finishedAt: 300,
        params: { branch: 'pr/7/fix', remote: 'origin', source: 'refs/pull/7/head' },
      },
      {
        id: 'create-worktree',
        status: 'succeeded',
        startedAt: 300,
        finishedAt: 500,
        params: { path: '/tmp/pr-wt', branch: 'pr/7/fix', branchCreated: true },
      },
      {
        id: 'configure-branch',
        status: 'succeeded',
        startedAt: 400,
        finishedAt: 450,
        params: { branch: 'pr/7/fix' },
      },
    ]);
    // No baseRef, nothing to freshen: fetch-refs never applies.
    expect(lifecycle.steps.some((step) => step.id === 'fetch-refs')).toBe(false);
  });

  it('a reused branch yields a skipped fetch-branch step and configure-branch still runs', () => {
    const lifecycle = buildCreationLifecycle(
      gitSetupInput,
      {
        status: 'succeeded',
        finalPath: '/tmp/pr-wt',
        createdWorktree: true,
        createdBranch: false,
      },
      [
        { stage: 'inspect', at: 100 },
        { stage: 'add-worktree', at: 150 },
        { stage: 'configure-branch', at: 200 },
        { stage: 'verify', at: 250 },
      ],
      300
    );
    expect(lifecycle.steps.map((step) => step.id)).toEqual([
      'fetch-branch',
      'create-worktree',
      'configure-branch',
    ]);
    expect(lifecycle.steps[0]).toMatchObject({ status: 'skipped', startedAt: null });
    expect(lifecycle.steps[0]!.message).toBeDefined();
    expect(lifecycle.steps[2]).toMatchObject({ status: 'succeeded' });
  });

  it('an adopted worktree with gitSetup yields adopt, skipped fetch, and configure', () => {
    const lifecycle = buildCreationLifecycle(
      gitSetupInput,
      {
        status: 'succeeded',
        finalPath: '/tmp/pr-wt',
        createdWorktree: false,
        createdBranch: false,
      },
      [
        { stage: 'inspect', at: 100 },
        { stage: 'configure-branch', at: 150 },
        { stage: 'verify', at: 200 },
      ],
      250
    );
    expect(lifecycle.steps.map((step) => step.id)).toEqual([
      'adopt-worktree',
      'fetch-branch',
      'configure-branch',
    ]);
    expect(lifecycle.steps[1]).toMatchObject({ status: 'skipped' });
  });

  it('a failed fetch lands as a failed fetch-branch step', () => {
    const lifecycle = buildCreationLifecycle(
      gitSetupInput,
      { status: 'failed', stage: 'fetch-branch', message: 'couldn\u2019t find remote ref' },
      [
        { stage: 'inspect', at: 100 },
        { stage: 'fetch-branch', at: 120 },
      ],
      200
    );
    expect(lifecycle.steps).toEqual([
      {
        id: 'fetch-branch',
        status: 'failed',
        startedAt: 120,
        finishedAt: 200,
        message: 'couldn\u2019t find remote ref',
        params: { branch: 'pr/7/fix', remote: 'origin', source: 'refs/pull/7/head' },
      },
    ]);
  });

  it('a failed configure-branch keeps the succeeded fetch-branch step in the timeline', () => {
    const lifecycle = buildCreationLifecycle(
      gitSetupInput,
      { status: 'failed', stage: 'configure-branch', message: 'could not lock config file' },
      [
        { stage: 'inspect', at: 100 },
        { stage: 'fetch-branch', at: 120 },
        { stage: 'add-worktree', at: 300 },
        { stage: 'configure-branch', at: 400 },
      ],
      450
    );
    expect(lifecycle.steps).toEqual([
      {
        id: 'fetch-branch',
        status: 'succeeded',
        startedAt: 120,
        finishedAt: 300,
        params: { branch: 'pr/7/fix', remote: 'origin', source: 'refs/pull/7/head' },
      },
      {
        id: 'configure-branch',
        status: 'failed',
        startedAt: 400,
        finishedAt: 450,
        message: 'could not lock config file',
        params: { branch: 'pr/7/fix' },
      },
    ]);
  });
});

describe('withLifecycleStep', () => {
  it('inserts new steps in canonical order and replaces existing ones in place', () => {
    const base = buildCreationLifecycle(
      { ...input, publish: undefined },
      { status: 'succeeded', finalPath: '/tmp/wt', createdWorktree: true, createdBranch: true },
      [{ stage: 'inspect', at: 100 }],
      200
    );
    const withRun = withLifecycleStep(base, {
      id: 'run',
      status: 'running',
      startedAt: 300,
      finishedAt: null,
      params: {},
    });
    expect(withRun.steps.map((step) => step.id)).toEqual([
      'create-worktree',
      'copy-artifacts',
      'fetch-refs',
      'run',
    ]);
    const replaced = withLifecycleStep(withRun, {
      id: 'copy-artifacts',
      status: 'succeeded',
      startedAt: 210,
      finishedAt: 250,
      params: { fileCount: 3 },
    });
    expect(replaced.steps.map((step) => step.id)).toEqual(withRun.steps.map((step) => step.id));
    expect(replaced.steps[1]).toMatchObject({ status: 'succeeded', params: { fileCount: 3 } });
  });
});

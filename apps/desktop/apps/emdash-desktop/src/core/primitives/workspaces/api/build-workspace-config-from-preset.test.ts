import { describe, expect, it } from 'vitest';
import type { GitBranchRef } from '@core/primitives/git/api';
import type { PullRequest } from '@root/src/core/services/pull-requests/api';
import { buildWorkspaceConfigFromPreset } from './build-workspace-config-from-preset';
import type { PresetContext } from './workspace-presets';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const mainBranch: GitBranchRef = { type: 'local', branch: 'main' };

function makePR(
  overrides: Partial<
    Pick<PullRequest, 'identifier' | 'headRepositoryUrl' | 'repositoryUrl' | 'headRefName'>
  > = {}
): PullRequest {
  return {
    url: 'https://github.com/org/repo/pull/42',
    provider: 'github',
    repositoryUrl: 'https://github.com/org/repo',
    baseRefName: 'main',
    baseRefOid: 'abc',
    headRepositoryUrl: overrides.headRepositoryUrl ?? 'https://github.com/org/repo',
    headRefName: overrides.headRefName ?? 'feat/my-pr',
    headRefOid: 'def',
    identifier: overrides.identifier ?? '#42',
    title: 'My PR',
    description: null,
    status: 'open',
    isDraft: false,
    additions: null,
    deletions: null,
    changedFiles: null,
    commitCount: null,
    mergeableStatus: null,
    mergeStateStatus: null,
    reviewDecision: null,
    createdAt: '2026-01-01',
    updatedAt: '2026-01-01',
    author: null,
    labels: [],
    assignees: [],
    checks: [],
  };
}

const baseCtx: PresetContext = {
  defaultBranch: mainBranch,
  repositoryWorkspaceId: 'ws-repo',
};

// ─── new-worktree ─────────────────────────────────────────────────────────────

describe('new-worktree preset', () => {
  it('produces create-branch git setup with defaultBranch as fromBranch', () => {
    const cfg = buildWorkspaceConfigFromPreset('new-worktree', baseCtx, { branchName: 'feat/x' });
    expect(cfg.version).toBe('2');
    expect(cfg.git).toMatchObject({
      kind: 'create-branch',
      branchName: 'feat/x',
      fromBranch: mainBranch,
      pushBranch: true,
    });
    expect(cfg.workspace).toEqual({ kind: 'new-worktree' });
  });

  it('uses overrides.fromBranch when provided', () => {
    const remote: GitBranchRef = {
      type: 'remote',
      branch: 'develop',
      remote: { name: 'origin', url: 'u' },
    };
    const cfg = buildWorkspaceConfigFromPreset('new-worktree', baseCtx, {
      fromBranch: remote,
      branchName: 'feat/y',
    });
    expect(cfg.git).toMatchObject({ kind: 'create-branch', fromBranch: remote });
  });

  it('allows pushBranch=false via overrides', () => {
    const cfg = buildWorkspaceConfigFromPreset('new-worktree', baseCtx, { pushBranch: false });
    expect(cfg.git).toMatchObject({ pushBranch: false });
  });

  it('produces use-branch git setup when createBranch=false', () => {
    const cfg = buildWorkspaceConfigFromPreset('new-worktree', baseCtx, { createBranch: false });
    expect(cfg.git).toMatchObject({ kind: 'use-branch', branchName: 'main' });
    expect(cfg.workspace).toEqual({ kind: 'new-worktree' });
  });

  it('throws when neither defaultBranch nor fromBranch override is available', () => {
    expect(() =>
      buildWorkspaceConfigFromPreset('new-worktree', { repositoryWorkspaceId: 'ws-repo' })
    ).toThrow('fromBranch');
  });
});

// ─── repo-root ────────────────────────────────────────────────────────────────

describe('repo-root preset', () => {
  it('produces repository-instance workspace when repositoryWorkspaceId is set', () => {
    const cfg = buildWorkspaceConfigFromPreset('repo-root', baseCtx);
    expect(cfg.git).toEqual({ kind: 'none' });
    expect(cfg.workspace).toEqual({ kind: 'repository-instance', workspaceId: 'ws-repo' });
  });

  it('falls back to new-worktree when repositoryWorkspaceId is missing (pre-mount)', () => {
    const cfg = buildWorkspaceConfigFromPreset('repo-root', {});
    expect(cfg.git).toEqual({ kind: 'none' });
    expect(cfg.workspace).toEqual({ kind: 'new-worktree' });
  });
});

// ─── use-existing ─────────────────────────────────────────────────────────────

describe('use-existing preset', () => {
  it('uses existingWorkspaceId when provided', () => {
    const cfg = buildWorkspaceConfigFromPreset('use-existing', {
      ...baseCtx,
      existingWorkspaceId: 'ws-feat',
    });
    expect(cfg.workspace).toEqual({ kind: 'repository-instance', workspaceId: 'ws-feat' });
  });

  it('falls back to repositoryWorkspaceId when existingWorkspaceId is absent', () => {
    const cfg = buildWorkspaceConfigFromPreset('use-existing', baseCtx);
    expect(cfg.workspace).toEqual({ kind: 'repository-instance', workspaceId: 'ws-repo' });
  });

  it('throws when neither existingWorkspaceId nor repositoryWorkspaceId is set', () => {
    expect(() => buildWorkspaceConfigFromPreset('use-existing', {})).toThrow('existingWorkspaceId');
  });
});

// ─── checkout-pr ─────────────────────────────────────────────────────────────

describe('checkout-pr preset', () => {
  it('produces pr-branch setup with no taskBranch for a same-repo PR', () => {
    const pr = makePR();
    const cfg = buildWorkspaceConfigFromPreset('checkout-pr', { pr });
    expect(cfg.git).toMatchObject({
      kind: 'pr-branch',
      prUrl: 'https://github.com/org/repo/pull/42',
      prNumber: 42,
      headBranch: 'feat/my-pr',
      headRepositoryUrl: 'https://github.com/org/repo',
      isFork: false,
    });
    expect((cfg.git as { taskBranch?: string }).taskBranch).toBeUndefined();
    expect(cfg.workspace).toEqual({ kind: 'new-worktree' });
  });

  it('sets isFork=true for cross-repo PRs', () => {
    const pr = makePR({ headRepositoryUrl: 'https://github.com/fork/repo' });
    const cfg = buildWorkspaceConfigFromPreset('checkout-pr', { pr });
    expect(cfg.git).toMatchObject({ isFork: true });
  });

  it('handles missing PR identifier (prNumber = 0)', () => {
    const pr = { ...makePR(), identifier: null };
    const cfg = buildWorkspaceConfigFromPreset('checkout-pr', { pr });
    expect((cfg.git as { prNumber: number }).prNumber).toBe(0);
  });

  it('throws when no PR is provided', () => {
    expect(() => buildWorkspaceConfigFromPreset('checkout-pr', {})).toThrow('PR');
  });
});

// ─── pr-new-branch ───────────────────────────────────────────────────────────

describe('pr-new-branch preset', () => {
  it('includes taskBranch from overrides.taskBranch', () => {
    const pr = makePR();
    const cfg = buildWorkspaceConfigFromPreset('pr-new-branch', { pr }, { taskBranch: 'task/42' });
    expect(cfg.git).toMatchObject({
      kind: 'pr-branch',
      prUrl: 'https://github.com/org/repo/pull/42',
      prNumber: 42,
      taskBranch: 'task/42',
      pushBranch: true,
    });
  });

  it('falls back to overrides.branchName when taskBranch is absent', () => {
    const pr = makePR();
    const cfg = buildWorkspaceConfigFromPreset(
      'pr-new-branch',
      { pr },
      { branchName: 'feat/branch' }
    );
    expect((cfg.git as { taskBranch: string }).taskBranch).toBe('feat/branch');
  });

  it('defaults taskBranch to empty string when no override provided', () => {
    const pr = makePR();
    const cfg = buildWorkspaceConfigFromPreset('pr-new-branch', { pr });
    expect((cfg.git as { taskBranch: string }).taskBranch).toBe('');
  });

  it('throws when no PR is provided', () => {
    expect(() => buildWorkspaceConfigFromPreset('pr-new-branch', {})).toThrow('PR');
  });
});

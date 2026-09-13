import { describe, expect, it } from 'vitest';
import { compileWorktreeGitPlan } from './compile-worktree-git-plan';
import { describeWorktreeGitPlan } from './describe-worktree-git-plan';
import type { WorkspaceConfig } from './workspace-config';

type GitHalf = Exclude<WorkspaceConfig['git'], { kind: 'none' }>;

const context = { baseRemote: 'origin', pushRemote: 'fork' };

function prBranch(overrides: Partial<Extract<GitHalf, { kind: 'pr-branch' }>> = {}): GitHalf {
  return {
    kind: 'pr-branch',
    prUrl: 'https://github.com/org/repo/pull/42',
    prNumber: 42,
    headBranch: 'feat/my-pr',
    headRepositoryUrl: 'https://github.com/org/repo',
    isFork: false,
    ...overrides,
  };
}

/** The preview steps for a config, exactly as the modal derives them. */
function stepsFor(git: GitHalf, ctx = context, preservePatterns: readonly string[] = ['.env']) {
  return describeWorktreeGitPlan(compileWorktreeGitPlan(git, ctx), { preservePatterns });
}

// ─── Plain new-branch (create-branch preset) ─────────────────────────────────

describe('describeWorktreeGitPlan — create-branch', () => {
  it('shows create-worktree, copy-artifacts, and push-branch for a pushed new branch', () => {
    const steps = stepsFor({
      kind: 'create-branch',
      branchName: 'feature/x',
      fromBranch: { type: 'local', branch: 'main' },
      pushBranch: true,
    });
    expect(steps.map((step) => step.id)).toEqual([
      'create-worktree',
      'copy-artifacts',
      'push-branch',
    ]);
  });

  it('omits push-branch when the branch is not pushed', () => {
    const steps = stepsFor({
      kind: 'create-branch',
      branchName: 'feature/x',
      fromBranch: { type: 'local', branch: 'main' },
      pushBranch: false,
    });
    expect(steps.map((step) => step.id)).toEqual(['create-worktree', 'copy-artifacts']);
  });

  it('omits copy-artifacts when the project defines no preservePatterns (pipeline guard)', () => {
    const steps = stepsFor(
      {
        kind: 'create-branch',
        branchName: 'feature/x',
        fromBranch: { type: 'local', branch: 'main' },
        pushBranch: false,
      },
      context,
      []
    );
    expect(steps.map((step) => step.id)).toEqual(['create-worktree']);
  });

  it('describes the new branch and its base ref', () => {
    const steps = stepsFor({
      kind: 'create-branch',
      branchName: 'feature/x',
      fromBranch: { type: 'remote', branch: 'develop', remote: { name: 'upstream', url: 'u' } },
    });
    const create = steps.find((step) => step.id === 'create-worktree');
    expect(create?.title).toBe('Create worktree');
    expect(create?.description).toBe(
      'Create a worktree on new branch feature/x based on upstream/develop'
    );
  });

  it('describes the push with upstream tracking', () => {
    const steps = stepsFor({
      kind: 'create-branch',
      branchName: 'feature/x',
      fromBranch: { type: 'local', branch: 'main' },
      pushBranch: true,
    });
    const push = steps.find((step) => step.id === 'push-branch');
    expect(push?.title).toBe('Push branch');
    expect(push?.description).toBe('Push feature/x to fork and set upstream tracking');
  });
});

// ─── Existing-branch (use-branch preset) ─────────────────────────────────────

describe('describeWorktreeGitPlan — use-branch', () => {
  it('shows a plain checkout of the existing branch', () => {
    const steps = stepsFor({ kind: 'use-branch', branchName: 'main' });
    expect(steps.map((step) => step.id)).toEqual(['create-worktree', 'copy-artifacts']);
    expect(steps[0]?.description).toBe('Create a worktree on branch main');
  });
});

// ─── checkout-pr, same-repo ──────────────────────────────────────────────────

describe('describeWorktreeGitPlan — checkout-pr, same-repo PR', () => {
  it('shows fetch-branch, create-worktree, configure-branch, copy-artifacts', () => {
    const steps = stepsFor(prBranch());
    expect(steps.map((step) => step.id)).toEqual([
      'fetch-branch',
      'create-worktree',
      'configure-branch',
      'copy-artifacts',
    ]);
  });

  it('describes the head-branch fetch and upstream tracking', () => {
    const steps = stepsFor(prBranch());
    expect(steps[0]?.title).toBe('Fetch branch');
    expect(steps[0]?.description).toBe('Fetch refs/heads/feat/my-pr from origin into feat/my-pr');
    expect(steps[1]?.description).toBe('Create a worktree on the fetched branch feat/my-pr');
    const configure = steps.find((step) => step.id === 'configure-branch');
    expect(configure?.title).toBe('Configure branch');
    expect(configure?.description).toBe('Set feat/my-pr to track refs/heads/feat/my-pr on origin');
  });
});

// ─── checkout-pr, fork (acceptance: namespaced branch + PR-ref fetch) ────────

describe('describeWorktreeGitPlan — checkout-pr, fork PR', () => {
  const fork = () =>
    prBranch({
      isFork: true,
      headRepositoryUrl: 'https://github.com/contributor/repo',
      prNumber: 7,
      headBranch: 'fix/thing',
    });

  it('shows the PR-ref fetch into the namespaced local branch', () => {
    const steps = stepsFor(fork());
    expect(steps.map((step) => step.id)).toEqual([
      'fetch-branch',
      'create-worktree',
      'configure-branch',
      'copy-artifacts',
    ]);
    expect(steps[0]?.description).toBe('Fetch refs/pull/7/head from origin into pr/7/fix/thing');
    expect(steps[1]?.description).toBe('Create a worktree on the fetched branch pr/7/fix/thing');
  });

  it('describes the PR-ref upstream (divergence source; the forge rejects pushes)', () => {
    const configure = stepsFor(fork()).find((step) => step.id === 'configure-branch');
    expect(configure?.description).toBe('Set pr/7/fix/thing to track refs/pull/7/head on origin');
  });

  it('uses the compiled remote, not a hardcoded origin', () => {
    const steps = stepsFor(fork(), { baseRemote: 'company', pushRemote: 'fork' });
    expect(steps[0]?.description).toBe('Fetch refs/pull/7/head from company into pr/7/fix/thing');
  });
});

// ─── pr-new-branch ───────────────────────────────────────────────────────────

describe('describeWorktreeGitPlan — pr-new-branch', () => {
  it('shows the PR-ref fetch into the task branch plus the background push', () => {
    const steps = stepsFor(prBranch({ taskBranch: 'task/on-top', pushBranch: true }));
    expect(steps.map((step) => step.id)).toEqual([
      'fetch-branch',
      'create-worktree',
      'configure-branch',
      'copy-artifacts',
      'push-branch',
    ]);
    expect(steps[0]?.description).toBe('Fetch refs/pull/42/head from origin into task/on-top');
  });

  it('describes the breadcrumb-only configure step (no upstream on the task branch)', () => {
    const configure = stepsFor(prBranch({ taskBranch: 'task/on-top' })).find(
      (step) => step.id === 'configure-branch'
    );
    expect(configure?.description).toBe('Record the pull request association on task/on-top');
  });

  it('omits configure-branch when the plan carries neither upstream nor breadcrumb', () => {
    // Old fork configs without a stored prUrl compile without a breadcrumb.
    const steps = stepsFor(
      prBranch({
        prUrl: undefined,
        isFork: true,
        headRepositoryUrl: 'https://github.com/contributor/repo',
        taskBranch: 'task/on-top',
      })
    );
    expect(steps.map((step) => step.id)).toEqual([
      'fetch-branch',
      'create-worktree',
      'copy-artifacts',
    ]);
  });

  it('omits push-branch when pushing is disabled', () => {
    const steps = stepsFor(prBranch({ taskBranch: 'task/on-top', pushBranch: false }));
    expect(steps.map((step) => step.id)).not.toContain('push-branch');
  });
});

import { describe, expect, it } from 'vitest';
import { compileWorktreeGitPlan } from './compile-worktree-git-plan';
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

// ─── Non-PR presets: outputs equivalent to the retired compileRegistryGitSpec ─

describe('compileWorktreeGitPlan — non-PR git configs', () => {
  it('compiles create-branch from a local source branch', () => {
    const plan = compileWorktreeGitPlan(
      {
        kind: 'create-branch',
        branchName: 'feature/x',
        fromBranch: { type: 'local', branch: 'main' },
        pushBranch: true,
      },
      context
    );
    expect(plan).toEqual({ branch: 'feature/x', baseRef: 'main', publish: { remote: 'fork' } });
  });

  it('compiles create-branch from a remote source branch into a remote-qualified baseRef', () => {
    const plan = compileWorktreeGitPlan(
      {
        kind: 'create-branch',
        branchName: 'feature/x',
        fromBranch: { type: 'remote', branch: 'develop', remote: { name: 'upstream', url: 'u' } },
      },
      context
    );
    expect(plan).toEqual({ branch: 'feature/x', baseRef: 'upstream/develop' });
  });

  it('compiles use-branch with the branch as its own base and no push', () => {
    const plan = compileWorktreeGitPlan({ kind: 'use-branch', branchName: 'main' }, context);
    expect(plan).toEqual({ branch: 'main', baseRef: 'main' });
  });

  it('emits no gitSetup for non-PR configs', () => {
    const plan = compileWorktreeGitPlan(
      {
        kind: 'create-branch',
        branchName: 'feature/x',
        fromBranch: { type: 'local', branch: 'main' },
      },
      context
    );
    expect(plan.gitSetup).toBeUndefined();
  });
});

// ─── checkout-pr, same-repo (case A: real branch, commit-and-push preserved) ─

describe('compileWorktreeGitPlan — checkout-pr, same-repo PR', () => {
  it('fetches the head branch into a local branch of the same name with upstream tracking', () => {
    const plan = compileWorktreeGitPlan(prBranch(), context);
    expect(plan).toEqual({
      branch: 'feat/my-pr',
      gitSetup: {
        fetchBranch: { remote: 'origin', sourceRef: 'refs/heads/feat/my-pr' },
        upstream: { remote: 'origin', mergeRef: 'refs/heads/feat/my-pr' },
        breadcrumb: { prUrl: 'https://github.com/org/repo/pull/42' },
        followRef: true,
      },
    });
  });

  it('omits baseRef (fetchBranch materializes the branch)', () => {
    const plan = compileWorktreeGitPlan(prBranch(), context);
    expect(plan.baseRef).toBeUndefined();
  });

  it('does not publish when the config sets pushBranch without a taskBranch', () => {
    const plan = compileWorktreeGitPlan(prBranch({ pushBranch: true }), context);
    expect(plan.publish).toBeUndefined();
  });
});

// ─── checkout-pr, fork (case B: review-first, namespaced) ────────────────────

describe('compileWorktreeGitPlan — checkout-pr, fork PR', () => {
  const fork = () =>
    prBranch({
      isFork: true,
      headRepositoryUrl: 'https://github.com/fork/repo',
    });

  it('fetches refs/pull/<N>/head into the namespaced pr/<N>/<headBranch> branch', () => {
    const plan = compileWorktreeGitPlan(fork(), context);
    expect(plan).toEqual({
      branch: 'pr/42/feat/my-pr',
      gitSetup: {
        fetchBranch: { remote: 'origin', sourceRef: 'refs/pull/42/head' },
        upstream: { remote: 'origin', mergeRef: 'refs/pull/42/head' },
        breadcrumb: { prUrl: 'https://github.com/org/repo/pull/42' },
        followRef: true,
      },
    });
  });

  it('does not publish a fork checkout without a task branch', () => {
    const plan = compileWorktreeGitPlan(fork(), context);
    expect(plan.publish).toBeUndefined();
  });
});

// ─── pr-new-branch (case C: uniform, no fork special-casing) ─────────────────

describe('compileWorktreeGitPlan — pr-new-branch', () => {
  it('fetches refs/pull/<N>/head into the task branch with no gitSetup upstream (same-repo)', () => {
    const plan = compileWorktreeGitPlan(
      prBranch({ taskBranch: 'task/42', pushBranch: true }),
      context
    );
    expect(plan).toEqual({
      branch: 'task/42',
      publish: { remote: 'fork' },
      gitSetup: {
        fetchBranch: { remote: 'origin', sourceRef: 'refs/pull/42/head' },
        breadcrumb: { prUrl: 'https://github.com/org/repo/pull/42' },
        followRef: true,
      },
    });
  });

  it('compiles identically for a fork PR (uniform case)', () => {
    const samerepo = compileWorktreeGitPlan(
      prBranch({ taskBranch: 'task/42', pushBranch: true }),
      context
    );
    const fork = compileWorktreeGitPlan(
      prBranch({
        taskBranch: 'task/42',
        pushBranch: true,
        isFork: true,
        headRepositoryUrl: 'https://github.com/fork/repo',
      }),
      context
    );
    expect(fork).toEqual(samerepo);
  });

  it('publishes only when pushBranch is true and a task branch exists', () => {
    expect(compileWorktreeGitPlan(prBranch({ taskBranch: 't' }), context).publish).toBeUndefined();
    expect(
      compileWorktreeGitPlan(prBranch({ taskBranch: 't', pushBranch: false }), context).publish
    ).toBeUndefined();
    expect(
      compileWorktreeGitPlan(prBranch({ taskBranch: 't', pushBranch: true }), context).publish
    ).toEqual({ remote: 'fork' });
  });
});

// ─── prUrl: canonical when present, derived on read for old configs ──────────

describe('compileWorktreeGitPlan — prUrl and breadcrumb', () => {
  it('uses the stored prUrl verbatim as the breadcrumb payload', () => {
    const plan = compileWorktreeGitPlan(
      prBranch({ prUrl: 'https://github.com/org/repo/pull/42' }),
      context
    );
    expect(plan.gitSetup?.breadcrumb).toEqual({ prUrl: 'https://github.com/org/repo/pull/42' });
  });

  it('derives the PR URL from headRepositoryUrl for old same-repo configs without prUrl', () => {
    const plan = compileWorktreeGitPlan(prBranch({ prUrl: undefined }), context);
    expect(plan.gitSetup?.breadcrumb).toEqual({ prUrl: 'https://github.com/org/repo/pull/42' });
  });

  it('normalizes the repository URL when deriving (e.g. trailing .git)', () => {
    const plan = compileWorktreeGitPlan(
      prBranch({ prUrl: undefined, headRepositoryUrl: 'https://github.com/org/repo.git' }),
      context
    );
    expect(plan.gitSetup?.breadcrumb).toEqual({ prUrl: 'https://github.com/org/repo/pull/42' });
  });

  it('omits the breadcrumb for old fork configs without prUrl (head URL is the fork, not the PR home)', () => {
    const plan = compileWorktreeGitPlan(
      prBranch({
        prUrl: undefined,
        isFork: true,
        headRepositoryUrl: 'https://github.com/fork/repo',
      }),
      context
    );
    expect(plan.gitSetup?.breadcrumb).toBeUndefined();
    // The fetch itself is unaffected.
    expect(plan.gitSetup?.fetchBranch).toEqual({
      remote: 'origin',
      sourceRef: 'refs/pull/42/head',
    });
  });

  it('omits the breadcrumb when no PR number is known (prNumber 0 placeholder)', () => {
    const plan = compileWorktreeGitPlan(prBranch({ prUrl: undefined, prNumber: 0 }), context);
    expect(plan.gitSetup?.breadcrumb).toBeUndefined();
  });
});

// ─── Remote threading ────────────────────────────────────────────────────────

describe('compileWorktreeGitPlan — remote name', () => {
  it('threads the provided base remote into fetchBranch and upstream', () => {
    const plan = compileWorktreeGitPlan(prBranch(), {
      baseRemote: 'company',
      pushRemote: 'fork',
    });
    expect(plan.gitSetup?.fetchBranch?.remote).toBe('company');
    expect(plan.gitSetup?.upstream?.remote).toBe('company');
  });

  it('keeps the publication target distinct from the base remote', () => {
    const plan = compileWorktreeGitPlan(
      {
        kind: 'create-branch',
        branchName: 'feature/x',
        fromBranch: { type: 'remote', branch: 'main', remote: { name: 'origin', url: 'u' } },
        pushBranch: true,
      },
      context
    );
    expect(plan.baseRef).toBe('origin/main');
    expect(plan.publish).toEqual({ remote: 'fork' });
  });

  it('rejects requested publication when no push remote resolves', () => {
    expect(() =>
      compileWorktreeGitPlan(
        {
          kind: 'create-branch',
          branchName: 'feature/x',
          fromBranch: { type: 'local', branch: 'main' },
          pushBranch: true,
        },
        { baseRemote: null, pushRemote: null }
      )
    ).toThrow('no push remote');
  });
});

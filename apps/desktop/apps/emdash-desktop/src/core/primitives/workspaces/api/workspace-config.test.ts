import { describe, expect, it } from 'vitest';
import { workspaceConfig } from './workspace-config';

// prUrl is additive on the pr-branch git config (pr-workspace-model migration
// decision): old stored configs without it must keep parsing at the same version,
// and new configs carry it through untouched. Derivation for old configs happens on
// read in `compileWorktreeGitPlan`, not here.

const storedPrBranchV2 = {
  version: '2',
  git: {
    kind: 'pr-branch',
    prNumber: 42,
    headBranch: 'feat/my-pr',
    headRepositoryUrl: 'https://github.com/org/repo',
    isFork: false,
    taskBranch: 'task/42',
    pushBranch: true,
  },
  workspace: { kind: 'new-worktree' },
};

describe('workspaceConfig versioned schema — additive prUrl', () => {
  it('parses an old v2 pr-branch config without prUrl (no version bump)', () => {
    const result = workspaceConfig.safeParse(storedPrBranchV2);
    expect(result.status).toBe('ok');
    if (result.status !== 'ok') return;
    expect(result.data.version).toBe('2');
    expect(result.data.git).toMatchObject({ kind: 'pr-branch', prNumber: 42 });
    expect((result.data.git as { prUrl?: string }).prUrl).toBeUndefined();
  });

  it('round-trips a new pr-branch config carrying prUrl', () => {
    const withUrl = {
      ...storedPrBranchV2,
      git: { ...storedPrBranchV2.git, prUrl: 'https://github.com/org/repo/pull/42' },
    };
    const result = workspaceConfig.safeParse(withUrl);
    expect(result.status).toBe('ok');
    if (result.status !== 'ok') return;
    expect((result.data.git as { prUrl?: string }).prUrl).toBe(
      'https://github.com/org/repo/pull/42'
    );
  });

  it('upgrades a v1 pr-branch config (no prUrl) through the existing v1 → v2 upcast', () => {
    const v1 = {
      version: '1',
      git: storedPrBranchV2.git,
      workspace: { host: 'local' },
    };
    const result = workspaceConfig.safeParse(v1);
    expect(result.status).toBe('ok');
    if (result.status !== 'ok') return;
    expect(result.data.version).toBe('2');
    expect(result.data.git).toMatchObject({ kind: 'pr-branch', headBranch: 'feat/my-pr' });
    expect((result.data.git as { prUrl?: string }).prUrl).toBeUndefined();
  });
});

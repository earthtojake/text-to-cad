import { describe, expect, it } from 'vitest';
import { getProvisionedWorkspaceBranch } from '@core/features/workspaces/api/node/workspace-branch';
import type { WorkspaceConfig } from '@core/primitives/workspaces/api';

const createBranchConfig: WorkspaceConfig = {
  version: '2',
  git: {
    kind: 'create-branch',
    branchName: 'task/provisioned',
    fromBranch: { type: 'local', branch: 'main' },
  },
  workspace: { kind: 'new-worktree' },
};

describe('workspace branch metadata', () => {
  it('does not treat a repository row as owning a provisioned branch', () => {
    expect(getProvisionedWorkspaceBranch({ kind: 'repository', config: null })).toBeNull();
  });

  it('does not derive provisioned branch from repository workspace config', () => {
    expect(
      getProvisionedWorkspaceBranch({ kind: 'repository', config: createBranchConfig })
    ).toBeNull();
  });

  it('does not derive provisioned branch for directory rows', () => {
    expect(
      getProvisionedWorkspaceBranch({ kind: 'directory', config: createBranchConfig })
    ).toBeNull();
  });

  it('derives the provisioned worktree branch from config', () => {
    expect(getProvisionedWorkspaceBranch({ kind: 'worktree', config: createBranchConfig })).toBe(
      'task/provisioned'
    );
  });

  it('does not treat a worktree row with git none as owning a branch', () => {
    const config: WorkspaceConfig = {
      version: '2',
      git: { kind: 'none' },
      workspace: { kind: 'new-worktree' },
    };

    expect(getProvisionedWorkspaceBranch({ kind: 'worktree', config })).toBeNull();
  });

  it('returns null when config is missing', () => {
    expect(getProvisionedWorkspaceBranch({ kind: null, config: null })).toBeNull();
  });
});

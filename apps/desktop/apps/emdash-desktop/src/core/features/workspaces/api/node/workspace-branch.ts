import type { GitSetup } from '@core/primitives/tasks/api';
import type { WorkspaceConfig } from '@core/primitives/workspaces/api';
import type { WorkspaceKind } from '@core/primitives/workspaces/api';

type WorkspaceBranchRow = {
  kind?: WorkspaceKind | string | null;
  config?: WorkspaceConfig | null;
};

export function deriveBranchName(git: GitSetup): string | null {
  switch (git.kind) {
    case 'none':
      return null;
    case 'use-branch':
    case 'create-branch':
      return git.branchName;
    case 'pr-branch':
      return git.taskBranch ?? git.headBranch;
  }
}

/** Branch identity lives in `workspaces.config` — only worktrees carry one. */
export function getProvisionedWorkspaceBranch(workspace: WorkspaceBranchRow): string | null {
  if (workspace.kind === 'repository' || workspace.kind === 'directory') return null;
  if (workspace.config) return deriveBranchName(workspace.config.git);
  return null;
}

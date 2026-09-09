import type { GitBranchRef } from '@core/primitives/git/api';
import type { PullRequest } from '@root/src/core/services/pull-requests/api';

// ---------------------------------------------------------------------------
// Preset IDs
// ---------------------------------------------------------------------------

export type WorkspacePresetId =
  | 'new-worktree'
  | 'checkout-pr'
  | 'pr-new-branch'
  | 'use-existing'
  | 'repo-root';

// ---------------------------------------------------------------------------
// Preset metadata — static catalogue, no build logic
// ---------------------------------------------------------------------------

export type WorkspacePresetMeta = {
  id: WorkspacePresetId;
  label: string;
  description: string;
  /** Only show this preset when a PR is linked in the creation context. */
  requiresPR: boolean;
  /** Requires the project repository to have at least one commit. */
  requiresCommits: boolean;
};

export const WORKSPACE_PRESETS: WorkspacePresetMeta[] = [
  {
    id: 'new-worktree',
    label: 'Create new worktree',
    description: 'Create an isolated worktree on a branch',
    requiresPR: false,
    requiresCommits: true,
  },
  {
    id: 'repo-root',
    label: 'Use the repository directory',
    description: 'Work directly in the project directory (no worktree)',
    requiresPR: false,
    requiresCommits: false,
  },
  {
    id: 'use-existing',
    label: 'Reuse an existing workspace',
    description: 'Reuse an existing worktree or repository workspace',
    requiresPR: false,
    requiresCommits: false,
  },
  {
    id: 'checkout-pr',
    label: 'Checkout PR in worktree',
    description: 'Fetch and review a pull request in its own worktree',
    requiresPR: true,
    requiresCommits: true,
  },
  {
    id: 'pr-new-branch',
    label: 'Create a new branch from a PR in worktree',
    description: 'Create a new branch on top of the PR head for your changes',
    requiresPR: true,
    requiresCommits: true,
  },
];

// ---------------------------------------------------------------------------
// Context provided at creation time to build a WorkspaceConfig
// ---------------------------------------------------------------------------

export type PresetContext = {
  /** Default branch of the project repository. */
  defaultBranch?: GitBranchRef;
  /** Current HEAD branch name on the project. */
  currentBranch?: string;
  /** Linked PR, required for checkout-pr and pr-new-branch presets. */
  pr?: PullRequest;
  /**
   * The workspace ID of the project's repository-root workspace.
   * Required for repo-root and use-existing presets.
   */
  repositoryWorkspaceId?: string;
  /**
   * An explicitly selected existing workspace ID.
   * Required for use-existing preset.
   */
  existingWorkspaceId?: string;
};

// ---------------------------------------------------------------------------
// Overrides — user-customizable fields for the selected preset
// ---------------------------------------------------------------------------

export type PresetOverrides = {
  /** New branch name (new-worktree, pr-new-branch). */
  branchName?: string;
  /** Source branch to branch from or check out (new-worktree). */
  fromBranch?: GitBranchRef;
  /** Whether to push the branch to remote after creation. */
  pushBranch?: boolean;
  /** Task-specific branch created on top of the PR head (pr-new-branch). */
  taskBranch?: string;
  /** When false, checkout fromBranch in a new worktree instead of creating a new branch (new-worktree preset). Defaults to true. */
  createBranch?: boolean;
};

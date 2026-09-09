export type WorkspaceType = 'local' | 'project-ssh';

/**
 * Describes the physical nature of a workspace directory.
 * Stored in `workspaces.kind`; the retirement migration train rewrote all
 * legacy vocabulary (`project-root`, `path`, null) into these values.
 */
export type WorkspaceKind = 'worktree' | 'repository' | 'directory';

export type WorkspaceResolution =
  | { kind: 'ready' }
  | { kind: 'needs_create' }
  | { kind: 'branch_elsewhere'; branchName: string; candidatePath: string; previousPath: string }
  | { kind: 'path_missing'; previousPath: string; branchName: string | null };

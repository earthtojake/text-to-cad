import path from 'node:path';
import { deriveWorktreePoolPath as derivePoolPath } from '@emdash/core/runtimes/workspace-registry/api';

export type DeriveWorktreePoolPathOptions = {
  worktreesRoot: string;
  repoPath: string;
};

export function defaultRepositoriesRoot(homeDirectory: string): string {
  return pathApiFor(homeDirectory).join(homeDirectory, 'hardcore', 'repositories');
}

// The built-in worktree root lives in the portable resolver module
// (`builtInWorktreeRootFor` in @core/primitives/project-settings/api) so
// placement, the settings page, and the create-task preview share one
// definition.

/**
 * Delegates to the one portable pool derivation (workspace-registry API) that
 * worktree payload compilation and the renderer previews also use.
 */
export function deriveWorktreePoolPath({
  worktreesRoot,
  repoPath,
}: DeriveWorktreePoolPathOptions): string {
  return derivePoolPath({ worktreeRoot: worktreesRoot, repoPath });
}

function pathApiFor(absolutePath: string): typeof path.posix {
  return /^[a-zA-Z]:[\\/]/u.test(absolutePath) || absolutePath.startsWith('\\\\')
    ? path.win32
    : path.posix;
}

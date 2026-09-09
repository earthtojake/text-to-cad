import { promises as fs } from 'node:fs';
import type { RegistryGitContext } from './git-context';
import { validateWorktreePath } from './worktree-path-safety';

export type DeleteWorktreeExecution = {
  /** The owning runtime's git context — budget slots and the per-worktree writer lock. */
  git: RegistryGitContext;
  repositoryPath: string;
  worktreePath: string;
  deleteBranch: boolean;
  /** Fallback branch name when the worktree is already gone from disk. */
  branchHint: string | null;
};

/**
 * The failure class is host-decided here, where the failure is understood (ADR 0006):
 * 'terminal' for structural refusals an identical retry cannot fix (path safety),
 * 'transient' for environmental git/filesystem failures a later sweep may clear.
 */
export type DeleteWorktreeExecutionResult =
  | { status: 'succeeded' }
  | { status: 'failed'; class: 'transient' | 'terminal'; message: string };

/**
 * Force-removes the worktree artifact (and optionally its branch). No dirty/unpushed
 * refusals by design — informed confirmation happens client-side from mirror
 * observations; the host executes what it is told. Path safety still applies: only
 * worktrees owned by the parent repository are removable.
 */
export async function executeDeleteWorktree(
  execution: DeleteWorktreeExecution
): Promise<DeleteWorktreeExecutionResult> {
  // Interactive tier: a user-initiated delete never waits behind background work.
  const exec = execution.git.exec(execution.repositoryPath, {
    tier: 'activation',
    repository: execution.repositoryPath,
  });

  const safe = await validateWorktreePath({
    repoPath: execution.repositoryPath,
    targetPath: execution.worktreePath,
    mutation: 'remove',
  });
  if (!safe.success) {
    return { status: 'failed', class: 'terminal', message: safe.error.message };
  }

  const branch = execution.deleteBranch
    ? ((await currentBranch(execution.git, execution.worktreePath)) ?? execution.branchHint)
    : null;

  // The writer lock (spec: git concurrency model): removal mutates this worktree's
  // checkout, so probes of it wait rather than observing a half-removed tree.
  const removal = await execution.git.locks.withWriter(
    execution.worktreePath,
    async (): Promise<DeleteWorktreeExecutionResult | null> => {
      if (await pathExists(execution.worktreePath)) {
        try {
          await exec.exec(['worktree', 'remove', '--force', execution.worktreePath]);
        } catch (error) {
          return {
            status: 'failed',
            class: 'transient',
            message: error instanceof Error ? error.message : String(error),
          };
        }
      }
      // Clears leftover admin data for worktrees whose directory vanished out-of-band.
      await exec.exec(['worktree', 'prune']).catch(() => undefined);
      return null;
    }
  );
  if (removal !== null) return removal;

  if (branch) {
    try {
      await exec.exec(['branch', '-D', branch]);
    } catch (error) {
      // A branch that is already gone satisfies the request.
      if (!/not found/iu.test(error instanceof Error ? error.message : String(error))) {
        return {
          status: 'failed',
          class: 'transient',
          message: error instanceof Error ? error.message : String(error),
        };
      }
    }
  }

  return { status: 'succeeded' };
}

async function currentBranch(
  git: RegistryGitContext,
  worktreePath: string
): Promise<string | null> {
  try {
    const result = await git.exec(worktreePath).exec(['branch', '--show-current']);
    return result.stdout.trim() || null;
  } catch {
    return null;
  }
}

async function pathExists(target: string): Promise<boolean> {
  try {
    await fs.lstat(target);
    return true;
  } catch {
    return false;
  }
}

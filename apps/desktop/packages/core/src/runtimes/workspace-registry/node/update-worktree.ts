import crypto from 'node:crypto';
import type { BoundExec } from '#services/exec/api';
import type { RegistryGitContext } from './git-context';
import { retryTransientLock, type GitWorkTier } from './git-schedule';

export type UpdateWorktreeExecution = {
  /** The owning runtime's git context — budget slots and the per-worktree writer lock. */
  git: RegistryGitContext;
  /** The owning repository's path — the scheduling key for the git budget. */
  repositoryPath: string;
  worktreePath: string;
  remote: string;
  sourceRef: string;
  /**
   * Host git budget tier for the fetch/merge subprocesses. Defaults to 'activation'
   * (a user-initiated update never waits behind background work); the autonomous
   * ref-follow pass runs at 'background' so it never starves probes or creation.
   */
  tier?: Extract<GitWorkTier, 'activation' | 'background'>;
  /**
   * True when the workspace must not move (live sessions under the worktree path).
   * Consulted under the writer lock, immediately before any git work.
   */
  isActive: () => Promise<boolean> | boolean;
};

export type UpdateWorktreeExecutionResult =
  | { status: 'updated'; fromOid: string; toOid: string }
  /** Already at (or already containing) the fetched head — nothing to move. */
  | { status: 'up-to-date'; oid: string }
  | { status: 'refused'; reason: 'active-sessions' | 'dirty' }
  /** Local commits the fetched head lacks: ff impossible, nothing moved. */
  | { status: 'diverged'; message: string }
  | { status: 'failed'; stage: 'inspect' | 'fetch' | 'merge'; message: string };

/**
 * The guarded fetch + fast-forward core (pr-workspace-model spec, Staleness): ONE
 * implementation of the guards and the ff-only mechanics, shared by the manual
 * updateWorktree verb and the host-autonomous ref-follow loop. Instruction-as-input —
 * remote and source ref arrive from the caller; nothing here reads durable records.
 *
 * The per-worktree writer lock is taken synchronously, before the first await, and
 * held across guard checks, fetch, and merge, so probes/scans (which wait on
 * `whenUnlocked`) never observe a torn checkout and the guards cannot go stale
 * against a concurrent mutator.
 *
 * Fetch mechanics: `--no-write-fetch-head` (registry hygiene) makes a
 * destination-less fetch unresolvable, so the source ref is fetched into a private,
 * uniquely named `refs/emdash/update/<uuid>` ref (force-updated — it is ours alone —
 * and deleted afterwards; unique because refs are shared repository-wide across
 * worktrees). The fetched OID is resolved explicitly, ancestry is checked with
 * `merge-base --is-ancestor` so a diverged branch fails cleanly before `git merge`
 * ever runs, and the fast-forward itself is `merge --ff-only <oid>` — a working-tree
 * checkout, never a bare ref write.
 */
export async function executeUpdateWorktree(
  execution: UpdateWorktreeExecution
): Promise<UpdateWorktreeExecutionResult> {
  const exec = execution.git.exec(execution.worktreePath, {
    tier: execution.tier ?? 'activation',
    repository: execution.repositoryPath,
  });
  return execution.git.locks.withWriter(execution.worktreePath, async () => {
    if (await execution.isActive()) {
      return { status: 'refused', reason: 'active-sessions' };
    }
    try {
      // The observation's notion of dirty: any status entry, untracked included.
      if (await isDirty(exec)) return { status: 'refused', reason: 'dirty' };
    } catch (error) {
      return { status: 'failed', stage: 'inspect', message: toMessage(error) };
    }

    const tempRef = `refs/emdash/update/${crypto.randomUUID()}`;
    try {
      let fetchedOid: string;
      let headOid: string;
      try {
        // Same hygiene flags as the creation-path fetches.
        await exec.exec([
          'fetch',
          execution.remote,
          `+${execution.sourceRef}:${tempRef}`,
          '--no-tags',
          '--no-write-fetch-head',
          '--no-auto-maintenance',
        ]);
        fetchedOid = await resolveCommit(exec, tempRef);
        headOid = await resolveCommit(exec, 'HEAD');
      } catch (error) {
        return { status: 'failed', stage: 'fetch', message: toMessage(error) };
      }

      if (fetchedOid === headOid) return { status: 'up-to-date', oid: headOid };
      if (await isAncestor(exec, fetchedOid, 'HEAD')) {
        // Ahead-only: the checkout already contains the fetched head (a stale cache
        // after a local push looks like this) — a no-op, never a divergence.
        return { status: 'up-to-date', oid: headOid };
      }
      if (!(await isAncestor(exec, 'HEAD', fetchedOid))) {
        return {
          status: 'diverged',
          message:
            `Local commits diverge from the fetched ${execution.sourceRef} — ` + 'resolve manually',
        };
      }
      try {
        await retryTransientLock(() => exec.exec(['merge', '--ff-only', fetchedOid]));
      } catch (error) {
        return { status: 'failed', stage: 'merge', message: toMessage(error) };
      }
      return { status: 'updated', fromOid: headOid, toOid: fetchedOid };
    } finally {
      await exec.exec(['update-ref', '-d', tempRef]).catch(() => undefined);
    }
  });
}

async function isDirty(exec: BoundExec): Promise<boolean> {
  const result = await exec.exec(['status', '--porcelain=v1', '--untracked-files=all', '-z'], {
    maxBuffer: 4 * 1024 * 1024,
  });
  return result.stdout.split('\0').some((entry) => entry.length > 0);
}

async function resolveCommit(exec: BoundExec, ref: string): Promise<string> {
  return (await exec.exec(['rev-parse', '--verify', `${ref}^{commit}`])).stdout.trim();
}

async function isAncestor(exec: BoundExec, ancestor: string, descendant: string): Promise<boolean> {
  try {
    await exec.exec(['merge-base', '--is-ancestor', ancestor, descendant]);
    return true;
  } catch {
    return false;
  }
}

function toMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

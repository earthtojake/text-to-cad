import { promises as fs } from 'node:fs';
import path from 'node:path';
import type { BoundExec } from '#services/exec/api';
import type { WorkspaceGitSetup } from '../api/schemas';
import type { RegistryGitContext } from './git-context';
import { retryTransientLock } from './git-schedule';
import { validateWorktreePath } from './worktree-path-safety';

export type CreateWorktreeExecution = {
  /** The owning runtime's git context — budget slots and the budgeted exec factory. */
  git: RegistryGitContext;
  repositoryPath: string;
  /** Resolved target path; may not exist yet. */
  worktreePath: string;
  branch: string;
  /** Null when gitSetup.fetchBranch materializes the branch instead. */
  baseRef: string | null;
  /** Structured branch setup (spec: pr-workspace-model provisioning). */
  gitSetup?: WorkspaceGitSetup;
  /** Overlay feeder: called as each stage begins. */
  onStage: (stage: string) => void;
};

export type CreateWorktreeExecutionResult =
  | {
      status: 'succeeded';
      finalPath: string;
      createdWorktree: boolean;
      /** True when the branch was created by this run (vs reusing an existing branch). */
      createdBranch: boolean;
    }
  | { status: 'failed'; stage: string; message: string };

/**
 * The foreground createWorktree stage pipeline (ADR 0005): inspect → resolve-base →
 * add-worktree → verify. This is everything an agent needs to start working — tracked
 * files checked out and functional git. Artifact cloning, branch pushing, and ref
 * freshening are background steps owned by the runtime, never awaited here. Failures
 * return stage-tagged results for the durable outcome; rollback of artifacts created in
 * this attempt is best-effort — irremovable debris is left for auto-adoption to surface.
 */
export async function executeCreateWorktree(
  execution: CreateWorktreeExecution
): Promise<CreateWorktreeExecutionResult> {
  // Creation-tier budget slots: starts immediately even under saturated probe load.
  const exec = execution.git.exec(execution.repositoryPath, {
    tier: 'creation',
    repository: execution.repositoryPath,
  });
  let existing = false;
  let createdWorktree = false;
  let createdBranch = false;

  const fail = async (stage: string, error: unknown): Promise<CreateWorktreeExecutionResult> => {
    await rollback(exec, execution, { createdWorktree, createdBranch });
    return {
      status: 'failed',
      stage,
      message: error instanceof Error ? error.message : String(error),
    };
  };

  execution.onStage('inspect');
  try {
    const safe = await validateWorktreePath({
      repoPath: execution.repositoryPath,
      targetPath: execution.worktreePath,
      mutation: 'create',
    });
    if (!safe.success) {
      return { status: 'failed', stage: 'inspect', message: safe.error.message };
    }
    existing = (await listWorktreePaths(exec)).has(
      await canonicalOrResolved(execution.worktreePath)
    );
    if (existing) {
      const current = (
        await execution.git
          .exec(execution.worktreePath, { tier: 'creation', repository: execution.repositoryPath })
          .exec(['branch', '--show-current'])
      ).stdout.trim();
      if (current !== execution.branch) {
        return {
          status: 'failed',
          stage: 'inspect',
          message:
            `Worktree ${execution.worktreePath} is checked out on ` +
            `${current || 'a detached HEAD'}, not ${execution.branch}`,
        };
      }
    }
  } catch (error) {
    return await fail('inspect', error);
  }

  if (!existing) {
    // Branch materialization from an arbitrary source ref (spec: pr-workspace-model
    // provisioning). Replay rule: an existing refs/heads/<branch> is never touched —
    // the fetch is skipped entirely and the branch reused. The destination is always
    // host-constructed from the verb's own branch, with a plain (never force) refspec.
    const fetchBranch = execution.gitSetup?.fetchBranch;
    if (fetchBranch && !(await branchExists(exec, execution.branch))) {
      execution.onStage('fetch-branch');
      try {
        // Same hygiene as fetch-base: no tags, no FETCH_HEAD write, no auto maintenance.
        await exec.exec([
          'fetch',
          fetchBranch.remote,
          `${fetchBranch.sourceRef}:refs/heads/${execution.branch}`,
          '--no-tags',
          '--no-write-fetch-head',
          '--no-auto-maintenance',
        ]);
        // The fetched branch belongs to this attempt: rollback deletes it on failure.
        createdBranch = true;
      } catch (error) {
        return await fail('fetch-branch', error);
      }
    }

    // Stale-is-fine: creation never fetches when the base ref resolves locally. Only an
    // unresolvable remote-shaped ref triggers a targeted single-ref fetch — no --all,
    // no --prune, no tags. Failure surfaces git's own error; no emdash timeout or retry.
    if (execution.baseRef !== null) {
      const baseRef = execution.baseRef;
      execution.onStage('resolve-base');
      try {
        if (!(await branchExists(exec, execution.branch)) && !(await refResolves(exec, baseRef))) {
          const remoteRef = await parseRemoteRef(exec, baseRef);
          if (remoteRef) {
            execution.onStage('fetch-base');
            // Hygiene (spec: git concurrency model): no FETCH_HEAD write, no auto
            // maintenance kicked off on the creation path.
            await exec.exec([
              'fetch',
              remoteRef.remote,
              `+refs/heads/${remoteRef.branch}:refs/remotes/${remoteRef.remote}/${remoteRef.branch}`,
              '--no-tags',
              '--no-write-fetch-head',
              '--no-auto-maintenance',
            ]);
          }
          // Non-remote-shaped unresolvable refs fall through: add-worktree fails with
          // git's own "invalid reference" error, exactly as it would have after a fetch.
        }
      } catch (error) {
        return await fail('resolve-base', error);
      }
    }

    execution.onStage('add-worktree');
    try {
      // Concurrent adds against one repository are safe (conflict matrix); a transient
      // ref/index lock collision retries with short backoff instead of serializing.
      if (await branchExists(exec, execution.branch)) {
        await retryTransientLock(() =>
          exec.exec(['worktree', 'add', execution.worktreePath, execution.branch])
        );
      } else if (execution.baseRef !== null) {
        const baseRef = execution.baseRef;
        await retryTransientLock(() =>
          exec.exec([
            'worktree',
            'add',
            '--no-track',
            '-b',
            execution.branch,
            execution.worktreePath,
            baseRef,
          ])
        );
        createdBranch = true;
      } else {
        // Structurally unreachable: input validation requires baseRef or fetchBranch,
        // and a settled fetch-branch guarantees the branch exists.
        throw new Error(`Branch ${execution.branch} does not exist and no base ref was given`);
      }
      createdWorktree = true;
    } catch (error) {
      return await fail('add-worktree', error);
    }
  }

  // Unconditionally idempotent plain config sets, running on the fresh and the
  // reused-branch/replay path alike. Branch-scoped keys land in the repository's
  // common config — the same place branch.<name>.remote/.merge always live.
  const { upstream, breadcrumb } = execution.gitSetup ?? {};
  if (upstream || breadcrumb) {
    execution.onStage('configure-branch');
    try {
      const entries: Array<[string, string]> = [];
      if (upstream) {
        entries.push([`branch.${execution.branch}.remote`, upstream.remote]);
        entries.push([`branch.${execution.branch}.merge`, upstream.mergeRef]);
      }
      if (breadcrumb) {
        entries.push([`branch.${execution.branch}.emdash-pr-url`, breadcrumb.prUrl]);
      }
      for (const [key, value] of entries) {
        await exec.exec(['config', key, value]);
      }
    } catch (error) {
      return await fail('configure-branch', error);
    }
  }

  execution.onStage('verify');
  let finalPath: string;
  try {
    finalPath = await canonicalOrResolved(execution.worktreePath);
    if (!(await listWorktreePaths(exec)).has(finalPath)) {
      return await fail(
        'verify',
        new Error(`Worktree was not listed after creation: ${execution.worktreePath}`)
      );
    }
  } catch (error) {
    return await fail('verify', error);
  }

  return { status: 'succeeded', finalPath, createdWorktree, createdBranch };
}

/**
 * Interprets a base ref of the shape `<remote>/<branch>` against the repository's
 * actual remotes. Returns null for refs that are not remote-shaped (plain local
 * branches, SHAs, tags) — those cannot be freshened by a targeted fetch.
 */
async function parseRemoteRef(
  exec: BoundExec,
  baseRef: string
): Promise<{ remote: string; branch: string } | null> {
  const separator = baseRef.indexOf('/');
  if (separator <= 0 || separator === baseRef.length - 1) return null;
  const remote = baseRef.slice(0, separator);
  const branch = baseRef.slice(separator + 1);
  const remotes = (await exec.exec(['remote'])).stdout.trim().split('\n').filter(Boolean);
  return remotes.includes(remote) ? { remote, branch } : null;
}

async function rollback(
  exec: BoundExec,
  execution: CreateWorktreeExecution,
  created: { createdWorktree: boolean; createdBranch: boolean }
): Promise<void> {
  try {
    if (created.createdWorktree) {
      await exec.exec(['worktree', 'remove', '--force', execution.worktreePath]);
    }
    if (created.createdBranch) {
      await exec.exec(['branch', '-D', execution.branch]);
    }
  } catch {
    // Best-effort only: leftover debris is surfaced by adoption, never hidden.
  }
}

async function listWorktreePaths(exec: BoundExec): Promise<Set<string>> {
  const result = await exec.exec(['worktree', 'list', '--porcelain']);
  const paths = new Set<string>();
  for (const line of result.stdout.split('\n')) {
    if (!line.startsWith('worktree ')) continue;
    paths.add(await canonicalOrResolved(line.slice('worktree '.length)));
  }
  return paths;
}

async function branchExists(exec: BoundExec, branch: string): Promise<boolean> {
  try {
    await exec.exec(['show-ref', '--verify', '--quiet', `refs/heads/${branch}`]);
    return true;
  } catch {
    return false;
  }
}

async function refResolves(exec: BoundExec, ref: string): Promise<boolean> {
  try {
    await exec.exec(['rev-parse', '--verify', '--quiet', `${ref}^{commit}`]);
    return true;
  } catch {
    return false;
  }
}

async function canonicalOrResolved(target: string): Promise<string> {
  try {
    return await fs.realpath(target);
  } catch {
    return path.resolve(target);
  }
}

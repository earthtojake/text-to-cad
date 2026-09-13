import { promises as fs } from 'node:fs';
import path from 'node:path';
import type { EnvSource } from '#primitives/exec/api';
import { createBoundExec, ExecError } from '#services/exec/api';

/** What the host found at a canonical directory path (kind is host-detected, ADR 0005). */
export type PathInspection =
  | { kind: 'directory' }
  | { kind: 'repository' }
  | { kind: 'worktree'; repositoryPath: string; gitAdminName: string }
  | { kind: 'inspect-failed'; message: string };

export type PathInspector = (canonicalPath: string) => Promise<PathInspection>;

/**
 * Resolves a client-supplied path to the canonical (symlink-free) directory path the
 * registry keys uniqueness on. Null when the path does not exist or is not a directory.
 */
export async function canonicalizeWorkspacePath(inputPath: string): Promise<string | null> {
  try {
    const canonical = await fs.realpath(inputPath);
    const stat = await fs.stat(canonical);
    return stat.isDirectory() ? canonical : null;
  } catch {
    return null;
  }
}

/**
 * Detects what a directory is: the toplevel of a repository, the toplevel of a linked
 * worktree (with its admin name and owning repository path), or a plain directory —
 * including directories inside a repository that are not its toplevel.
 */
export async function inspectWorkspacePath(
  canonicalPath: string,
  env: EnvSource = async () => process.env
): Promise<PathInspection> {
  let stdout: string;
  try {
    ({ stdout } = await createBoundExec({
      file: 'git',
      cwd: canonicalPath,
      env: async () => nonInteractiveEnv(await env()),
    }).exec(['rev-parse', '--show-toplevel', '--git-dir', '--git-common-dir'], {
      timeoutMs: 10_000,
    }));
  } catch (error) {
    // Exit 128 = not inside a git work tree: a plain directory, not a failure.
    if (error instanceof ExecError && error.exitCode !== null) return { kind: 'directory' };
    return {
      kind: 'inspect-failed',
      message: error instanceof Error ? error.message : String(error),
    };
  }

  const [toplevelRaw, gitDirRaw, commonDirRaw] = stdout.split('\n');
  if (!toplevelRaw || !gitDirRaw || !commonDirRaw) {
    return { kind: 'inspect-failed', message: `Unexpected git rev-parse output: ${stdout}` };
  }

  const toplevel = await realpathSafe(path.resolve(canonicalPath, toplevelRaw));
  if (toplevel !== canonicalPath) {
    // Inside a repository but not its toplevel: tracked as a plain directory workspace.
    return { kind: 'directory' };
  }

  const gitDir = path.resolve(canonicalPath, gitDirRaw);
  const commonDir = path.resolve(canonicalPath, commonDirRaw);
  if ((await realpathSafe(gitDir)) === (await realpathSafe(commonDir))) {
    return { kind: 'repository' };
  }

  // Linked worktree: git-dir is <common>/worktrees/<adminName>; the owning repository's
  // working directory is the parent of the common .git dir.
  const repositoryPath = await realpathSafe(path.dirname(commonDir));
  return { kind: 'worktree', repositoryPath, gitAdminName: path.basename(gitDir) };
}

function nonInteractiveEnv(base: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  return {
    ...base,
    LC_ALL: 'C',
    LANG: 'C',
    LANGUAGE: 'C',
    GIT_TERMINAL_PROMPT: '0',
    GIT_ASKPASS: '',
  };
}

async function realpathSafe(target: string): Promise<string> {
  try {
    return await fs.realpath(target);
  } catch {
    return target;
  }
}

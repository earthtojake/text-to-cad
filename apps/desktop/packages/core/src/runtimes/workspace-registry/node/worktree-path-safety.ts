import { lstat, realpath } from 'node:fs/promises';
import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import type { BoundExec } from '#services/exec/api';
import { defaultGitExecFactory, type GitExecFactory } from '#services/exec/node/git-exec';

export type WorktreePathMutation = 'create' | 'remove';

export type WorktreePathError = {
  code: 'unsafe-worktree-path' | 'foreign-worktree';
  message: string;
};

export type ValidateWorktreePathOptions = {
  repoPath: string;
  targetPath: string;
  mutation: WorktreePathMutation;
  signal?: AbortSignal;
  createGitExec?: GitExecFactory;
  pathExists?: (path: string) => Promise<boolean>;
  canonicalPath?: (path: string) => Promise<string>;
  canonicalPotentialPath?: (path: string) => Promise<string>;
};

/**
 * Preserves the applicable safety guarantees from the legacy lifecycle helper.
 *
 * The registry never recursively removes an unregistered stale path, so the old
 * pool-containment escape hatch is intentionally absent. Existing targets must be
 * Git worktrees owned by the requested repository; missing remove targets are safe no-ops.
 */
export async function validateWorktreePath(
  options: ValidateWorktreePathOptions
): Promise<Result<void, WorktreePathError>> {
  const createGitExec = options.createGitExec ?? defaultGitExecFactory;
  const exists = options.pathExists ?? defaultPathExists;
  const canonical =
    options.canonicalPath ?? (options.pathExists ? identityCanonicalPath : defaultCanonicalPath);
  const canonicalPotential =
    options.canonicalPotentialPath ??
    options.canonicalPath ??
    (options.pathExists ? identityCanonicalPath : defaultCanonicalPotentialPath);
  const repoPath = path.resolve(options.repoPath);
  const targetPath = path.resolve(options.targetPath);
  const [canonicalRepoPath, canonicalTargetPath] = await Promise.all([
    canonical(repoPath),
    canonicalPotential(targetPath),
  ]);

  if (canonicalTargetPath === canonicalRepoPath) {
    return unsafe(options.targetPath, 'the repository root is not a removable worktree');
  }
  if (options.mutation === 'create' && pathsOverlap(canonicalRepoPath, canonicalTargetPath)) {
    return unsafe(options.targetPath, 'new worktrees must not contain or be inside the repository');
  }

  const targetExists = await exists(targetPath);
  if (!targetExists) {
    return ok();
  }

  const [targetCommonDir, repositoryCommonDir] = await Promise.all([
    gitCommonDir(createGitExec(targetPath), options.signal),
    gitCommonDir(createGitExec(repoPath), options.signal),
  ]);
  if (!targetCommonDir) {
    return unsafe(options.targetPath, 'the existing target is not a Git worktree');
  }
  if (!repositoryCommonDir) {
    return foreign(options.targetPath);
  }

  const [canonicalTarget, canonicalRepository] = await Promise.all([
    canonical(targetCommonDir),
    canonical(repositoryCommonDir),
  ]);
  return canonicalTarget === canonicalRepository ? ok() : foreign(options.targetPath);
}

async function gitCommonDir(exec: BoundExec, signal?: AbortSignal): Promise<string | null> {
  try {
    const result = await exec.exec(['rev-parse', '--path-format=absolute', '--git-common-dir'], {
      signal,
    });
    return result.stdout.trim() || null;
  } catch {
    return null;
  }
}

function pathsOverlap(repoPath: string, targetPath: string): boolean {
  return isDescendant(repoPath, targetPath) || isDescendant(targetPath, repoPath);
}

function isDescendant(parentPath: string, candidatePath: string): boolean {
  const relative = path.relative(parentPath, candidatePath);
  return (
    relative !== '' &&
    relative !== '..' &&
    !relative.startsWith(`..${path.sep}`) &&
    !path.isAbsolute(relative)
  );
}

async function defaultPathExists(targetPath: string): Promise<boolean> {
  try {
    await lstat(targetPath);
    return true;
  } catch (error) {
    if (isNodeError(error) && error.code === 'ENOENT') return false;
    throw error;
  }
}

async function defaultCanonicalPath(targetPath: string): Promise<string> {
  try {
    return await realpath(targetPath);
  } catch (error) {
    if (isNodeError(error) && error.code === 'ENOENT') return path.resolve(targetPath);
    throw error;
  }
}

async function defaultCanonicalPotentialPath(targetPath: string): Promise<string> {
  const unresolved: string[] = [];
  let candidate = path.resolve(targetPath);
  for (;;) {
    try {
      return path.join(await realpath(candidate), ...unresolved.reverse());
    } catch (error) {
      if (!isNodeError(error) || error.code !== 'ENOENT') throw error;
      const parent = path.dirname(candidate);
      if (parent === candidate) throw error;
      unresolved.push(path.basename(candidate));
      candidate = parent;
    }
  }
}

async function identityCanonicalPath(targetPath: string): Promise<string> {
  return path.resolve(targetPath);
}

function isNodeError(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && 'code' in error;
}

function unsafe(targetPath: string, reason: string): Result<never, WorktreePathError> {
  return err({
    code: 'unsafe-worktree-path',
    message: `Refusing to mutate ${targetPath}: ${reason}`,
  });
}

function foreign(targetPath: string): Result<never, WorktreePathError> {
  return err({
    code: 'foreign-worktree',
    message: `Refusing to mutate ${targetPath} because it belongs to another Git repository`,
  });
}

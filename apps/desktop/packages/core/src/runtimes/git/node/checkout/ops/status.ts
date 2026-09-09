import fs from 'node:fs/promises';
import path from 'node:path';
import { parsePortableRelativePath, type PortableRelativePath } from '#primitives/path/api';
import {
  MAX_STATUS_FILES,
  StatusParser,
  type CheckoutOperation,
  type CheckoutStatusState,
  type FileGitStatus,
  type FileStatus,
  type GitChangeStatus,
  type GitStatusCode,
} from '#runtimes/git/api';
import { gitFailure } from '#runtimes/git/node/exec/errors';
import type { BoundExec } from '#services/exec/api';

/**
 * Computes checkout status from `git status --porcelain=v2`.
 * Total: expected failures are encoded as the state's `error` variant so
 * subscribers always see the latest truth.
 *
 * Git reports checkout-relative paths, which are preserved as portable paths.
 */
export async function computeStatusState(
  exec: BoundExec,
  gitDir: string
): Promise<CheckoutStatusState> {
  try {
    const parser = new StatusParser();
    await exec.execStreaming(
      ['--no-optional-locks', 'status', '--porcelain=v2', '-z', '-uall'],
      (chunk) => {
        parser.update(chunk);
        return !parser.tooManyFiles;
      }
    );
    if (parser.tooManyFiles || parser.status.length > MAX_STATUS_FILES) {
      return { kind: 'too-many-files' };
    }
    const operation = await detectOperation(gitDir);
    return buildStatusState(parser.status, operation);
  } catch (error) {
    return { kind: 'error', message: gitFailure(error).message };
  }
}

export function buildStatusState(
  entries: FileStatus[],
  operation: CheckoutOperation
): CheckoutStatusState {
  const record: Record<PortableRelativePath, FileGitStatus> = {};
  const summary = { staged: 0, unstaged: 0, conflicted: 0, untracked: 0 };

  for (const entry of entries) {
    // For renames the parser puts the new path in `rename` and the original in `path`.
    const currentPath = toPortablePath(entry.rename ?? entry.path);
    const isConflicted = isConflictCode(entry.x, entry.y);
    const fileStatus: FileGitStatus = {
      path: currentPath,
      index: codeToStatus(entry.x),
      worktree: codeToStatus(entry.y),
      isConflicted,
    };
    if (entry.rename) fileStatus.origPath = toPortablePath(entry.path);
    record[currentPath] = fileStatus;

    if (isConflicted) {
      summary.conflicted += 1;
      continue;
    }
    if (entry.x === '?') {
      summary.untracked += 1;
      continue;
    }
    if (entry.x !== ' ' && entry.x !== '!') summary.staged += 1;
    if (entry.y !== ' ' && entry.y !== '?' && entry.y !== '!') summary.unstaged += 1;
  }

  return { kind: 'ok', entries: record, summary, operation };
}

function toPortablePath(filePath: string): PortableRelativePath {
  const parsed = parsePortableRelativePath(filePath, { unicodeNormalization: 'preserve' });
  if (!parsed.success || !parsed.data) {
    throw new Error(parsed.success ? 'Git returned an empty file path' : parsed.error.message);
  }
  return parsed.data;
}

/** In-progress operation detection via the worktree git dir's state files. */
export async function detectOperation(gitDir: string): Promise<CheckoutOperation> {
  if (
    (await exists(path.join(gitDir, 'rebase-merge'))) ||
    (await exists(path.join(gitDir, 'rebase-apply')))
  ) {
    return 'rebase';
  }
  if (await exists(path.join(gitDir, 'MERGE_HEAD'))) return 'merge';
  if (await exists(path.join(gitDir, 'CHERRY_PICK_HEAD'))) return 'cherry-pick';
  if (await exists(path.join(gitDir, 'REVERT_HEAD'))) return 'revert';
  if (await exists(path.join(gitDir, 'BISECT_LOG'))) return 'bisect';
  return 'none';
}

export function mapGitChangeStatus(code: string): GitChangeStatus {
  if (code.includes('U') || code === 'AA' || code === 'DD') return 'conflicted';
  if (code.includes('A') || code.includes('?')) return 'added';
  if (code.includes('D')) return 'deleted';
  if (code.includes('R')) return 'renamed';
  return 'modified';
}

function codeToStatus(code: string): GitStatusCode {
  switch (code) {
    case 'M':
    case 'm':
      return 'modified';
    case 'A':
      return 'added';
    case 'D':
      return 'deleted';
    case 'R':
      return 'renamed';
    case 'C':
      return 'copied';
    case 'T':
      return 'type-changed';
    case 'U':
      return 'unmerged';
    case '?':
      return 'untracked';
    case '!':
      return 'ignored';
    default:
      return 'unmodified';
  }
}

function isConflictCode(x: string, y: string): boolean {
  return x === 'U' || y === 'U' || (x === 'A' && y === 'A') || (x === 'D' && y === 'D');
}

async function exists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch (error) {
    if (!isMissingPath(error)) throw error;
    return false;
  }
}

function isMissingPath(error: unknown): error is NodeJS.ErrnoException {
  return (
    error instanceof Error &&
    'code' in error &&
    (error.code === 'ENOENT' || error.code === 'ENOTDIR')
  );
}

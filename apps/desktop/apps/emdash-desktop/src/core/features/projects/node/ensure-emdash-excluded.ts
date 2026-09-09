import { log } from '@emdash/shared/logger';
import { SSH_PROJECT_STATE_DIR_NAME } from '@core/features/projects/node/worktree-defaults';
import {
  fileKey,
  fsErrorMessage,
  type FilesClientScope,
} from '@core/services/runtime-broker/node/files';

const GIT_EXCLUDE_PATH = '.git/info/exclude';
const IGNORE_PATTERN = `${SSH_PROJECT_STATE_DIR_NAME}/`;

function joinProjectPath(rootPath: string, relativePath: string): string {
  const separator = rootPath.includes('\\') && !rootPath.includes('/') ? '\\' : '/';
  return rootPath.endsWith('/') || rootPath.endsWith('\\')
    ? `${rootPath}${relativePath}`
    : `${rootPath}${separator}${relativePath}`;
}

/**
 * Ensure the project's `.emdash/` runtime dir is git-ignored via `.git/info/exclude`.
 *
 * emdash keeps per-project state under `.emdash/` inside the repo: the SSH worktree
 * worktree pool ({@link SSH_PROJECT_STATE_DIR_NAME}/worktrees), saved attachments, and uploaded
 * images. None of that belongs in the user's tree, so we exclude it locally rather than
 * touching a tracked `.gitignore`. `info/exclude` lives in the git common dir, so a single
 * entry on the main checkout also covers every linked task worktree.
 *
 * Best effort and idempotent: skips repos without a real `.git` directory (linked
 * worktrees / submodules use a `.git` file whose exclude is out of this fs's root) and
 * skips when `.emdash` is already ignored (e.g. via a global gitignore).
 */
export async function ensureEmdashGitExcluded(
  files: FilesClientScope,
  repoPath: string
): Promise<void> {
  const gitPath = joinProjectPath(repoPath, '.git');
  const excludePath = joinProjectPath(repoPath, GIT_EXCLUDE_PATH);

  const gitDir = await files.client.fs.stat(fileKey(files, gitPath));
  if (!gitDir.success || gitDir.data.type !== 'directory') return;

  let existing = '';
  const excludeExists = await files.client.fs.exists(fileKey(files, excludePath));
  if (excludeExists.success && excludeExists.data.exists) {
    const read = await files.client.fs.readText(fileKey(files, excludePath));
    if (!read.success) return;
    // `read` caps at a default byte limit; rewriting a truncated view would drop
    // any rules past the cut. Bail rather than risk corrupting the file.
    if (read.data.truncated) return;
    existing = read.data.content;
  }

  const alreadyExcluded = existing
    .split(/\r?\n/)
    .map((line) => line.trim())
    .some((line) => line === SSH_PROJECT_STATE_DIR_NAME || line === IGNORE_PATTERN);
  if (alreadyExcluded) return;

  const base = existing.replace(/\s*$/, '');
  const next = base.length > 0 ? `${base}\n${IGNORE_PATTERN}\n` : `${IGNORE_PATTERN}\n`;
  const result = await files.client.fs.writeFile({
    ...fileKey(files, excludePath),
    content: next,
    precondition: { kind: 'overwrite' },
  });
  if (!result.success) {
    throw new Error(fsErrorMessage(result.error));
  }
}

/** Fire-and-forget wrapper that never rejects; logs and moves on. */
export function ensureEmdashGitExcludedSafe(
  files: FilesClientScope,
  repoPath: string,
  projectId: string
): void {
  void ensureEmdashGitExcluded(files, repoPath).catch((error) => {
    log.warn('ensureEmdashGitExcluded failed', {
      projectId,
      error: error instanceof Error ? error.message : String(error),
    });
  });
}

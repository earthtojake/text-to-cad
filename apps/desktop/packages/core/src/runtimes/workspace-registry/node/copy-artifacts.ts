import { execFile } from 'node:child_process';
import { once } from 'node:events';
import { cp, glob, lstat, mkdir, rename, rm } from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import { EMDASH_CONFIG_FILE } from '#primitives/emdash-config/api';
import type { RegistryGitContext } from './git-context';

const execFileAsync = promisify(execFile);

export type CopyArtifactsInput = {
  /** The owning runtime's git context — copy subprocesses take its budget slots. */
  git: RegistryGitContext;
  repositoryPath: string;
  worktreePath: string;
  /** The deliberate selection: gitignored files that ride into the new worktree. */
  preservePatterns: readonly string[];
};

export type CopyArtifactsOutcome =
  | {
      status: 'succeeded';
      /** 'cow' when every entry cloned on the fast tier; 'copy' when any fell back. */
      engine: 'cow' | 'copy' | 'none';
      /** Matched top-level entries materialized (a preserved directory counts as one). */
      entries: number;
      warnings: string[];
    }
  | { status: 'skipped'; reason: string }
  | { status: 'failed'; message: string };

/** Staging suffix for entry-level rename idempotency; replays clean and redo these. */
const STAGING_SUFFIX = '.emdash-clone-tmp';

/**
 * The copy-artifacts background step: materializes exactly the gitignored entries the
 * project names in `preservePatterns` into a freshly created worktree. Each pattern
 * resolves with `fs.glob` against the source checkout — cost scales with the matched
 * set; enumerating the full ignored set wholesale is the named anti-pattern (spec:
 * preserved-artifact copy). Matches pass containment validation and a batch
 * `git check-ignore` filter so tracked files already materialized by the checkout are
 * never overwritten. Copying is per-entry CoW with plain-copy fallback, staged and
 * renamed so crash-replay is idempotent; symlinks are cloned as symlinks.
 */
export async function executeCopyArtifacts(
  input: CopyArtifactsInput
): Promise<CopyArtifactsOutcome> {
  if (input.preservePatterns.length === 0) {
    return { status: 'skipped', reason: 'No preservePatterns configured' };
  }

  const warnings: string[] = [];
  const safePatterns: string[] = [];
  for (const pattern of input.preservePatterns) {
    if (!isSafePattern(pattern)) {
      warnings.push(`Skipped unsafe preserve pattern "${pattern}"`);
      continue;
    }
    safePatterns.push(pattern);
  }
  if (safePatterns.length === 0) {
    return { status: 'succeeded', engine: 'none', entries: 0, warnings };
  }

  let candidates: string[];
  try {
    candidates = await resolvePatternMatches(input.repositoryPath, safePatterns);
  } catch (error) {
    return { status: 'failed', message: `Could not resolve preserve patterns: ${message(error)}` };
  }

  let accepted: string[];
  try {
    accepted = await filterIgnored(input.git, input.repositoryPath, candidates);
  } catch (error) {
    return { status: 'failed', message: `Could not filter preserved matches: ${message(error)}` };
  }

  let engine: 'cow' | 'copy' | 'none' = 'none';
  let entries = 0;
  const errors: string[] = [];
  for (const entry of accepted) {
    const destination = path.resolve(input.worktreePath, entry);
    if (!isContainedBy(input.worktreePath, destination)) {
      warnings.push(`Skipped unsafe preserve destination "${entry}"`);
      continue;
    }
    // Each entry's copy subprocess takes a background-tier budget slot (spec: the
    // budget governs artifact-copy processes too).
    const outcome = await input.git.schedule.run(
      { tier: 'background', repository: input.repositoryPath },
      () => cloneEntry(input.repositoryPath, input.worktreePath, entry)
    );
    if (outcome === 'failed-terminally') {
      errors.push(entry);
      continue;
    }
    entries += 1;
    if (outcome === 'cloned-cow') {
      engine = engine === 'copy' ? 'copy' : 'cow';
    } else if (outcome === 'cloned-copy') {
      engine = 'copy';
    }
  }

  if (errors.length > 0) {
    return {
      status: 'failed',
      message:
        `Could not copy ${errors.length} preserved ${errors.length === 1 ? 'entry' : 'entries'} ` +
        `(first: ${errors[0]}).`,
    };
  }
  return { status: 'succeeded', engine, entries, warnings };
}

/**
 * Resolves the preserve patterns against the source checkout and reduces the matches
 * to top-level entries: a match nested inside another matched directory rides its
 * parent. Matches are repo-relative POSIX paths.
 */
async function resolvePatternMatches(
  repositoryPath: string,
  patterns: string[]
): Promise<string[]> {
  const matched = new Set<string>();
  for await (const match of glob(patterns, { cwd: repositoryPath })) {
    const relative = match.split(path.sep).join('/');
    if (relative === EMDASH_CONFIG_FILE || relative === '.git' || relative.startsWith('.git/')) {
      continue;
    }
    matched.add(relative);
  }

  const sorted = [...matched].sort();
  const topLevel: string[] = [];
  for (const entry of sorted) {
    const last = topLevel[topLevel.length - 1];
    if (last !== undefined && entry.startsWith(`${last}/`)) continue;
    topLevel.push(entry);
  }
  return topLevel;
}

/**
 * Batch `git check-ignore --stdin -z`: keeps only matches git reports as ignored, so
 * a careless glob can never clobber tracked (or merely untracked) files the checkout
 * owns. Exit code 1 means "nothing ignored" and is not an error.
 */
async function filterIgnored(
  git: RegistryGitContext,
  repositoryPath: string,
  candidates: string[]
): Promise<string[]> {
  if (candidates.length === 0) return [];
  // spawn bypasses the exec-level budget wrapping; take the slot around it here.
  const ignored = await git.schedule.run(
    { tier: 'background', repository: repositoryPath },
    async () => {
      const child = await git.exec(repositoryPath).spawn(['check-ignore', '--stdin', '-z']);
      const stdoutChunks: Buffer[] = [];
      child.stdout.on('data', (chunk: Buffer) => stdoutChunks.push(chunk));
      child.stderr.resume();
      child.stdin.end(candidates.join('\0') + '\0');
      const [exitCode] = (await once(child, 'close')) as [number | null];
      if (exitCode !== 0 && exitCode !== 1) {
        throw new Error(`git check-ignore exited with ${exitCode}`);
      }
      return new Set(Buffer.concat(stdoutChunks).toString('utf8').split('\0').filter(Boolean));
    }
  );
  return candidates.filter((candidate) => ignored.has(candidate));
}

type CloneEntryOutcome = 'cloned-cow' | 'cloned-copy' | 'existing' | 'failed-terminally';

/**
 * Clones one preserved entry with staged-rename idempotency: an existing destination
 * is trusted (a completed rename is atomic), stale staging is deleted, the best engine
 * is attempted first and a plain copy retried once on any failure.
 */
async function cloneEntry(
  repositoryPath: string,
  worktreePath: string,
  entry: string
): Promise<CloneEntryOutcome> {
  const source = path.join(repositoryPath, entry);
  const destination = path.join(worktreePath, entry);
  const staging = destination + STAGING_SUFFIX;

  if (await exists(destination)) return 'existing';
  try {
    await rm(staging, { recursive: true, force: true });
    await mkdir(path.dirname(destination), { recursive: true });
  } catch {
    return 'failed-terminally';
  }

  let tier: 'cow' | 'copy' = 'cow';
  try {
    await cowClone(source, staging);
  } catch {
    // Attempt-and-fallback (EXDEV/ENOTSUP-class failures included): delete the partial
    // destination and retry once as a plain copy.
    tier = 'copy';
    try {
      await rm(staging, { recursive: true, force: true });
      // fs.cp is the portable plain tier (files and directories); symlinks copy as links.
      await cp(source, staging, { recursive: true, verbatimSymlinks: true });
    } catch {
      await rm(staging, { recursive: true, force: true }).catch(() => undefined);
      return 'failed-terminally';
    }
  }

  try {
    await rename(staging, destination);
  } catch {
    await rm(staging, { recursive: true, force: true }).catch(() => undefined);
    // A concurrent replay may have landed the entry; that is success, not failure.
    return (await exists(destination)) ? 'existing' : 'failed-terminally';
  }
  return tier === 'cow' ? 'cloned-cow' : 'cloned-copy';
}

/**
 * The best-tier clone: `cp -c` (per-file clonefile) on macOS, `cp -a --reflink=auto`
 * on Linux — the flag already degrades reflink→copy on ext4, so a failure here is a
 * real error. With `-R`, symlinks are not followed (`-P` is the BSD default; GNU `-a`
 * implies `-d`). No native code (spec: Node/libuv cannot issue clonefile on Darwin).
 */
async function cowClone(source: string, destination: string): Promise<void> {
  if (process.platform === 'darwin') {
    // Note: modern macOS `cp -c` silently falls back to a plain copy on non-APFS
    // volumes, so the reported 'cow' tier is best-effort on macOS.
    await execFileAsync('cp', ['-c', '-R', '-P', source, destination]);
    return;
  }
  if (process.platform === 'linux') {
    await execFileAsync('cp', ['-a', '--reflink=auto', source, destination]);
    return;
  }
  throw new Error(`No copy-on-write tier on ${process.platform}`);
}

function isSafePattern(pattern: string): boolean {
  if (!pattern || path.isAbsolute(pattern)) return false;
  return !pattern.split(/[\\/]/).some((part) => part === '..');
}

function isContainedBy(root: string, target: string): boolean {
  const relative = path.relative(root, target);
  return relative === '' || (!relative.startsWith('..') && !path.isAbsolute(relative));
}

async function exists(target: string): Promise<boolean> {
  try {
    await lstat(target);
    return true;
  } catch {
    return false;
  }
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

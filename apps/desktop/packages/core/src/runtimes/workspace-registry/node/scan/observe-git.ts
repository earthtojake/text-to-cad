import { readdir, readFile, stat } from 'node:fs/promises';
import { dirname, isAbsolute, join, resolve } from 'node:path';
import type { BoundExec } from '#services/exec/api';
import type { WorkspaceGitObservations } from '../../api/schemas';
import type { RegistryGitContext } from '../git-context';

const EXEC_TIMEOUT_MS = 30_000;
const LOCAL_BRANCH_PREFIX = 'refs/heads/';
/** Oversized output degrades the one workspace, never the scan (spec: T04). */
const STATUS_MAX_BUFFER = 4 * 1024 * 1024;
const UNTRACKED_FILE_MAX_BYTES = 5 * 1024 * 1024;
const UNTRACKED_FILES_MAX = 5_000;
/**
 * Per-scan cap on bytes read for untracked line counting. First contact with a
 * huge untracked tree degrades the untracked component to null (the same
 * degrade semantics as UNTRACKED_FILES_MAX) instead of dominating the scan;
 * later scans serve unchanged files from the stat-keyed cache for free.
 */
const UNTRACKED_SCAN_BYTE_BUDGET = 32 * 1024 * 1024;

export type UntrackedLineEntry = { size: number; mtimeMs: number; lines: number };
/** Stat-keyed line-count cache for one workspace's untracked files. */
export type UntrackedLinesCache = Map<string, UntrackedLineEntry>;

export function createUntrackedLinesCache(): UntrackedLinesCache {
  return new Map();
}

/**
 * Remote-name → URL cache scoped to one repository's scan pass (spec: probe budget —
 * the remote URL resolves at most once per repository per scan cycle). Worktrees share
 * their repository's config, so the remote name alone is a sufficient key. `null`
 * caches a failed resolution for the rest of the cycle.
 */
export type RemoteUrlCache = Map<string, string | null>;

export function createRemoteUrlCache(): RemoteUrlCache {
  return new Map();
}

export type ObserveWorkspaceGitOptions = {
  /** Per-workspace cache; the scan runtime owns it and evicts it with the record. */
  untrackedCache?: UntrackedLinesCache;
  untrackedByteBudget?: number;
  /** Per-scan-cycle cache; absent = resolve per workspace (single-workspace scans). */
  remoteUrlCache?: RemoteUrlCache;
};

export type ObserveWorkspaceGitRefsOptions = {
  remoteUrlCache?: RemoteUrlCache;
};

export type WorktreeListing = {
  path: string;
  isMain: boolean;
  branch: string | null;
  locked: boolean;
  prunable: boolean;
  /** Git worktree admin name (the relink anchor); undefined for the main worktree. */
  adminName: string | undefined;
};

/**
 * Lists a repository's worktrees with their admin names — the registry's reconciliation
 * input. Admin names come from the common dir's `worktrees/<name>/gitdir` files.
 */
export async function listRepositoryWorktrees(
  git: RegistryGitContext,
  repoPath: string
): Promise<WorktreeListing[]> {
  const exec = git.exec(repoPath);
  const [listResult, commonDirResult] = await Promise.all([
    exec.exec(['worktree', 'list', '--porcelain'], { timeoutMs: EXEC_TIMEOUT_MS }),
    exec.exec(['rev-parse', '--git-common-dir'], { timeoutMs: EXEC_TIMEOUT_MS }),
  ]);
  const commonDir = resolveGitPath(repoPath, commonDirResult.stdout.trim());
  const adminNames = await readAdminNames(commonDir);

  const listings: WorktreeListing[] = [];
  let current: Partial<{ path: string; branch: string; locked: boolean; prunable: boolean }> = {};
  const flush = () => {
    if (!current.path) return;
    listings.push({
      path: current.path,
      isMain: listings.length === 0,
      branch: current.branch ?? null,
      locked: current.locked ?? false,
      prunable: current.prunable ?? false,
      adminName: adminNames.get(current.path),
    });
    current = {};
  };
  for (const line of listResult.stdout.split('\n')) {
    if (line === '') {
      flush();
      continue;
    }
    if (line.startsWith('worktree ')) current.path = line.slice('worktree '.length);
    else if (line.startsWith('branch ')) {
      current.branch = line.slice('branch '.length).replace(/^refs\/heads\//, '');
    } else if (line === 'locked' || line.startsWith('locked ')) current.locked = true;
    else if (line === 'prunable' || line.startsWith('prunable ')) current.prunable = true;
  }
  flush();
  return listings;
}

/**
 * Computes the per-workspace git observation block. Diff stats include untracked files'
 * lines as additions (respecting .gitignore). Returns null when the workspace cannot be
 * observed — the record degrades, the scan never fails on one workspace.
 */
export async function observeWorkspaceGit(
  git: RegistryGitContext,
  workspacePath: string,
  listing?: Pick<WorktreeListing, 'locked' | 'prunable'>,
  options: ObserveWorkspaceGitOptions = {}
): Promise<WorkspaceGitObservations | null> {
  // Probes of a worktree under active plumbing/removal wait for the writer to finish
  // rather than observing a torn checkout (spec: per-worktree writer lock).
  await git.locks.whenUnlocked(workspacePath);
  const exec = git.exec(workspacePath);
  try {
    const [branch, headOid, status, divergence] = await Promise.all([
      readBranch(exec),
      readHeadOid(exec),
      readStatus(exec),
      readDivergence(exec),
    ]);
    const identity = await readBranchIdentity(exec, branch, options.remoteUrlCache);
    const untrackedAdded = await countUntrackedLines(workspacePath, status.untracked, options);
    const tracked = await readTrackedDiffStats(exec);
    const diffStats =
      tracked === null && untrackedAdded === null
        ? null
        : {
            added: (tracked?.added ?? 0) + (untrackedAdded ?? 0),
            deleted: tracked?.deleted ?? 0,
          };
    return {
      branch,
      dirty: status.dirty,
      diffStats,
      ahead: divergence?.ahead ?? null,
      behind: divergence?.behind ?? null,
      locked: listing?.locked ?? false,
      prunable: listing?.prunable ?? false,
      headOid,
      upstream: identity.upstream,
      prBreadcrumb: identity.prBreadcrumb,
    };
  } catch {
    return null;
  }
}

/**
 * The cheap scan path for ref-only changes (commit, branch switch, fetch): re-reads
 * branch, divergence, head OID, upstream identity, and breadcrumb (a branch switch
 * changes all of them), carrying dirty/diff/lock state from the previous observation —
 * no `git status`, no untracked line counting.
 */
export async function observeWorkspaceGitRefs(
  git: RegistryGitContext,
  workspacePath: string,
  previous: WorkspaceGitObservations | null,
  options: ObserveWorkspaceGitRefsOptions = {}
): Promise<WorkspaceGitObservations | null> {
  await git.locks.whenUnlocked(workspacePath);
  const exec = git.exec(workspacePath);
  try {
    const [branch, headOid, divergence] = await Promise.all([
      readBranch(exec),
      readHeadOid(exec),
      readDivergence(exec),
    ]);
    const identity = await readBranchIdentity(exec, branch, options.remoteUrlCache);
    return {
      branch,
      dirty: previous?.dirty ?? false,
      diffStats: previous?.diffStats ?? null,
      ahead: divergence?.ahead ?? null,
      behind: divergence?.behind ?? null,
      locked: previous?.locked ?? false,
      prunable: previous?.prunable ?? false,
      headOid,
      upstream: identity.upstream,
      prBreadcrumb: identity.prBreadcrumb,
    };
  } catch {
    return previous;
  }
}

async function readBranch(exec: BoundExec): Promise<string | null> {
  try {
    const result = await exec.exec(['symbolic-ref', 'HEAD'], {
      timeoutMs: EXEC_TIMEOUT_MS,
    });
    const ref = result.stdout.trim();
    return ref.startsWith(LOCAL_BRANCH_PREFIX) ? ref.slice(LOCAL_BRANCH_PREFIX.length) : null;
  } catch {
    return null;
  }
}

/** Full OID of HEAD; null on unborn HEAD or probe failure — never fails the record. */
async function readHeadOid(exec: BoundExec): Promise<string | null> {
  try {
    const result = await exec.exec(['rev-parse', 'HEAD'], { timeoutMs: EXEC_TIMEOUT_MS });
    return result.stdout.trim() || null;
  } catch {
    return null;
  }
}

type BranchIdentity = {
  upstream: { remote: string; mergeRef: string; remoteUrl: string | null } | null;
  prBreadcrumb: string | null;
};

/**
 * Upstream identity and PR breadcrumb from ONE branch-scoped config probe (spec: probe
 * budget): `config --get-regexp '^branch\.<branch>\.'` covers remote, merge, and the
 * breadcrumb together. Values are reported verbatim — the host never interprets the
 * breadcrumb or ref patterns. Detached HEAD (null branch) yields nulls; a failed probe
 * degrades these fields to null without touching the rest of the record.
 */
async function readBranchIdentity(
  exec: BoundExec,
  branch: string | null,
  remoteUrlCache: RemoteUrlCache | undefined
): Promise<BranchIdentity> {
  if (branch === null) return { upstream: null, prBreadcrumb: null };
  let stdout: string;
  try {
    // Exit code 1 (no matching config at all) lands in the catch: all fields null.
    ({ stdout } = await exec.exec(
      ['config', '-z', '--get-regexp', `^branch\\.${escapeConfigRegexp(branch)}\\.`],
      { timeoutMs: EXEC_TIMEOUT_MS }
    ));
  } catch {
    return { upstream: null, prBreadcrumb: null };
  }
  const prefix = `branch.${branch}.`;
  let remote: string | null = null;
  let mergeRef: string | null = null;
  let prBreadcrumb: string | null = null;
  for (const entry of stdout.split('\0')) {
    if (entry === '') continue;
    // `-z` entries are `key\nvalue`; a value-less key has no newline.
    const separator = entry.indexOf('\n');
    const key = separator === -1 ? entry : entry.slice(0, separator);
    const value = separator === -1 ? '' : entry.slice(separator + 1);
    if (!key.startsWith(prefix)) continue;
    const name = key.slice(prefix.length);
    if (name === 'remote') remote = value;
    else if (name === 'merge') mergeRef = value;
    else if (name === 'emdash-pr-url') prBreadcrumb = value;
  }
  const upstream =
    remote !== null && mergeRef !== null
      ? { remote, mergeRef, remoteUrl: await resolveRemoteUrl(exec, remote, remoteUrlCache) }
      : null;
  return { upstream, prBreadcrumb };
}

/** Escapes ERE metacharacters so the branch name matches literally in --get-regexp. */
function escapeConfigRegexp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

async function resolveRemoteUrl(
  exec: BoundExec,
  remote: string,
  cache: RemoteUrlCache | undefined
): Promise<string | null> {
  const hit = cache?.get(remote);
  if (hit !== undefined) return hit;
  let url: string | null;
  try {
    const result = await exec.exec(['remote', 'get-url', remote], { timeoutMs: EXEC_TIMEOUT_MS });
    url = result.stdout.trim() || null;
  } catch {
    url = null;
  }
  cache?.set(remote, url);
  return url;
}

async function readStatus(exec: BoundExec): Promise<{ dirty: boolean; untracked: string[] }> {
  const result = await exec.exec(['status', '--porcelain=v1', '--untracked-files=all', '-z'], {
    timeoutMs: EXEC_TIMEOUT_MS,
    maxBuffer: STATUS_MAX_BUFFER,
  });
  const entries = result.stdout.split('\0').filter((entry) => entry.length > 0);
  const untracked: string[] = [];
  for (const entry of entries) {
    if (entry.startsWith('?? ')) untracked.push(entry.slice(3));
  }
  return { dirty: entries.length > 0, untracked };
}

async function readTrackedDiffStats(
  exec: BoundExec
): Promise<{ added: number; deleted: number } | null> {
  let stdout: string;
  try {
    ({ stdout } = await exec.exec(['diff', '--numstat', 'HEAD', '--'], {
      timeoutMs: EXEC_TIMEOUT_MS,
      maxBuffer: STATUS_MAX_BUFFER,
    }));
  } catch {
    // Unborn HEAD: no tracked baseline; untracked counting carries the additions.
    return { added: 0, deleted: 0 };
  }
  let added = 0;
  let deleted = 0;
  for (const line of stdout.split('\n')) {
    if (!line.trim()) continue;
    const [rawAdded, rawDeleted] = line.split('\t');
    added += parseNumstatValue(rawAdded);
    deleted += parseNumstatValue(rawDeleted);
  }
  return { added, deleted };
}

function parseNumstatValue(value: string | undefined): number {
  if (!value || value === '-') return 0;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

/**
 * Counts untracked files' lines the way numstat counts additions. Binary and oversized
 * files are skipped (numstat reports '-' for binary); pathological trees degrade to null
 * rather than blocking the scan.
 *
 * Each scan does one stat per file; only files whose (size, mtime) changed are re-read,
 * bounded by a per-scan byte budget. Exceeding the budget degrades the whole untracked
 * component to null — never a partial count.
 */
async function countUntrackedLines(
  workspacePath: string,
  untracked: string[],
  options: ObserveWorkspaceGitOptions
): Promise<number | null> {
  if (untracked.length > UNTRACKED_FILES_MAX) return null;
  const cache = options.untrackedCache;
  const budget = options.untrackedByteBudget ?? UNTRACKED_SCAN_BYTE_BUDGET;
  let added = 0;
  let bytesRead = 0;
  for (const relativePath of untracked) {
    try {
      const info = await stat(join(workspacePath, relativePath));
      if (!info.isFile()) continue;

      const hit = cache?.get(relativePath);
      if (hit && hit.size === info.size && hit.mtimeMs === info.mtimeMs) {
        added += hit.lines;
        continue;
      }

      if (info.size > UNTRACKED_FILE_MAX_BYTES) {
        cache?.set(relativePath, { size: info.size, mtimeMs: info.mtimeMs, lines: 0 });
        continue;
      }
      if (bytesRead + info.size > budget) return null;

      const content = await readFile(join(workspacePath, relativePath));
      bytesRead += content.byteLength;
      // Binary heuristic, like git's: NUL in the first 8 kB counts as zero lines.
      const lines = content.subarray(0, 8_000).includes(0) ? 0 : countLines(content);
      cache?.set(relativePath, { size: info.size, mtimeMs: info.mtimeMs, lines });
      added += lines;
    } catch {
      // Vanished mid-scan or unreadable: skip the file, keep the scan.
    }
  }
  if (cache) {
    const current = new Set(untracked);
    for (const key of cache.keys()) {
      if (!current.has(key)) cache.delete(key);
    }
  }
  return added;
}

function countLines(content: Buffer): number {
  if (content.byteLength === 0) return 0;
  let lines = 0;
  for (const byte of content) {
    if (byte === 10) lines += 1;
  }
  if (content[content.byteLength - 1] !== 10) lines += 1;
  return lines;
}

async function readDivergence(exec: BoundExec): Promise<{ ahead: number; behind: number } | null> {
  try {
    const result = await exec.exec(['rev-list', '--left-right', '--count', 'HEAD...@{u}'], {
      timeoutMs: EXEC_TIMEOUT_MS,
    });
    const [aheadRaw, behindRaw] = result.stdout.trim().split(/\s+/u);
    return {
      ahead: Number.parseInt(aheadRaw ?? '0', 10) || 0,
      behind: Number.parseInt(behindRaw ?? '0', 10) || 0,
    };
  } catch {
    return null;
  }
}

async function readAdminNames(commonDir: string): Promise<Map<string, string>> {
  const byPath = new Map<string, string>();
  let entries: string[];
  try {
    entries = await readdir(join(commonDir, 'worktrees'));
  } catch {
    return byPath;
  }
  await Promise.all(
    entries.map(async (adminName) => {
      try {
        const gitdir = (
          await readFile(join(commonDir, 'worktrees', adminName, 'gitdir'), 'utf8')
        ).trim();
        byPath.set(dirname(gitdir), adminName);
      } catch {
        // Corrupted admin dirs surface as prunable in the worktree listing.
      }
    })
  );
  return byPath;
}

function resolveGitPath(cwd: string, rawPath: string): string {
  return isAbsolute(rawPath) ? rawPath : resolve(cwd, rawPath);
}

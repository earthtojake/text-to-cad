/**
 * Git, as the review tab needs it: what changed, by how much, and the diff.
 *
 * The `git` CLI, not a library. Every answer here is one `git` invocation and
 * a parser, which means the app agrees with what the person sees in their own
 * terminal — including their `.gitattributes`, their `diff.external`, their
 * submodules and their line-ending config. A reimplementation of git's diff
 * that disagreed with git in one of those cases would be worse than no diff.
 *
 * Two halves, in order: what the review tab reads (status, diffs, commit,
 * push) and what the git modes need (plan §9) — repository detection,
 * worktree creation, listing, removal and the keep-limit sweep, and
 * `Create pull request` through `gh`. Which mode a session gets and where its
 * worktree goes is `projects/workspace.ts`; this file has no opinion about
 * settings, sessions or the app's directories.
 *
 * The parsers are exported and pure: `git`'s porcelain formats are stable and
 * fiddly, and they are the part worth a unit test.
 */
import fsp from "node:fs/promises";
import path from "node:path";

import { execa, type Options } from "execa";

/* -------------------------------------------------------------------------- */
/* Types                                                                       */
/* -------------------------------------------------------------------------- */

/** Git's own status letters, narrowed to the ones the badge shows. */
export type ChangeStatus = "added" | "modified" | "deleted" | "renamed" | "untracked";

export type ChangedFile = {
  /** Repository-relative, POSIX separators. */
  path: string;
  /** Set for a rename: where the file came from. */
  oldPath?: string;
  status: ChangeStatus;
  insertions: number;
  deletions: number;
  /** True when git will not diff it — the review tab says so rather than lying. */
  binary: boolean;
};

export type GitStatus = {
  /** False for a directory that is not a repository. Everything else is empty. */
  isRepository: boolean;
  branch: string | null;
  /** True when HEAD has no commits yet. */
  unborn: boolean;
  ahead: number;
  behind: number;
  files: ChangedFile[];
  insertions: number;
  deletions: number;
};

/** What a review is taken against. */
export type DiffScope =
  | { kind: "working-tree" }
  /** Everything since a point in time, e.g. "Since 1 hour ago". */
  | { kind: "since"; since: string }
  /** An explicit revision range, `<from>..<to>`. */
  | { kind: "range"; from: string; to?: string };

export type FileDiff = {
  path: string;
  oldPath?: string;
  status: ChangeStatus;
  insertions: number;
  deletions: number;
  binary: boolean;
  /** The two sides, for a diff editor. Null when git cannot produce one. */
  before: string | null;
  after: string | null;
};

/* -------------------------------------------------------------------------- */
/* Running git                                                                 */
/* -------------------------------------------------------------------------- */

export class GitError extends Error {
  override readonly name = "GitError";
}

const GIT_OPTIONS: Options = {
  // A pager waiting on a TTY that does not exist hangs the call forever, and
  // an editor prompt in a commit does the same. Both are turned off here
  // rather than trusted to the user's config.
  env: { GIT_PAGER: "cat", GIT_TERMINAL_PROMPT: "0", GIT_OPTIONAL_LOCKS: "0" },
  extendEnv: true,
  reject: false,
  stripFinalNewline: false,
  // A `git log` over a large repository can be megabytes; the default 100 MB
  // cap is fine, but a hang is not — a slow network remote must not wedge a
  // pane the user is looking at.
  timeout: 60_000,
};

async function git(cwd: string, args: string[]): Promise<string> {
  const result = await execa("git", args, { ...GIT_OPTIONS, cwd });
  if (result.failed || result.exitCode !== 0) {
    const stderr = typeof result.stderr === "string" ? result.stderr.trim() : "";
    throw new GitError(stderr || `git ${args[0]} failed`);
  }
  return typeof result.stdout === "string" ? result.stdout : "";
}

/** Run git, answering `null` instead of throwing. For the optional reads. */
async function tryGit(cwd: string, args: string[]): Promise<string | null> {
  return git(cwd, args).catch(() => null);
}

/**
 * `git diff --no-index <null> <path>`, which is how an untracked file gets a
 * diff at all.
 *
 * It needs its own runner because it reports "the files differ" as **exit code
 * 1** — the same code every other git command uses for failure. Through
 * `tryGit` that becomes `null`, and a new file in a review shows no diff and
 * `+0 −0`, which is wrong in exactly the place the number matters.
 */
async function gitNoIndex(
  cwd: string,
  extra: string[],
  filePath: string,
): Promise<string | null> {
  const nullDevice = process.platform === "win32" ? "NUL" : "/dev/null";
  const result = await execa(
    "git",
    ["diff", "--no-index", ...extra, "--", nullDevice, filePath],
    { ...GIT_OPTIONS, cwd },
  ).catch(() => null);
  if (!result || (result.exitCode !== 0 && result.exitCode !== 1)) {
    return null;
  }
  return typeof result.stdout === "string" ? result.stdout : null;
}

/** The repository root containing `cwd`, or null when there is none. */
export async function repositoryRoot(cwd: string): Promise<string | null> {
  const root = await tryGit(cwd, ["rev-parse", "--show-toplevel"]);
  return root ? path.normalize(root.trim()) : null;
}

/* -------------------------------------------------------------------------- */
/* Parsers                                                                     */
/* -------------------------------------------------------------------------- */

const STATUS_LETTERS: Record<string, ChangeStatus> = {
  A: "added",
  M: "modified",
  D: "deleted",
  R: "renamed",
  C: "added",
  T: "modified",
  U: "modified",
  "?": "untracked",
};

/**
 * `git status --porcelain=v1 -z --branch --untracked-files=all`.
 *
 * NUL-separated because a path with a newline in it is legal and a
 * line-oriented parser silently drops the rest of the list when it meets one.
 * A rename record is two NUL-terminated entries in a row: the new path, then
 * the old one.
 */
export function parsePorcelainStatus(output: string): {
  branch: string | null;
  unborn: boolean;
  ahead: number;
  behind: number;
  files: Omit<ChangedFile, "insertions" | "deletions" | "binary">[];
} {
  const records = output.split("\0");
  let branch: string | null = null;
  let unborn = false;
  let ahead = 0;
  let behind = 0;
  const files: Omit<ChangedFile, "insertions" | "deletions" | "binary">[] = [];

  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    if (!record) {
      continue;
    }

    if (record.startsWith("## ")) {
      const header = record.slice(3);
      // `## main...origin/main [ahead 2, behind 1]`, or
      // `## No commits yet on main`.
      if (header.startsWith("No commits yet on ")) {
        unborn = true;
        branch = header.slice("No commits yet on ".length).trim();
        continue;
      }
      // `git status -z --branch` writes `## HEAD (no branch)` when HEAD is
      // detached. Testing the whole header rather than the parsed name: the
      // space in it is what the split below would otherwise eat, leaving a
      // branch called "HEAD".
      if (header.startsWith("HEAD (no branch)")) {
        continue;
      }
      const [names, tracking] = splitOnce(header, " ");
      branch = splitOnce(names, "...")[0] || null;
      ahead = Number(/ahead (\d+)/.exec(tracking ?? "")?.[1] ?? 0);
      behind = Number(/behind (\d+)/.exec(tracking ?? "")?.[1] ?? 0);
      continue;
    }

    // `XY path`, where X is the index status and Y the worktree's.
    const codes = record.slice(0, 2);
    const filePath = record.slice(3);
    if (!filePath) {
      continue;
    }
    const staged = codes[0] ?? " ";
    const unstaged = codes[1] ?? " ";
    const letter = staged !== " " && staged !== "?" ? staged : unstaged;
    const status = STATUS_LETTERS[letter] ?? "modified";

    if (staged === "R" || staged === "C") {
      // The old path is the next NUL-terminated record.
      const oldPath = records[index + 1];
      index += 1;
      files.push({ path: filePath, status, ...(oldPath ? { oldPath } : {}) });
      continue;
    }
    files.push({ path: filePath, status });
  }

  return { branch, unborn, ahead, behind, files };
}

/**
 * `git diff --numstat -z`: `<insertions>\t<deletions>\t<path>`, with `-` for
 * both counts when the file is binary. A rename is three NUL-separated fields
 * instead of one path: an empty path, then old, then new.
 */
export function parseNumstat(output: string): Map<
  string,
  { insertions: number; deletions: number; binary: boolean; oldPath?: string }
> {
  const counts = new Map<
    string,
    { insertions: number; deletions: number; binary: boolean; oldPath?: string }
  >();
  const records = output.split("\0");

  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    if (!record) {
      continue;
    }
    const parts = record.split("\t");
    if (parts.length < 3) {
      continue;
    }
    const [rawInsertions, rawDeletions, rawPath] = parts as [string, string, string];
    const binary = rawInsertions === "-" || rawDeletions === "-";
    const entry = {
      insertions: binary ? 0 : Number(rawInsertions) || 0,
      deletions: binary ? 0 : Number(rawDeletions) || 0,
      binary,
    };

    if (rawPath === "") {
      // Rename: the old and new paths are the next two records.
      const oldPath = records[index + 1] ?? "";
      const newPath = records[index + 2] ?? "";
      index += 2;
      if (newPath) {
        counts.set(newPath, { ...entry, oldPath });
      }
      continue;
    }
    counts.set(rawPath, entry);
  }

  return counts;
}

/** `a...b` -> `["a", "b"]`; no separator -> `["a...b", ""]`. */
function splitOnce(value: string, separator: string): [string, string] {
  const at = value.indexOf(separator);
  return at < 0 ? [value, ""] : [value.slice(0, at), value.slice(at + separator.length)];
}

/* -------------------------------------------------------------------------- */
/* Status                                                                      */
/* -------------------------------------------------------------------------- */

/** The empty answer, for a directory that is not a repository. */
export function emptyStatus(): GitStatus {
  return {
    isRepository: false,
    branch: null,
    unborn: false,
    ahead: 0,
    behind: 0,
    files: [],
    insertions: 0,
    deletions: 0,
  };
}

/**
 * What has changed, with per-file counts.
 *
 * Untracked files get counts too, by diffing them against the empty blob —
 * `git diff --numstat` says nothing about a file git has never seen, and a
 * review that shows a new 400-line file as `+0 −0` is wrong in the one place
 * the number matters.
 */
export async function status(cwd: string, scope: DiffScope = { kind: "working-tree" }): Promise<GitStatus> {
  const root = await repositoryRoot(cwd);
  if (!root) {
    return emptyStatus();
  }

  const porcelain = parsePorcelainStatus(
    await git(root, ["status", "--porcelain=v1", "-z", "--branch", "--untracked-files=all"]),
  );

  const files =
    scope.kind === "working-tree"
      ? await workingTreeFiles(root, porcelain)
      : await rangeFiles(root, scope, porcelain);

  return {
    isRepository: true,
    branch: porcelain.branch,
    unborn: porcelain.unborn,
    ahead: porcelain.ahead,
    behind: porcelain.behind,
    files,
    insertions: files.reduce((total, file) => total + file.insertions, 0),
    deletions: files.reduce((total, file) => total + file.deletions, 0),
  };
}

async function workingTreeFiles(
  root: string,
  porcelain: ReturnType<typeof parsePorcelainStatus>,
): Promise<ChangedFile[]> {
  // Tracked changes, staged and unstaged in one number: the review shows the
  // working tree against HEAD, which is what "22 files changed" means.
  const numstat = porcelain.unborn
    ? new Map()
    : parseNumstat(await git(root, ["diff", "--numstat", "-z", "-M", "HEAD"]));

  const files: ChangedFile[] = [];
  for (const file of porcelain.files) {
    const counted = numstat.get(file.path);
    if (counted) {
      files.push({ ...file, ...counted, oldPath: counted.oldPath ?? file.oldPath });
      continue;
    }
    if (file.status === "untracked") {
      files.push({ ...file, ...(await countUntracked(root, file.path)) });
      continue;
    }
    files.push({ ...file, insertions: 0, deletions: 0, binary: false });
  }
  return files.sort((left, right) => left.path.localeCompare(right.path));
}

/**
 * An untracked file's counts, read off the file rather than out of git.
 *
 * `git diff --no-index /dev/null <file>` gives the same answer, and for a
 * checkout with sixty new files that is sixty process spawns before the review
 * can draw its header — the difference between "instant" and "three seconds".
 * A file git has never seen is entirely insertions, so the answer is its line
 * count, and "binary" is the same NUL-byte test git itself uses.
 */
async function countUntracked(root: string, filePath: string) {
  const fs = await import("node:fs/promises");
  const buffer = await fs.readFile(path.join(root, filePath)).catch(() => null);
  if (!buffer) {
    return { insertions: 0, deletions: 0, binary: false };
  }
  const sample = buffer.subarray(0, Math.min(buffer.byteLength, 8000));
  if (sample.includes(0)) {
    return { insertions: 0, deletions: 0, binary: true };
  }
  let lines = 0;
  for (const byte of buffer) {
    if (byte === 0x0a) {
      lines += 1;
    }
  }
  // A file with no trailing newline still has a last line.
  if (buffer.byteLength > 0 && buffer[buffer.byteLength - 1] !== 0x0a) {
    lines += 1;
  }
  return { insertions: lines, deletions: 0, binary: false };
}

async function rangeFiles(
  root: string,
  scope: DiffScope,
  porcelain: ReturnType<typeof parsePorcelainStatus>,
): Promise<ChangedFile[]> {
  const base = await baseRevision(root, scope);
  if (!base) {
    return [];
  }
  const numstat = parseNumstat(await git(root, ["diff", "--numstat", "-z", "-M", base]));
  const nameStatus = await git(root, ["diff", "--name-status", "-z", "-M", base]);
  const statuses = parseNameStatus(nameStatus);

  const files: ChangedFile[] = [...numstat.entries()].map(([filePath, counted]) => ({
    path: filePath,
    status: statuses.get(filePath) ?? "modified",
    insertions: counted.insertions,
    deletions: counted.deletions,
    binary: counted.binary,
    ...(counted.oldPath ? { oldPath: counted.oldPath } : {}),
  }));

  // An open-ended range — `git diff <base>` with no second revision — is
  // measured against the working tree, and `git diff` says nothing about a
  // file git has never seen. Without this a "since this turn began" review of
  // a turn whose whole output was new files shows nothing at all, which is the
  // one case the scope exists for.
  if (openEnded(scope)) {
    for (const file of porcelain.files) {
      if (file.status === "untracked" && !numstat.has(file.path)) {
        files.push({ ...file, ...(await countUntracked(root, file.path)) });
      }
    }
  }

  return files.sort((left, right) => left.path.localeCompare(right.path));
}

/** True when the scope's second side is the working tree rather than a revision. */
function openEnded(scope: DiffScope): boolean {
  return scope.kind === "since" || (scope.kind === "range" && !scope.to);
}

/** `git diff --name-status -z`: a status letter and a path per record. */
export function parseNameStatus(output: string): Map<string, ChangeStatus> {
  const statuses = new Map<string, ChangeStatus>();
  const records = output.split("\0");
  for (let index = 0; index < records.length; index += 1) {
    const code = records[index];
    if (!code) {
      continue;
    }
    const letter = code[0] as string;
    const status = STATUS_LETTERS[letter] ?? "modified";
    if (letter === "R" || letter === "C") {
      const newPath = records[index + 2];
      index += 2;
      if (newPath) {
        statuses.set(newPath, status);
      }
      continue;
    }
    const filePath = records[index + 1];
    index += 1;
    if (filePath) {
      statuses.set(filePath, status);
    }
  }
  return statuses;
}

/** The revision a scope is measured from. */
async function baseRevision(root: string, scope: DiffScope): Promise<string | null> {
  if (scope.kind === "range") {
    return scope.to ? `${scope.from}..${scope.to}` : scope.from;
  }
  if (scope.kind === "since") {
    // The newest commit at or before that time; nothing there means the whole
    // history is newer, so the range is the root commit.
    const revision = await tryGit(root, ["rev-list", "-1", `--before=${scope.since}`, "HEAD"]);
    const trimmed = revision?.trim();
    return trimmed || (await tryGit(root, ["rev-list", "--max-parents=0", "-1", "HEAD"]))?.trim() || null;
  }
  return "HEAD";
}

/* -------------------------------------------------------------------------- */
/* Diffs                                                                       */
/* -------------------------------------------------------------------------- */

/**
 * The two sides of one file, for the diff editor.
 *
 * Monaco's diff editor renders from two texts, not from a unified patch, so
 * that is what is fetched: the blob at the base revision and the file as it is
 * now. Doing the same thing by parsing a unified patch would mean
 * reconstructing the unchanged context lines the patch omits.
 */
export async function fileDiff(
  cwd: string,
  filePath: string,
  scope: DiffScope = { kind: "working-tree" },
): Promise<FileDiff> {
  const root = await repositoryRoot(cwd);
  if (!root) {
    throw new GitError("not a git repository");
  }

  // Scoped to the one path. Asking `status()` for the metadata instead would
  // walk the whole working tree once per open section, and a review of forty
  // files opens three sections before it has drawn.
  const meta = await fileMeta(root, filePath, scope);
  if (meta.binary) {
    return { ...meta, before: null, after: null };
  }

  const base = await baseRevision(root, scope);
  const beforePath = meta.oldPath ?? filePath;

  const before =
    meta.status === "added" || meta.status === "untracked" || !base
      ? ""
      : ((await tryGit(root, ["show", `${base.split("..")[0] ?? base}:${beforePath}`])) ?? "");

  const after =
    meta.status === "deleted"
      ? ""
      : // An open-ended scope's second side is the working tree, not a
        // revision: "since this turn began" has to show the edit the agent
        // has not committed, which is every edit it just made.
        scope.kind === "working-tree" || openEnded(scope)
        ? await readWorkingCopy(root, filePath)
        : ((await tryGit(root, ["show", `${scopeTip(scope)}:${filePath}`])) ?? "");

  return { ...meta, before, after };
}

/** One file's status and counts, without walking the tree. */
async function fileMeta(
  root: string,
  filePath: string,
  scope: DiffScope,
): Promise<Omit<FileDiff, "before" | "after">> {
  const base = (await baseRevision(root, scope)) ?? "HEAD";
  const numstat = parseNumstat(
    (await tryGit(root, ["diff", "--numstat", "-z", "-M", base, "--", filePath])) ?? "",
  );
  const statuses = parseNameStatus(
    (await tryGit(root, ["diff", "--name-status", "-z", "-M", base, "--", filePath])) ?? "",
  );
  const counted = numstat.get(filePath);

  if (counted) {
    return {
      path: filePath,
      status: statuses.get(filePath) ?? "modified",
      insertions: counted.insertions,
      deletions: counted.deletions,
      binary: counted.binary,
      ...(counted.oldPath ? { oldPath: counted.oldPath } : {}),
    };
  }

  // Nothing against the base means git has never seen it: it is untracked.
  return { path: filePath, status: "untracked", ...(await countUntracked(root, filePath)) };
}

function scopeTip(scope: DiffScope): string {
  return scope.kind === "range" && scope.to ? scope.to : "HEAD";
}

async function readWorkingCopy(root: string, filePath: string): Promise<string> {
  const fs = await import("node:fs/promises");
  return fs.readFile(path.join(root, filePath), "utf8").catch(() => "");
}

/**
 * The unified patch for one file — what a person copies out of a review, and
 * what `Commit or push` is describing.
 */
export async function unifiedDiff(
  cwd: string,
  filePath: string,
  scope: DiffScope = { kind: "working-tree" },
): Promise<string> {
  const root = await repositoryRoot(cwd);
  if (!root) {
    throw new GitError("not a git repository");
  }
  const base = await baseRevision(root, scope);
  const args = ["diff", "-M", "--patch"];
  if (scope.kind === "working-tree") {
    args.push("HEAD");
  } else if (base) {
    args.push(base);
  }
  args.push("--", filePath);
  const patch = await tryGit(root, args);
  if (patch && patch.trim() !== "") {
    return patch;
  }
  // An untracked file has no patch against HEAD; `--no-index` produces one.
  return (await gitNoIndex(root, ["--patch"], filePath)) ?? "";
}

/* -------------------------------------------------------------------------- */
/* Committing                                                                  */
/* -------------------------------------------------------------------------- */

/**
 * Stage everything and commit. The review tab's `Commit`.
 *
 * `--no-verify` is deliberately *not* passed: a repository's hooks are part of
 * how it wants to be committed to, and skipping them from a GUI is how a
 * broken commit gets made without anyone deciding to make one.
 */
export async function commitAll(cwd: string, message: string): Promise<{ sha: string }> {
  const root = await repositoryRoot(cwd);
  if (!root) {
    throw new GitError("not a git repository");
  }
  if (message.trim() === "") {
    throw new GitError("a commit needs a message");
  }
  await git(root, ["add", "-A"]);
  await git(root, ["commit", "-m", message]);
  const sha = (await git(root, ["rev-parse", "HEAD"])).trim();
  return { sha };
}

/** Push the current branch, setting upstream when it has none. */
export async function push(cwd: string): Promise<void> {
  const root = await repositoryRoot(cwd);
  if (!root) {
    throw new GitError("not a git repository");
  }
  const branch = (await git(root, ["rev-parse", "--abbrev-ref", "HEAD"])).trim();
  if (branch === "HEAD") {
    throw new GitError("cannot push a detached HEAD");
  }
  const upstream = await tryGit(root, ["rev-parse", "--abbrev-ref", `${branch}@{upstream}`]);
  await git(root, upstream ? ["push"] : ["push", "--set-upstream", "origin", branch]);
}

/* -------------------------------------------------------------------------- */
/* Repository detection (P7)                                                   */
/* -------------------------------------------------------------------------- */

/**
 * What the composer's git-mode chip needs to know before it offers a mode,
 * and what the settings page prints beside a project.
 *
 * One call, because every field is cheap and the caller wants all of them:
 * asking four channels whether a directory is a repository, on what branch,
 * tracking what, and whether it is dirty, is four round trips to answer one
 * question.
 */
export type RepoInfo = {
  isRepository: boolean;
  /** The repository root, which is not necessarily the directory asked about. */
  root: string | null;
  branch: string | null;
  /** `origin/main`, or null when the branch tracks nothing. */
  upstream: string | null;
  /** The remote's default branch, for a pull request's base. */
  defaultBranch: string | null;
  /** Any staged, unstaged or untracked change. */
  dirty: boolean;
  detached: boolean;
  /** HEAD points at a branch with no commits: nothing can be branched from it. */
  unborn: boolean;
  hasRemote: boolean;
};

export function emptyRepoInfo(): RepoInfo {
  return {
    isRepository: false,
    root: null,
    branch: null,
    upstream: null,
    defaultBranch: null,
    dirty: false,
    detached: false,
    unborn: false,
    hasRemote: false,
  };
}

export async function repoInfo(cwd: string): Promise<RepoInfo> {
  const root = await repositoryRoot(cwd);
  if (!root) {
    return emptyRepoInfo();
  }

  const [branchName, symbolic, porcelain, remotes, verified] = await Promise.all([
    tryGit(root, ["rev-parse", "--abbrev-ref", "HEAD"]),
    // `rev-parse --abbrev-ref HEAD` fails outright in a repository with no
    // commits, so the branch git *would* create comes from `symbolic-ref`.
    // Without it a fresh `git init` reads as detached, and the mode chip would
    // say a repository has no branch when the person is standing on one.
    tryGit(root, ["symbolic-ref", "--short", "HEAD"]),
    // `-z` and `--untracked-files=all`: the same read `status()` makes, so
    // "dirty" here and "there are changes to review" there cannot disagree.
    tryGit(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]),
    tryGit(root, ["remote"]),
    // No commits yet: `rev-parse HEAD` fails while `--abbrev-ref HEAD` still
    // names the branch git would create on the first commit.
    tryGit(root, ["rev-parse", "--verify", "HEAD"]),
  ]);

  const branch = (branchName?.trim() || symbolic?.trim()) ?? "";
  const detached = branch === "HEAD" || branch === "";

  const upstream = detached
    ? null
    : (await tryGit(root, ["rev-parse", "--abbrev-ref", `${branch}@{upstream}`]))?.trim() || null;

  return {
    isRepository: true,
    root,
    branch: detached ? null : branch,
    upstream,
    defaultBranch: await defaultBranchOf(root),
    dirty: (porcelain ?? "").split("\0").some((record) => record !== ""),
    detached,
    unborn: verified === null,
    hasRemote: (remotes ?? "").trim() !== "",
  };
}

/**
 * The branch a pull request should target.
 *
 * `origin/HEAD` is the remote's own answer and what `gh` uses; a checkout
 * cloned before the default was renamed may not have it, so the fallback is
 * whichever of the usual two exists on the remote, and then nothing — a null
 * base lets `gh` pick, which is better than guessing `master` at a repository
 * that has not had one for five years.
 */
async function defaultBranchOf(root: string): Promise<string | null> {
  const symbolic = await tryGit(root, ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"]);
  const named = symbolic?.trim().replace(/^origin\//, "");
  if (named) {
    return named;
  }
  for (const candidate of ["main", "master"]) {
    if (await tryGit(root, ["rev-parse", "--verify", `refs/remotes/origin/${candidate}`])) {
      return candidate;
    }
  }
  return null;
}

/** The commit HEAD is at, or null in a repository with no commits. */
export async function head(cwd: string): Promise<string | null> {
  const sha = await tryGit(cwd, ["rev-parse", "HEAD"]);
  return sha?.trim() || null;
}

/** Whether anything is uncommitted — the check `removeWorktree` refuses on. */
export async function isDirty(cwd: string): Promise<boolean> {
  const porcelain = await tryGit(cwd, [
    "status",
    "--porcelain=v1",
    "-z",
    "--untracked-files=all",
  ]);
  return (porcelain ?? "").split("\0").some((record) => record !== "");
}

/* -------------------------------------------------------------------------- */
/* Slugs                                                                       */
/* -------------------------------------------------------------------------- */

/**
 * A directory and branch name made from a session's first prompt.
 *
 * Lowercase ASCII words joined by hyphens, because the name becomes both a
 * path component and a git ref: a ref may not contain a space, `~^:?*[\`, two
 * consecutive dots or a trailing dot, and a path on Windows may not contain
 * `<>:"|?*`. Restricting to `[a-z0-9-]` satisfies both without a table of
 * per-platform exceptions.
 *
 * Input with nothing left after the filter answers `""`: what a nameless
 * session is called is a product decision, and this is a string function.
 */
export function slugify(name: string, max = 40): string {
  const slug = name
    .normalize("NFKD")
    // Strip the combining marks NFKD just separated, so "Modèle" becomes
    // "modele" rather than "mod-le". `\p{M}` and not `\p{Diacritic}`: the
    // latter also matches the ASCII `^`, `~`, `` ` `` and `"`, which are
    // separators here and would be deleted, gluing two words together.
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (slug.length <= max) {
    return slug;
  }
  // Cut at a word boundary when there is one near the limit, so the name stays
  // readable instead of ending mid-word.
  const cut = slug.slice(0, max);
  const boundary = cut.lastIndexOf("-");
  return (boundary > max / 2 ? cut.slice(0, boundary) : cut).replace(/-+$/, "");
}

/* -------------------------------------------------------------------------- */
/* Worktrees                                                                   */
/* -------------------------------------------------------------------------- */

export type WorktreeInfo = {
  /** Absolute path, normalised. */
  path: string;
  /** Short branch name, or null when the worktree is detached. */
  branch: string | null;
  head: string | null;
  bare: boolean;
  detached: boolean;
  locked: boolean;
  /** The repository's own working tree — the one that cannot be removed. */
  primary: boolean;
};

/**
 * `git worktree list --porcelain [-z]`.
 *
 * Both forms parse here. With `-z` every attribute is NUL-terminated and a
 * record ends with an extra NUL; without it they are newline-terminated. The
 * only difference is the terminator, so the NULs are folded to newlines and
 * one parser reads both — and `-z` is what is asked for, so a path with a
 * newline in it does not silently end the record.
 *
 * The first record is always the main working tree.
 */
export function parseWorktreeList(output: string): WorktreeInfo[] {
  const worktrees: WorktreeInfo[] = [];
  let current: WorktreeInfo | null = null;

  for (const line of output.replace(/\0/g, "\n").split("\n")) {
    if (line === "") {
      continue;
    }
    const [key, value] = splitOnce(line, " ");
    if (key === "worktree") {
      current = {
        path: path.normalize(value),
        branch: null,
        head: null,
        bare: false,
        detached: false,
        locked: false,
        primary: worktrees.length === 0,
      };
      worktrees.push(current);
      continue;
    }
    if (!current) {
      continue;
    }
    if (key === "HEAD") {
      current.head = value;
    } else if (key === "branch") {
      current.branch = value.replace(/^refs\/heads\//, "");
    } else if (key === "bare") {
      current.bare = true;
    } else if (key === "detached") {
      current.detached = true;
    } else if (key === "locked") {
      current.locked = true;
    }
  }

  return worktrees;
}

/** Every worktree of the repository containing `cwd`, the main one first. */
export async function listWorktrees(cwd: string): Promise<WorktreeInfo[]> {
  const root = await repositoryRoot(cwd);
  if (!root) {
    return [];
  }
  // `-z` first; a git too old for it fails, and the plain form parses the same.
  const zero = await tryGit(root, ["worktree", "list", "--porcelain", "-z"]);
  const output = zero ?? (await tryGit(root, ["worktree", "list", "--porcelain"])) ?? "";
  return parseWorktreeList(output);
}

export type CreateWorktreeOptions = {
  /** Any directory inside the repository to branch from. */
  repoPath: string;
  /** Where the worktree directory goes: `<worktreeRoot>/<project>`. */
  parentDir: string;
  /** The name to slugify — a session's first prompt, usually. */
  name?: string;
  /** From settings; `hardcore/` by default. */
  branchPrefix?: string;
  /** From settings: fetch the remote first, so the branch starts from the server. */
  fetch?: boolean;
  /** What to branch from. Defaults to HEAD. */
  base?: string;
};

export type CreatedWorktree = {
  path: string;
  branch: string;
  /** The revision the branch was cut from, for the record. */
  base: string;
};

/**
 * A new branch in a new worktree under `parentDir` (plan §9).
 *
 * Worktrees live outside the project on purpose: one inside the checkout is a
 * directory the project's own tools index, test and lint, and every agent
 * working in one would see all the others' trees.
 *
 * The name is made unique against both the filesystem and the ref namespace
 * before `git worktree add` runs. Letting git fail on the collision instead
 * would be one error message for two different problems — a directory in the
 * way, and a branch someone else is already on.
 */
export async function createWorktree(options: CreateWorktreeOptions): Promise<CreatedWorktree> {
  const root = await repositoryRoot(options.repoPath);
  if (!root) {
    throw new GitError("Project is not a git repository, worktree mode unavailable");
  }
  if ((await head(root)) === null) {
    throw new GitError("This repository has no commits yet, so there is nothing to branch from");
  }

  if (options.fetch) {
    // Best-effort: a laptop on a plane must still get a worktree. The branch
    // then starts from what the checkout already has, which is what the user
    // would get by hand.
    await tryGit(root, ["fetch", "--quiet", "--prune"]);
  }

  const prefix = options.branchPrefix ?? "hardcore/";
  const stem = slugify(options.name ?? "") || generatedName();
  const base = options.base ?? "HEAD";

  const { directory, branch } = await uniqueName(root, options.parentDir, prefix, stem);

  await fsp.mkdir(options.parentDir, { recursive: true });
  await git(root, ["worktree", "add", "-b", branch, directory, base]);

  return {
    path: path.normalize(directory),
    branch,
    base: (await head(directory)) ?? base,
  };
}

/** `session-4f2c`: enough to tell two nameless threads apart, short enough to read. */
function generatedName(): string {
  return `session-${Math.random().toString(16).slice(2, 6)}`;
}

/**
 * The first of `<stem>`, `<stem>-2`, `<stem>-3`… whose directory does not
 * exist and whose branch is not taken.
 */
async function uniqueName(
  root: string,
  parentDir: string,
  prefix: string,
  stem: string,
): Promise<{ directory: string; branch: string }> {
  for (let attempt = 1; attempt <= 100; attempt += 1) {
    const name = attempt === 1 ? stem : `${stem}-${attempt}`;
    const directory = path.join(parentDir, name);
    const branch = `${prefix}${name}`;
    const exists = await fsp.stat(directory).then(
      () => true,
      () => false,
    );
    if (exists) {
      continue;
    }
    if (await tryGit(root, ["rev-parse", "--verify", "--quiet", `refs/heads/${branch}`])) {
      continue;
    }
    return { directory, branch };
  }
  throw new GitError(`a hundred worktrees are already called ${stem}`);
}

/**
 * Remove a worktree's directory and git's registration of it.
 *
 * Uncommitted work is refused rather than discarded: `git worktree remove`
 * takes a `--force` that deletes it, and a button in a settings page is not
 * where someone decides to lose an afternoon. The branch is left behind —
 * deleting a checkout is reversible, deleting the commits on it is not.
 */
export async function removeWorktree(
  worktreePath: string,
  options: { force?: boolean } = {},
): Promise<void> {
  const root = await repositoryRoot(worktreePath);
  if (!root) {
    throw new GitError("that worktree is no longer a git repository");
  }
  const target = (await listWorktrees(root)).find((candidate) =>
    samePath(candidate.path, worktreePath),
  );
  if (!target) {
    throw new GitError("git does not know that worktree");
  }
  if (target.primary) {
    throw new GitError("that is the repository itself, not a worktree");
  }
  if (!options.force && (await isDirty(worktreePath))) {
    throw new GitError("that worktree has uncommitted changes");
  }
  await git(root, ["worktree", "remove", ...(options.force ? ["--force"] : []), worktreePath]);
}

/** Path comparison that survives a trailing separator and Windows' case rules. */
export function samePath(left: string, right: string): boolean {
  const normalise = (value: string) => path.normalize(value).replace(/[\\/]+$/, "");
  const a = normalise(left);
  const b = normalise(right);
  return process.platform === "win32" ? a.toLowerCase() === b.toLowerCase() : a === b;
}

export type PruneOptions = {
  repoPath: string;
  /** Only worktrees under here are considered: never one the user made. */
  parentDir: string;
  /** How many survive. */
  keep: number;
  /** Worktrees with an open session — never swept. */
  protectedPaths?: string[];
};

/**
 * Sweep the oldest worktrees past the keep limit (Settings › Git & Worktrees).
 *
 * Three things are never removed, and each is a separate promise to the user:
 * a worktree Hardcore did not create (outside `parentDir`), one a session is
 * still open on, and one with uncommitted changes. An automatic sweep that
 * could throw work away would make the setting unusable, so it is only ever
 * allowed to remove what the branch can recreate.
 */
export async function pruneWorktrees(options: PruneOptions): Promise<{ removed: string[] }> {
  const worktrees = await listWorktrees(options.repoPath);
  const kept = options.protectedPaths ?? [];

  const candidates: { path: string; usedAt: number }[] = [];
  for (const worktree of worktrees) {
    if (worktree.primary || worktree.locked || !isUnder(options.parentDir, worktree.path)) {
      continue;
    }
    if (kept.some((protectedPath) => samePath(protectedPath, worktree.path))) {
      continue;
    }
    const stat = await fsp.stat(worktree.path).catch(() => null);
    candidates.push({ path: worktree.path, usedAt: stat?.mtimeMs ?? 0 });
  }

  // Newest first, so the tail is what falls off the end of the limit.
  candidates.sort((left, right) => right.usedAt - left.usedAt);

  const removed: string[] = [];
  for (const candidate of candidates.slice(Math.max(0, options.keep))) {
    if (await isDirty(candidate.path)) {
      continue;
    }
    await removeWorktree(candidate.path).then(
      () => removed.push(candidate.path),
      // One worktree that will not go must not stop the sweep: the next launch
      // would meet the same one and the limit would never be enforced.
      () => undefined,
    );
  }
  return { removed };
}

/** True when `child` is inside `parent` — the test that keeps the sweep in its own root. */
export function isUnder(parent: string, child: string): boolean {
  const relative = path.relative(path.normalize(parent), path.normalize(child));
  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);
}

/* -------------------------------------------------------------------------- */
/* Pull requests                                                               */
/* -------------------------------------------------------------------------- */

let ghPath: Promise<string | null> | null = null;

/**
 * Where `gh` is, or null. Cached: the answer does not change while the app
 * runs, and the review header asks on every render.
 *
 * `env` matters. An app launched from the Dock inherits launchd's PATH, which
 * has never heard of Homebrew — the same reason `agents/shell-env.ts` exists.
 */
export function ghAvailable(env?: NodeJS.ProcessEnv, force = false): Promise<string | null> {
  if (!ghPath || force) {
    const command = process.platform === "win32" ? "where" : "which";
    ghPath = execa(command, ["gh"], {
      ...GIT_OPTIONS,
      ...(env ? { env, extendEnv: false } : {}),
    })
      .then((result) =>
        result.exitCode === 0 && typeof result.stdout === "string"
          ? (result.stdout.split(/\r?\n/)[0]?.trim() ?? null) || null
          : null,
      )
      .catch(() => null);
  }
  return ghPath;
}

export type PullRequestOptions = {
  title: string;
  body?: string;
  /** From settings. */
  draft?: boolean;
  /** Defaults to the remote's default branch, and then to gh's own guess. */
  base?: string | null;
  env?: NodeJS.ProcessEnv;
};

/**
 * Open a pull request with `gh`, pushing the branch first when it has no
 * upstream — `gh` would offer to do that interactively, and there is no
 * terminal here to answer it in.
 *
 * The URL comes back rather than being opened: whether a link opens in a
 * browser is the renderer's decision, and a main process that opened one as a
 * side effect would do it in the tests too.
 */
export async function createPullRequest(
  cwd: string,
  options: PullRequestOptions,
): Promise<{ url: string }> {
  const root = await repositoryRoot(cwd);
  if (!root) {
    throw new GitError("not a git repository");
  }
  if (!(await ghAvailable(options.env))) {
    throw new GitError("the GitHub CLI (gh) is not installed");
  }

  const branch = (await git(root, ["rev-parse", "--abbrev-ref", "HEAD"])).trim();
  if (branch === "HEAD") {
    throw new GitError("cannot open a pull request from a detached HEAD");
  }
  await push(root);

  const base = options.base ?? (await defaultBranchOf(root));
  const result = await execa(
    "gh",
    [
      "pr",
      "create",
      "--head",
      branch,
      ...(base ? ["--base", base] : []),
      ...(options.draft ? ["--draft"] : []),
      "--title",
      options.title,
      "--body",
      options.body ?? "",
    ],
    {
      ...GIT_OPTIONS,
      cwd: root,
      ...(options.env ? { env: options.env, extendEnv: false } : {}),
    },
  );

  const stdout = typeof result.stdout === "string" ? result.stdout : "";
  const stderr = typeof result.stderr === "string" ? result.stderr : "";
  const url = findUrl(stdout) ?? findUrl(stderr);
  if (!url) {
    throw new GitError(stderr.trim() || "gh did not print a pull request URL");
  }
  return { url };
}

/**
 * The URL in `gh`'s output.
 *
 * `gh pr create` prints the URL on its own line on success and, when the pull
 * request already exists, an error naming the existing one — which is the
 * answer the user wanted either way, so both are read the same.
 */
export function findUrl(output: string): string | null {
  return /https:\/\/\S+/.exec(output)?.[0]?.replace(/[.,)]+$/, "") ?? null;
}

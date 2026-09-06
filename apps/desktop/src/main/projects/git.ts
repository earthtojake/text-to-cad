/**
 * Git, as the review tab needs it: what changed, by how much, and the diff.
 *
 * The `git` CLI, not a library. Every answer here is one `git` invocation and
 * a parser, which means the app agrees with what the person sees in their own
 * terminal — including their `.gitattributes`, their `diff.external`, their
 * submodules and their line-ending config. A reimplementation of git's diff
 * that disagreed with git in one of those cases would be worse than no diff.
 *
 * **P7 owns the rest of this file's remit** (plan §9): the three git modes,
 * worktree creation and deletion, `Commit or push`'s push half and
 * `Create pull request`. What is here is what the review tab reads, plus the
 * commit it can make.
 *
 * The parsers are exported and pure: `git`'s porcelain formats are stable and
 * fiddly, and they are the part worth a unit test.
 */
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
      : await rangeFiles(root, scope);

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

async function rangeFiles(root: string, scope: DiffScope): Promise<ChangedFile[]> {
  const base = await baseRevision(root, scope);
  if (!base) {
    return [];
  }
  const numstat = parseNumstat(await git(root, ["diff", "--numstat", "-z", "-M", base]));
  const nameStatus = await git(root, ["diff", "--name-status", "-z", "-M", base]);
  const statuses = parseNameStatus(nameStatus);

  return [...numstat.entries()]
    .map(([filePath, counted]) => ({
      path: filePath,
      status: statuses.get(filePath) ?? "modified",
      insertions: counted.insertions,
      deletions: counted.deletions,
      binary: counted.binary,
      ...(counted.oldPath ? { oldPath: counted.oldPath } : {}),
    }))
    .sort((left, right) => left.path.localeCompare(right.path));
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
      : scope.kind === "working-tree"
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

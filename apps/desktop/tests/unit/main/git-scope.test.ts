/**
 * A review scope is renderer input, and its revisions become git argv. A
 * `from` of `--output=/any/file` would be read by `git diff` as an option and
 * write wherever it names, so a scope is checked before git is started at all.
 */
import { execFile } from "node:child_process";
import { mkdtemp, open, realpath, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import type * as Execa from "execa";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const execa = vi.hoisted(() => vi.fn());
vi.mock("execa", async (importOriginal) => {
  const actual = await importOriginal<typeof Execa>();
  execa.mockImplementation(actual.execa);
  return { ...actual, execa };
});

import * as git from "@main/projects/git";
import { diffScopeFor, resolveDiffScope, ReviewScopeSchema } from "@shared/types";

beforeEach(() => {
  execa.mockClear();
});

const run = promisify(execFile);
const scratch: string[] = [];
afterEach(async () => {
  await Promise.all(scratch.splice(0).map((directory) => rm(directory, { recursive: true, force: true })));
});

/** A fresh `git init` with one uncommitted file and no commits. */
async function unbornRepo(): Promise<string> {
  const directory = await realpath(await mkdtemp(path.join(os.tmpdir(), "t2c-unborn-")));
  scratch.push(directory);
  await run("git", ["init", "--quiet", "--initial-branch=main"], { cwd: directory });
  await writeFile(path.join(directory, "part.py"), "one\ntwo\n");
  return directory;
}

const hostile = [
  { kind: "range", from: "--output=/tmp/x" },
  { kind: "range", from: "HEAD" },
  { kind: "range", from: "abcdef12", to: "--output=/tmp/x" },
  { kind: "range", from: "abcdef12..HEAD" },
  { kind: "since", since: "--output=/tmp/x" },
  { kind: "since", since: "2 hours ago" },
] as const;

describe("review scopes", () => {
  it.each(hostile)("refuses %o before any git call", async (scope) => {
    await expect(git.status(process.cwd(), scope)).rejects.toThrow(git.GitError);
    await expect(git.fileDiff(process.cwd(), "a.txt", scope)).rejects.toThrow(git.GitError);
    await expect(git.unifiedDiff(process.cwd(), "a.txt", scope)).rejects.toThrow(git.GitError);
    expect(execa).not.toHaveBeenCalled();
  });

  it("refuses an unmarked scope that names neither session scope", async () => {
    const scope = { kind: "unmarked", scope: "--output=/tmp/x" } as unknown as git.DiffScope;
    await expect(git.status(process.cwd(), scope)).rejects.toThrow(git.GitError);
    expect(execa).not.toHaveBeenCalled();
  });

  it("accepts every scope the review header can send, and a recorded mark", () => {
    for (const named of ReviewScopeSchema.options) {
      expect(() => git.assertSafeScope(resolveDiffScope(diffScopeFor(named), null))).not.toThrow();
    }
    expect(() => git.assertSafeScope({ kind: "unmarked", scope: "turn" })).not.toThrow();
    expect(() => git.assertSafeScope({ kind: "unmarked", scope: "session" })).not.toThrow();
    const sha = "0123456789abcdef0123456789abcdef01234567";
    expect(() => git.assertSafeScope({ kind: "range", from: sha })).not.toThrow();
    expect(() => git.assertSafeScope({ kind: "range", from: sha, to: sha })).not.toThrow();
  });
});

/**
 * A session with no recorded mark has no revision to measure `Last turn` or
 * `This session` from. The answer is an empty review that says why — never the
 * working tree under the scope's name (docs/integrations.md: never silently
 * substitute a different revision).
 */
describe("a session scope with no recorded mark", () => {
  it("resolves to an explicit unmarked scope, not the working tree", () => {
    const marks = { turnHead: null, sessionHead: null };
    expect(resolveDiffScope({ kind: "turn" }, marks)).toEqual({ kind: "unmarked", scope: "turn" });
    expect(resolveDiffScope({ kind: "session" }, marks)).toEqual({ kind: "unmarked", scope: "session" });
    expect(resolveDiffScope({ kind: "turn" }, null)).toEqual({ kind: "unmarked", scope: "turn" });
    expect(resolveDiffScope({ kind: "turn" }, { turnHead: null, sessionHead: "aaa" })).toEqual({
      kind: "unmarked",
      scope: "turn",
    });
    // The other scopes are untouched.
    expect(resolveDiffScope(diffScopeFor("all"), null)).toEqual({ kind: "working-tree" });
    expect(resolveDiffScope(diffScopeFor("1h"), null)).toEqual({ kind: "since", since: "1 hour ago" });
  });

  it("status answers the repository with no files and names the missing mark, without diffing", async () => {
    for (const which of ["turn", "session"] as const) {
      execa.mockClear();
      const answer = await git.status(process.cwd(), { kind: "unmarked", scope: which });
      expect(answer).toMatchObject({ isRepository: true, files: [], insertions: 0, deletions: 0, unmarked: which });
      const diffed = execa.mock.calls.some((call) => (call[1] as string[] | undefined)?.includes("diff"));
      expect(diffed).toBe(false);
    }
  });

  it("the working-tree answer carries no unmarked reason", async () => {
    const answer = await git.status(process.cwd(), { kind: "working-tree" });
    expect(answer.unmarked).toBeUndefined();
  });

  it("every answer carries the working tree's file count, whatever the scope, so a commit button needs no second read", async () => {
    const directory = await unbornRepo();
    await writeFile(path.join(directory, "other.py"), "x\n");
    for (const scope of [{ kind: "working-tree" }, { kind: "unmarked", scope: "turn" }] as const) {
      expect((await git.status(directory, scope)).workingFiles).toBe(2);
    }
    // A repository with a recorded mark: the scope can be empty while the tree is not.
    const marked = await git.status(process.cwd(), { kind: "unmarked", scope: "session" });
    expect(marked.workingFiles).toBe((await git.status(process.cwd(), { kind: "working-tree" })).files.length);
  });

  it("a file's diff in an unmarked scope is refused with the reason, not answered from the working tree", async () => {
    await expect(git.fileDiff(process.cwd(), "package.json", { kind: "unmarked", scope: "turn" })).rejects.toThrow(
      /no turn recorded/i,
    );
    await expect(
      git.unifiedDiff(process.cwd(), "package.json", { kind: "unmarked", scope: "session" }),
    ).rejects.toThrow(/no session start recorded/i);
  });
});

/**
 * A repository with no commits cannot be marked: `rev-parse HEAD` has nothing
 * to name. That is not a missing record — every change in it is new since the
 * repository began, so the working tree is exactly the answer, and the review
 * says it is measuring from the start.
 */
describe("a session scope in a repository with no commits yet", () => {
  it("status answers the working tree, measured from the repository's start", async () => {
    const directory = await unbornRepo();
    for (const which of ["turn", "session"] as const) {
      const answer = await git.status(directory, { kind: "unmarked", scope: which });
      expect(answer.unmarked).toBeUndefined();
      expect(answer).toMatchObject({ unborn: true, fromStart: true, insertions: 2 });
      expect(answer.files.map((file) => file.path)).toEqual(["part.py"]);
    }
    expect((await git.status(directory, { kind: "working-tree" })).fromStart).toBeUndefined();
  });

  it("a file's diff is the file itself, not a refusal", async () => {
    const directory = await unbornRepo();
    const diff = await git.fileDiff(directory, "part.py", { kind: "unmarked", scope: "turn" });
    expect(diff).toMatchObject({ before: "", after: "one\ntwo\n", insertions: 2 });
    expect(await git.unifiedDiff(directory, "part.py", { kind: "unmarked", scope: "session" })).toMatch(/\+two/);
  });
});

describe("emptyTreeIfUnborn", () => {
  const EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904";
  /** A runner where HEAD is symbolic and `rev-parse --verify` ends as given. */
  const runner = (revParse: git.GitRunResult): git.GitRunner => async (cwd, args, input) => {
    if (args[0] === "symbolic-ref") return { exitCode: 0, stdout: "refs/heads/main\n", stderr: "", timedOut: false };
    if (args[0] === "rev-parse") return revParse;
    return git.runGit(cwd, args, input);
  };

  it("answers the empty tree only when rev-parse exits 1 with nothing on stderr", async () => {
    const cwd = await unbornRepo();
    expect(await git.emptyTreeIfUnborn(cwd)).toBe(EMPTY_TREE);
    expect(await git.emptyTreeIfUnborn(cwd, runner({ exitCode: 1, stdout: "", stderr: "", timedOut: false }))).toBe(EMPTY_TREE);
  });

  it("answers null when rev-parse failed for any other reason — git could not say", async () => {
    const cwd = await unbornRepo();
    // exit 128: a corrupt or locked ref, or not a repository.
    expect(await git.emptyTreeIfUnborn(cwd, runner({ exitCode: 128, stdout: "", stderr: "fatal: bad object HEAD", timedOut: false }))).toBeNull();
    // A timeout: killed, no exit code.
    expect(await git.emptyTreeIfUnborn(cwd, runner({ exitCode: undefined, stdout: "", stderr: "", timedOut: true }))).toBeNull();
    // A spawn error: no exit code, nothing said.
    expect(await git.emptyTreeIfUnborn(cwd, runner({ exitCode: undefined, stdout: "", stderr: "", timedOut: false }))).toBeNull();
    // Exit 1 that said something is not the quiet "does not resolve".
    expect(await git.emptyTreeIfUnborn(cwd, runner({ exitCode: 1, stdout: "", stderr: "error: unable to read", timedOut: false }))).toBeNull();
  });

  it("answers null when HEAD is not a symbolic ref", async () => {
    const cwd = await unbornRepo();
    const detached: git.GitRunner = async (directory, args, input) =>
      args[0] === "symbolic-ref" ? { exitCode: 1, stdout: "", stderr: "", timedOut: false } : git.runGit(directory, args, input);
    expect(await git.emptyTreeIfUnborn(cwd, detached)).toBeNull();
  });
});

/**
 * `Last turn` and `This session` are measured from the working tree as it
 * stood, not from HEAD: until something is committed a range from HEAD is
 * "all changes", and the turn would include everything before it.
 */
describe("snapshot marks", () => {
  const sh = (cwd: string, ...args: string[]) =>
    run("git", ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", ...args], { cwd }).then((r) => r.stdout.trim());

  async function committedRepo(): Promise<string> {
    const cwd = await unbornRepo();
    await sh(cwd, "add", "-A");
    await sh(cwd, "commit", "-q", "-m", "base");
    return cwd;
  }

  it("Last turn lists only what the turn changed, not earlier uncommitted work", async () => {
    const cwd = await committedRepo();
    // Turn one begins, and writes a.txt; turn two begins, and writes b.txt.
    const session = await git.snapshotTree(cwd, "s1/session");
    await git.snapshotTree(cwd, "s1/turn");
    await writeFile(path.join(cwd, "a.txt"), "from turn one\n");
    const turn2 = await git.snapshotTree(cwd, "s1/turn");
    await writeFile(path.join(cwd, "b.txt"), "from turn two\n");
    const marks = { turnHead: turn2, sessionHead: session };

    const last = await git.status(cwd, resolveDiffScope({ kind: "turn" }, marks));
    expect(last.files.map((file) => file.path)).toEqual(["b.txt"]);
    expect(last.files[0]).toMatchObject({ status: "untracked", insertions: 1 });
    // This session began before turn one, so it has both.
    const whole = await git.status(cwd, resolveDiffScope({ kind: "session" }, marks));
    expect(whole.files.map((file) => file.path)).toEqual(["a.txt", "b.txt"]);
    // The patch and both sides of a file agree with the list.
    expect(await git.unifiedDiff(cwd, "b.txt", resolveDiffScope({ kind: "turn" }, marks))).toContain("+from turn two");
    expect((await git.fileDiff(cwd, "b.txt", resolveDiffScope({ kind: "turn" }, marks))).after).toBe("from turn two\n");
  });

  it("a file modified in the turn is M against the snapshot, and one deleted is D", async () => {
    const cwd = await committedRepo();
    await writeFile(path.join(cwd, "part.py"), "one\ntwo\n three\n");
    await writeFile(path.join(cwd, "gone.txt"), "x\ny\n");
    const turn = await git.snapshotTree(cwd, "s2/turn");
    await writeFile(path.join(cwd, "part.py"), "one\ntwo\n three\nfour\n");
    await rm(path.join(cwd, "gone.txt"));
    const scope = resolveDiffScope({ kind: "turn" }, { turnHead: turn, sessionHead: turn });
    const listed = await git.status(cwd, scope);
    expect(listed.files).toEqual([
      expect.objectContaining({ path: "gone.txt", status: "deleted", insertions: 0, deletions: 2 }),
      expect.objectContaining({ path: "part.py", status: "modified", insertions: 1, deletions: 0 }),
    ]);
  });

  it("a read of a snapshot scope writes no objects, however much changed", async () => {
    const cwd = await committedRepo();
    await writeFile(path.join(cwd, "old.txt"), "there at the mark\n");
    const turn = await git.snapshotTree(cwd, "s4/turn");
    const scope = resolveDiffScope({ kind: "turn" }, { turnHead: turn, sessionHead: turn });
    // Reads run twice a second while an agent writes; `count-objects` counts the loose ones.
    const loose = async () => Number((await sh(cwd, "count-objects")).split(" ")[0]);
    await git.status(cwd, scope); // the first may write the empty blob an intent-to-add entry names
    const before = await loose();
    await writeFile(path.join(cwd, "big.bin"), "x".repeat(50_000));
    await writeFile(path.join(cwd, "part.py"), "rewritten\n");
    const listed = await git.status(cwd, scope);
    expect(listed.files.map((file) => file.path)).toEqual(["big.bin", "part.py"]);
    await git.fileDiff(cwd, "big.bin", scope);
    await git.unifiedDiff(cwd, "part.py", scope);
    expect(await loose()).toBe(before);
  });

  it("pins the tree under a ref, and dropMarks unpins it", async () => {
    const cwd = await committedRepo();
    const tree = await git.snapshotTree(cwd, "s3/turn");
    expect(await sh(cwd, "for-each-ref", "--format=%(refname) %(objectname)", "refs/text-to-cad/")).toBe(`refs/text-to-cad/s3/turn ${tree}`);
    await git.dropMarks(cwd, "s3");
    expect(await sh(cwd, "for-each-ref", "refs/text-to-cad/")).toBe("");
  });

  it("leaves an untracked file over the size limit out of the tree, and it still reads as untracked", async () => {
    const cwd = await committedRepo();
    const big = path.join(cwd, "part.step");
    const handle = await open(big, "w");
    await handle.truncate(20 * 1024 * 1024); // sparse: no disk, but git would hash all of it
    await handle.close();
    await writeFile(path.join(cwd, "small.txt"), "s\n");
    const blob = await sh(cwd, "hash-object", "part.step");
    const turn = await git.snapshotTree(cwd, "s5/turn");
    // `cat-file -e` fails for an object that was never written.
    await expect(sh(cwd, "cat-file", "-e", blob)).rejects.toThrow();
    expect(await sh(cwd, "ls-tree", "-r", "--name-only", turn ?? "")).toBe("part.py\nsmall.txt");
    const scope = resolveDiffScope({ kind: "turn" }, { turnHead: turn, sessionHead: turn });
    const listed = await git.status(cwd, scope);
    expect(listed.files).toEqual([expect.objectContaining({ path: "part.step", status: "untracked" })]);
  });

  /** The `git add` calls the spy has seen since it was last cleared. */
  const adds = () =>
    execa.mock.calls
      .filter((call) => (call[1] as string[] | undefined)?.[0] === "add")
      .map((call) => ({ args: call[1] as string[], input: (call[2] as { input?: string } | undefined)?.input }));

  it("a read adds only the untracked paths to its index, and reads with the same index reuse it", async () => {
    const cwd = await committedRepo();
    await writeFile(path.join(cwd, "old.txt"), "there at the mark\n");
    await writeFile(path.join(cwd, "older.txt"), "so was this\n");
    const turn = await git.snapshotTree(cwd, "s6/turn");
    const scope = resolveDiffScope({ kind: "turn" }, { turnHead: turn, sessionHead: turn });

    execa.mockClear();
    await git.status(cwd, scope);
    expect(adds()).toHaveLength(1);
    expect(adds()[0]?.args).not.toContain("-A");
    expect(adds()[0]?.input?.split("\0")).toEqual([":(literal)old.txt", ":(literal)older.txt"]);

    // Two more sections open on the same, unchanged repository.
    execa.mockClear();
    await git.fileDiff(cwd, "old.txt", scope);
    await git.unifiedDiff(cwd, "older.txt", scope);
    await git.status(cwd, scope);
    expect(adds()).toEqual([]);

    // A new untracked file is a different index.
    await writeFile(path.join(cwd, "new.txt"), "n\n");
    await git.status(cwd, scope);
    expect(adds()).toHaveLength(1);
  });

  it("a read whose index cannot be built fails, rather than reading earlier untracked files as deleted", async () => {
    const cwd = await committedRepo();
    await writeFile(path.join(cwd, "old.txt"), "there at the mark\n");
    const turn = await git.snapshotTree(cwd, "s7/turn");
    const scope = resolveDiffScope({ kind: "turn" }, { turnHead: turn, sessionHead: turn });
    const actual = await vi.importActual<typeof Execa>("execa");
    execa.mockImplementation(((file: string, args: string[], options: object) =>
      args[0] === "add"
        ? Promise.resolve({ failed: true, exitCode: 128, stdout: "", stderr: "fatal: unable to write new index file" })
        : actual.execa(file, args, options)) as never);
    try {
      await expect(git.status(cwd, scope)).rejects.toThrow(/unable to write new index file/);
      await expect(git.fileDiff(cwd, "old.txt", scope)).rejects.toThrow(git.GitError);
    } finally {
      execa.mockImplementation(actual.execa);
    }
  });

  it("leaves the person's index and staging alone", async () => {
    const cwd = await committedRepo();
    await writeFile(path.join(cwd, "staged.txt"), "s\n");
    await sh(cwd, "add", "staged.txt");
    await writeFile(path.join(cwd, "loose.txt"), "l\n");
    await git.snapshotTree(cwd);
    expect(await sh(cwd, "status", "--porcelain")).toBe("A  staged.txt\n?? loose.txt");
  });
});

describe("commits ahead", () => {
  it("a repository with no remote is not walked for unpushed commits", async () => {
    const cwd = await unbornRepo();
    const sh = (...args: string[]) => run("git", ["-c", "user.name=t", "-c", "user.email=t@example.com", ...args], { cwd });
    await sh("add", "-A");
    await sh("commit", "-q", "-m", "base");
    execa.mockClear();
    expect((await git.status(cwd)).ahead).toBe(0);
    expect((await git.pushState(cwd)).ahead).toBe(0);
    const walked = execa.mock.calls.some((call) => (call[1] as string[] | undefined)?.[0] === "rev-list");
    expect(walked).toBe(false);
  });
});

describe("unifiedDiff of a file that stopped changing", () => {
  it("is empty for a tracked file reverted since it was listed, not a new-file patch", async () => {
    const cwd = await unbornRepo();
    const sh = (...args: string[]) => run("git", ["-c", "user.name=t", "-c", "user.email=t@example.com", ...args], { cwd });
    await sh("add", "-A");
    await sh("commit", "-q", "-m", "base");
    await writeFile(path.join(cwd, "part.py"), "changed\n");
    expect((await git.status(cwd, { kind: "working-tree" })).files.map((file) => file.path)).toEqual(["part.py"]);
    await writeFile(path.join(cwd, "part.py"), "one\ntwo\n");
    expect(await git.unifiedDiff(cwd, "part.py", { kind: "working-tree" })).toBe("");
  });
});

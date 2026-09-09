/**
 * P7's half of `src/main/projects/git.ts`, against real repositories.
 *
 * Real `git`, not a mock. Every function here is a `git` invocation and a
 * parser, so a fake `git` would only be testing the fake: whether `git
 * worktree add -b` refuses a branch that already exists, whether `git worktree
 * remove` needs `--force` for a dirty tree, and what `--porcelain -z` actually
 * prints are the facts under test.
 *
 * The repositories are temporary directories built in `beforeEach`, and
 * `realpath`ed: on macOS `os.tmpdir()` is `/var/…`, git answers with
 * `/private/var/…`, and a path comparison between the two is a false negative
 * that looks like a bug in the code under test.
 */
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readdir, realpath, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import { afterEach, describe, expect, it } from "vitest";

import * as git from "@main/projects/git";

const run = promisify(execFile);

/** A fixed identity: a fresh CI runner has no `user.name` and `git commit` fails without one. */
const GIT_ENV = {
  ...process.env,
  GIT_AUTHOR_NAME: "Hardcore Tests",
  GIT_AUTHOR_EMAIL: "tests@example.invalid",
  GIT_COMMITTER_NAME: "Hardcore Tests",
  GIT_COMMITTER_EMAIL: "tests@example.invalid",
  GIT_CONFIG_GLOBAL: "/dev/null",
  GIT_CONFIG_SYSTEM: "/dev/null",
};

const temporary: string[] = [];

afterEach(async () => {
  for (const directory of temporary.splice(0)) {
    await rm(directory, { recursive: true, force: true });
  }
});

async function scratch(prefix: string): Promise<string> {
  const directory = await realpath(await mkdtemp(path.join(os.tmpdir(), prefix)));
  temporary.push(directory);
  return directory;
}

/** A repository with one commit, and a directory beside it for its worktrees. */
async function repository(): Promise<{ root: string; worktrees: string }> {
  const base = await scratch("hardcore-git-");
  const root = path.join(base, "project");
  const worktrees = path.join(base, "worktrees");
  await mkdir(root, { recursive: true });
  await git_(root, "init", "--quiet", "--initial-branch=main");
  await writeFile(path.join(root, "README.md"), "one\ntwo\n");
  await git_(root, "add", "-A");
  await git_(root, "commit", "--quiet", "-m", "first");
  return { root, worktrees };
}

function git_(cwd: string, ...args: string[]) {
  return run("git", args, { cwd, env: GIT_ENV });
}

/* -------------------------------------------------------------------------- */
/* Slugs                                                                       */
/* -------------------------------------------------------------------------- */

describe("slugify", () => {
  it("makes a name that is legal as both a path component and a git ref", () => {
    expect(git.slugify("Model the wrist path")).toBe("model-the-wrist-path");
    // Everything a ref may not contain, and everything Windows may not: gone.
    expect(git.slugify("fix: a~b^c:d?e*f[g]h\\i/j|k<l>m\"n")).toBe("fix-a-b-c-d-e-f-g-h-i-j-k-l-m-n");
    expect(git.slugify("Modèle du poignet")).toBe("modele-du-poignet");
    expect(git.slugify("  ...  ")).toBe("");
    expect(git.slugify("")).toBe("");
  });

  it("truncates at a word boundary and never ends on a hyphen", () => {
    const long = git.slugify("model the forearm to hand wrist path with a tendon route", 40);
    expect(long.length).toBeLessThanOrEqual(40);
    expect(long.endsWith("-")).toBe(false);
    // The cut lands on a word, not mid-word.
    expect(long).toBe("model-the-forearm-to-hand-wrist-path");
    // A single word longer than the limit has no boundary to cut at, so it is
    // cut where the limit falls rather than answering an empty string.
    expect(git.slugify("x".repeat(80), 10)).toBe("x".repeat(10));
  });
});

/* -------------------------------------------------------------------------- */
/* Parsers                                                                     */
/* -------------------------------------------------------------------------- */

describe("parseWorktreeList", () => {
  it("reads the newline form and the NUL form the same way", () => {
    const lines = [
      "worktree /repo",
      "HEAD abc123",
      "branch refs/heads/main",
      "",
      "worktree /wt/feature",
      "HEAD def456",
      "branch refs/heads/hardcore/feature",
      "locked",
      "",
      "worktree /wt/loose",
      "HEAD 999",
      "detached",
      "",
    ].join("\n");

    const fromLines = git.parseWorktreeList(lines);
    const fromNuls = git.parseWorktreeList(lines.replace(/\n/g, "\0"));
    expect(fromNuls).toEqual(fromLines);

    expect(fromLines).toHaveLength(3);
    expect(fromLines[0]).toMatchObject({ path: "/repo", branch: "main", primary: true });
    expect(fromLines[1]).toMatchObject({
      branch: "hardcore/feature",
      locked: true,
      primary: false,
    });
    expect(fromLines[2]).toMatchObject({ branch: null, detached: true });
  });
});

describe("findUrl", () => {
  it("takes gh's URL out of either stream, without trailing punctuation", () => {
    expect(git.findUrl("https://github.com/o/r/pull/12\n")).toBe("https://github.com/o/r/pull/12");
    expect(
      git.findUrl("a pull request for branch x already exists: https://github.com/o/r/pull/9."),
    ).toBe("https://github.com/o/r/pull/9");
    expect(git.findUrl("no url here")).toBeNull();
  });
});

describe("isUnder and samePath", () => {
  it("keeps the sweep inside its own root", () => {
    expect(git.isUnder("/a/b", "/a/b/c")).toBe(true);
    expect(git.isUnder("/a/b", "/a/b")).toBe(false);
    expect(git.isUnder("/a/b", "/a/bc")).toBe(false);
    expect(git.isUnder("/a/b", "/a")).toBe(false);
    expect(git.samePath("/a/b/", "/a/b")).toBe(true);
    expect(git.samePath("/a/b", "/a/c")).toBe(false);
  });
});

/* -------------------------------------------------------------------------- */
/* Repository detection                                                        */
/* -------------------------------------------------------------------------- */

describe("repoInfo", () => {
  it("answers empty for a directory that is not a repository", async () => {
    const plain = await scratch("hardcore-plain-");
    expect(await git.repoInfo(plain)).toEqual(git.emptyRepoInfo());
  });

  it("reports the branch, cleanliness and the absence of a remote", async () => {
    const { root } = await repository();
    expect(await git.repoInfo(root)).toMatchObject({
      isRepository: true,
      branch: "main",
      upstream: null,
      dirty: false,
      detached: false,
      unborn: false,
      hasRemote: false,
    });

    await writeFile(path.join(root, "new.txt"), "x");
    expect((await git.repoInfo(root)).dirty).toBe(true);
  });

  it("reports a repository with no commits as unborn", async () => {
    const base = await scratch("hardcore-unborn-");
    await git_(base, "init", "--quiet", "--initial-branch=main");
    const info = await git.repoInfo(base);
    expect(info).toMatchObject({ isRepository: true, unborn: true, branch: "main" });
    expect(await git.head(base)).toBeNull();
  });
});

/* -------------------------------------------------------------------------- */
/* Worktrees                                                                   */
/* -------------------------------------------------------------------------- */

describe("createWorktree", () => {
  it("puts the worktree under the parent directory and names the branch with the prefix", async () => {
    const { root, worktrees } = await repository();

    const created = await git.createWorktree({
      repoPath: root,
      parentDir: worktrees,
      name: "Model the wrist",
      branchPrefix: "hardcore/",
    });

    expect(created.path).toBe(path.join(worktrees, "model-the-wrist"));
    expect(created.branch).toBe("hardcore/model-the-wrist");
    expect(created.base).toBe(await git.head(root));
    // It is a real checkout of the repository, not an empty folder.
    expect(await readdir(created.path)).toContain("README.md");

    const listed = await git.listWorktrees(root);
    expect(listed).toHaveLength(2);
    expect(listed[0]?.primary).toBe(true);
    expect(listed[1]).toMatchObject({
      path: created.path,
      branch: "hardcore/model-the-wrist",
      primary: false,
    });
  });

  it("generates a name when there is nothing to slugify", async () => {
    const { root, worktrees } = await repository();
    const created = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "…" });
    expect(path.basename(created.path)).toMatch(/^session-[0-9a-f]{1,4}$/);
    expect(created.branch).toBe(`hardcore/${path.basename(created.path)}`);
  });

  it("suffixes a name whose directory or branch is taken", async () => {
    const { root, worktrees } = await repository();
    const first = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "wrist" });
    const second = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "wrist" });
    expect(path.basename(first.path)).toBe("wrist");
    expect(path.basename(second.path)).toBe("wrist-2");
    expect(second.branch).toBe("hardcore/wrist-2");

    // A branch that exists without a worktree also has to be stepped over:
    // `git worktree add -b` would fail on it.
    await git_(root, "branch", "hardcore/wrist-3");
    const third = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "wrist" });
    expect(third.branch).toBe("hardcore/wrist-4");
  });

  it("refuses a directory that is not a repository, in words a person can act on", async () => {
    const plain = await scratch("hardcore-plain-");
    await expect(
      git.createWorktree({ repoPath: plain, parentDir: path.join(plain, "wt") }),
    ).rejects.toThrow("Project is not a git repository, worktree mode unavailable");
  });

  it("refuses a repository with nothing to branch from", async () => {
    const base = await scratch("hardcore-unborn-");
    await git_(base, "init", "--quiet", "--initial-branch=main");
    await expect(
      git.createWorktree({ repoPath: base, parentDir: path.join(base, "wt") }),
    ).rejects.toThrow(/no commits yet/i);
  });
});

describe("removeWorktree", () => {
  it("removes a clean worktree and leaves its branch behind", async () => {
    const { root, worktrees } = await repository();
    const created = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "gone" });

    await git.removeWorktree(created.path);

    expect(await git.listWorktrees(root)).toHaveLength(1);
    // The checkout is recreatable; the commits on the branch are not, so the
    // branch stays.
    const branches = await git_(root, "branch", "--list", created.branch);
    expect(branches.stdout).toContain(created.branch);
  });

  it("refuses a dirty worktree unless it is forced", async () => {
    const { root, worktrees } = await repository();
    const created = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "busy" });
    await writeFile(path.join(created.path, "README.md"), "edited\n");

    await expect(git.removeWorktree(created.path)).rejects.toThrow("uncommitted changes");
    expect(await git.listWorktrees(root)).toHaveLength(2);

    await git.removeWorktree(created.path, { force: true });
    expect(await git.listWorktrees(root)).toHaveLength(1);
  });

  it("refuses the repository's own working tree", async () => {
    const { root } = await repository();
    await expect(git.removeWorktree(root)).rejects.toThrow("the repository itself");
  });
});

describe("pruneWorktrees", () => {
  it("keeps the newest, and never touches what it did not create", async () => {
    const { root, worktrees } = await repository();
    const elsewhere = path.join(path.dirname(worktrees), "mine");

    const made: string[] = [];
    for (const name of ["one", "two", "three"]) {
      const created = await git.createWorktree({ repoPath: root, parentDir: worktrees, name });
      made.push(created.path);
      // `git worktree add` for three worktrees in the same millisecond gives
      // them the same mtime, and the sweep's order would then be arbitrary.
      await touch(created.path, Date.now() - (3 - made.length) * 60_000);
    }
    const outside = await git.createWorktree({
      repoPath: root,
      parentDir: elsewhere,
      name: "handmade",
    });

    const { removed } = await git.pruneWorktrees({
      repoPath: root,
      parentDir: worktrees,
      keep: 1,
    });

    // "three" is newest and survives; "one" and "two" go; the worktree in
    // another directory is not the sweep's business at all.
    expect(removed.sort()).toEqual([made[0], made[1]].sort());
    const left = (await git.listWorktrees(root)).filter((worktree) => !worktree.primary);
    expect(left.map((worktree) => worktree.path).sort()).toEqual([made[2], outside.path].sort());
  });

  it("never removes one with an open session or uncommitted work", async () => {
    const { root, worktrees } = await repository();
    const busy = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "busy" });
    const held = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "held" });
    const spare = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "spare" });
    await writeFile(path.join(busy.path, "wip.txt"), "not committed\n");

    const { removed } = await git.pruneWorktrees({
      repoPath: root,
      parentDir: worktrees,
      keep: 0,
      protectedPaths: [held.path],
    });

    expect(removed).toEqual([spare.path]);
    const left = (await git.listWorktrees(root)).filter((worktree) => !worktree.primary);
    expect(left.map((worktree) => worktree.path).sort()).toEqual([busy.path, held.path].sort());
  });
});

/* -------------------------------------------------------------------------- */
/* Scopes                                                                      */
/* -------------------------------------------------------------------------- */

describe("status against a recorded revision", () => {
  it("includes files git has never seen, which is what a turn's output is", async () => {
    const { root } = await repository();
    const mark = (await git.head(root))!;

    // A turn: one commit, one edit on top of it, one brand new file.
    await writeFile(path.join(root, "README.md"), "one\ntwo\nthree\n");
    await git_(root, "commit", "--quiet", "-am", "the turn's commit");
    await writeFile(path.join(root, "README.md"), "one\ntwo\nthree\nfour\n");
    await writeFile(path.join(root, "made.txt"), "a\nb\nc\n");

    const scoped = await git.status(root, { kind: "range", from: mark });
    expect(scoped.files.map((file) => file.path).sort()).toEqual(["README.md", "made.txt"]);
    // The new file counts its lines rather than reporting +0, and the edit is
    // measured from the mark, not from the commit made since.
    expect(scoped.files.find((file) => file.path === "made.txt")).toMatchObject({
      status: "untracked",
      insertions: 3,
    });
    expect(scoped.files.find((file) => file.path === "README.md")?.insertions).toBe(2);
    expect(scoped.insertions).toBe(5);
  });

  it("shows the working copy as the second side, not the last commit", async () => {
    const { root } = await repository();
    const mark = (await git.head(root))!;
    await writeFile(path.join(root, "README.md"), "one\ntwo\ncommitted\n");
    await git_(root, "commit", "--quiet", "-am", "a commit after the mark");
    await writeFile(path.join(root, "README.md"), "one\ntwo\ncommitted\nuncommitted\n");

    const diff = await git.fileDiff(root, "README.md", { kind: "range", from: mark });
    expect(diff.before).toBe("one\ntwo\n");
    expect(diff.after).toContain("uncommitted");
  });
});

/** Set a directory's mtime, so the sweep's ordering is deterministic. */
async function touch(directory: string, at: number): Promise<void> {
  const { utimes } = await import("node:fs/promises");
  await utimes(directory, new Date(at), new Date(at));
}

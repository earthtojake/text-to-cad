/**
 * P7's half of `src/main/projects/git.ts` against real repositories: the
 * review tab's scopes and diffs, and opening a pull request.
 *
 * Real `git`, not a mock. Every function here is a `git` invocation and a
 * parser, so a fake `git` would only be testing the fake: whether `git
 * worktree add -b` refuses a branch that already exists, whether `git worktree
 * remove` needs `--force` for a dirty tree, and what `--porcelain -z` actually
 * prints are the facts under test.
 *
 * Each test's repository is a fresh temporary directory, copied from a
 * template this file builds once (`./git-fixtures`), and `realpath`ed: on
 * macOS `os.tmpdir()` is `/var/…`, git answers with `/private/var/…`, and a
 * path comparison between the two is a false negative that looks like a bug
 * in the code under test.
 */
import { mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { execa } from "execa";
import { afterAll, afterEach, describe, expect, it } from "vitest";

import * as git from "@main/projects/git";

import { cleanGitTemplates, committedRepository, GIT_ENV, gitIn as git_, pushedRepository } from "./git-fixtures";

const temporary: string[] = [];

afterEach(async () => {
  for (const directory of temporary.splice(0)) {
    await rm(directory, { recursive: true, force: true });
  }
});
afterAll(cleanGitTemplates);

async function scratch(prefix: string): Promise<string> {
  const directory = await realpath(await mkdtemp(path.join(os.tmpdir(), prefix)));
  temporary.push(directory);
  return directory;
}

/** A repository with one commit, and a directory beside it for its worktrees. */
async function repository(): Promise<{ root: string; worktrees: string }> {
  const base = await scratch("text-to-cad-git-");
  const root = path.join(base, "project");
  const worktrees = path.join(base, "worktrees");
  await committedRepository(root, "one\ntwo\n");
  return { root, worktrees };
}

describe("createPullRequest", () => {
  /** A `gh` on PATH that reports an existing pull request by `author` at `head`. */
  async function fakeGh(author: string, headOid: string) {
    const bin = await scratch("text-to-cad-gh-");
    const script = [
      "#!/bin/sh",
      'case "$1 $2" in',
      '  "pr create") echo \'a pull request for branch "text-to-cad/wrist" into branch "main" already exists:\' >&2;'
        + ' echo "https://github.com/o/r/pull/7" >&2; exit 1 ;;',
      `  "pr view") echo '{"author":{"login":"${author}"},"headRefOid":"${headOid}"}' ;;`,
      '  "api user") echo "me" ;;',
      "esac",
    ].join("\n");
    await writeFile(path.join(bin, "gh"), `${script}\n`, { mode: 0o755 });
    return { ...GIT_ENV, PATH: `${bin}${path.delimiter}${process.env.PATH ?? ""}` };
  }

  async function pushed() {
    const base = await scratch("text-to-cad-git-");
    const root = path.join(base, "project");
    const worktrees = path.join(base, "worktrees");
    await pushedRepository(root, path.join(base, "remote.git"), { readme: "one\ntwo\n" });
    const created = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "wrist" });
    return { cwd: created.path, head: (await git.head(created.path))! };
  }

  it("does not take someone else's pull request from a branch of the same name as this one", async () => {
    const { cwd, head } = await pushed();
    const env = await fakeGh("someone-else", head);
    await git.ghAvailable(env, true);
    await expect(git.createPullRequest(cwd, { title: "Wrist", env })).rejects.toThrow(
      "already exists, and it is not this one: https://github.com/o/r/pull/7",
    );
  });

  it("answers the existing pull request when it is the person's own, at the commit just pushed", async () => {
    const { cwd, head } = await pushed();
    const env = await fakeGh("me", head);
    await git.ghAvailable(env, true);
    await expect(git.createPullRequest(cwd, { title: "Wrist", env })).resolves.toEqual({
      url: "https://github.com/o/r/pull/7",
    });
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

describe("a since-period older than the whole history", () => {
  it("counts the first commit's own changes, not only what came after it", async () => {
    const { root } = await repository();
    await writeFile(path.join(root, "README.md"), "one\ntwo\nthree\n");
    await git_(root, "commit", "--quiet", "-am", "second");

    const since = await git.status(root, { kind: "since", since: "7 days ago" });
    // README.md was made by the first commit, minutes ago: all three lines are new.
    expect(since.files).toEqual([expect.objectContaining({ path: "README.md", status: "added", insertions: 3, deletions: 0 })]);
    const diff = await git.fileDiff(root, "README.md", { kind: "since", since: "7 days ago" });
    expect(diff).toMatchObject({ status: "added", before: "", after: "one\ntwo\nthree\n" });
  });
});

describe("a repository with no commits yet", () => {
  it("counts a staged file's lines rather than +0 −0", async () => {
    const base = await scratch("text-to-cad-unborn-");
    await git_(base, "init", "--quiet", "--initial-branch=main");
    await writeFile(path.join(base, "part.py"), "a\nb\n");
    await git_(base, "add", "part.py");
    await writeFile(path.join(base, "part.py"), "a\nb\nc\n");

    const status = await git.status(base);
    expect(status.files).toEqual([expect.objectContaining({ path: "part.py", insertions: 3, deletions: 0 })]);
  });
});

describe("a renamed file", () => {
  it("diffs against its old path, not as a new file", async () => {
    const { root } = await repository();
    const mark = (await git.head(root))!;
    await git_(root, "mv", "README.md", "NOTES.md");
    await writeFile(path.join(root, "NOTES.md"), "one\ntwo\nthree\n");

    for (const scope of [{ kind: "working-tree" as const }, { kind: "range" as const, from: mark }]) {
      const diff = await git.fileDiff(root, "NOTES.md", scope);
      expect(diff).toMatchObject({ status: "renamed", oldPath: "README.md", insertions: 1, deletions: 0 });
      expect(diff.before).toBe("one\ntwo\n");
      const patch = await git.unifiedDiff(root, "NOTES.md", scope);
      expect(patch).toContain("rename from README.md");
      expect(patch).toContain("+three");
    }
  });
});


describe("a diff side that cannot be read", () => {
  it("says so when git show fails, instead of rendering the side as empty", async () => {
    const { root } = await repository();
    await writeFile(path.join(root, "README.md"), "one\ntwo\nthree\n");
    const real = (await execa("which", ["git"])).stdout;
    const bin = await scratch("text-to-cad-nogitshow-");
    await writeFile(path.join(bin, "git"), `#!/bin/sh\nfor a in "$@"; do [ "$a" = show ] && { echo "fatal: unable to read blob" >&2; exit 128; }; done\nexec ${real} "$@"\n`, { mode: 0o755 });
    const original = process.env.PATH;
    process.env.PATH = `${bin}${path.delimiter}${original ?? ""}`;
    try {
      await expect(git.fileDiff(root, "README.md")).rejects.toThrow(/^could not read README\.md at HEAD: fatal: unable to read blob$/);
    } finally {
      process.env.PATH = original;
    }
  });

  it("draws a submodule as one line naming its commit, not an empty editor", async () => {
    const { root } = await repository();
    const inner = await scratch("text-to-cad-submodule-");
    await committedRepository(inner, "inner\n");
    await git_(root, "-c", "protocol.file.allow=always", "submodule", "add", "--quiet", inner, "sub");
    await git_(root, "commit", "--quiet", "-m", "add submodule");
    const before = (await git.head(path.join(root, "sub")))!;
    await writeFile(path.join(root, "sub", "next.txt"), "next\n");
    await git_(path.join(root, "sub"), "add", "next.txt");
    await git_(path.join(root, "sub"), "commit", "--quiet", "-m", "move the pointer");
    const after = (await git.head(path.join(root, "sub")))!;
    await git_(root, "add", "sub");

    const diff = await git.fileDiff(root, "sub");
    expect(diff.before).toBe(`submodule sub at ${before}\n`);
    expect(diff.after).toBe(`submodule sub at ${after}\n`);
  });
});

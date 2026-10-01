/**
 * P7's half of `src/main/projects/git.ts` against real repositories: removing
 * worktrees and the keep-limit sweep.
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
import { execFile } from "node:child_process";
import { chmod, mkdir, readdir, readFile, rm, utimes, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

import { afterAll, afterEach, describe, expect, it } from "vitest";

import * as git from "@main/projects/git";

import { cleanGitTemplates, gitIn as git_, repositoryWithWorktrees, scratchDir } from "./git-fixtures";

const run = promisify(execFile);

const temporary: string[] = [];

afterEach(async () => {
  for (const directory of temporary.splice(0)) {
    await rm(directory, { recursive: true, force: true });
  }
});
afterAll(cleanGitTemplates);

describe("removeWorktree", () => {
  it("removes a clean worktree and leaves its branch behind", async () => {
    const { root, worktrees } = await repositoryWithWorktrees(temporary);
    const created = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "gone" });

    await git.removeWorktree(created.path);

    expect(await git.listWorktrees(root)).toHaveLength(1);
    // The checkout is recreatable; the commits on the branch are not, so the
    // branch stays.
    const branches = await git_(root, "branch", "--list", created.branch);
    expect(branches.stdout).toContain(created.branch);
  });

  it("refuses a dirty worktree unless it is forced", async () => {
    const { root, worktrees } = await repositoryWithWorktrees(temporary);
    const created = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "busy" });
    await writeFile(path.join(created.path, "README.md"), "edited\n");

    await expect(git.removeWorktree(created.path)).rejects.toThrow("uncommitted changes");
    expect(await git.listWorktrees(root)).toHaveLength(2);

    await git.removeWorktree(created.path, { force: true });
    expect(await git.listWorktrees(root)).toHaveLength(1);
  });

  it("refuses ignored files it would delete unless forced, but not disposable caches", async () => {
    const { root, worktrees } = await repositoryWithWorktrees(temporary);
    await writeFile(path.join(root, ".gitignore"), ".env\n*.step\nnode_modules/\n__pycache__/\n");
    await git_(root, "add", "-A");
    await git_(root, "commit", "--quiet", "-m", "ignore");

    const caches = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "caches" });
    await mkdir(path.join(caches.path, "node_modules", "left-pad"), { recursive: true });
    await writeFile(path.join(caches.path, "node_modules", "left-pad", "index.js"), "x\n");
    await mkdir(path.join(caches.path, "__pycache__"));
    await writeFile(path.join(caches.path, "__pycache__", "a.pyc"), "x");
    await git.removeWorktree(caches.path);

    const work = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "work" });
    await writeFile(path.join(work.path, ".env"), "TOKEN=1\n");
    await writeFile(path.join(work.path, "arm.step"), "ISO-10303-21;\n");
    expect(await git.isDirty(work.path)).toBe(false);
    expect(await git.hasUnsavedWork(work.path)).toBe(true);
    await expect(git.removeWorktree(work.path)).rejects.toThrow(/ignored files.*\.env/);
    expect(await readdir(work.path)).toContain(".env");

    await git.removeWorktree(work.path, { force: true });
    expect(await git.listWorktrees(root)).toHaveLength(1);
  });

  it("removes the registration of a folder deleted by hand, and the sweep does too", async () => {
    const { root, worktrees } = await repositoryWithWorktrees(temporary);
    const gone = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "gone by hand" });
    const swept = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "swept" });
    await rm(gone.path, { recursive: true, force: true });
    await rm(swept.path, { recursive: true, force: true });

    await git.removeWorktree(gone.path, { repoPath: root });
    expect((await git.pruneWorktrees({ repoPath: root, parentDir: worktrees, keep: 0 })).removed).toEqual([swept.path]);
    expect((await git.listWorktrees(root)).filter((worktree) => !worktree.primary)).toEqual([]);
    // The branches stay, as for any removal.
    expect((await git_(root, "branch", "--list", gone.branch, swept.branch)).stdout).toContain(gone.branch);
  });

  // Root reads through a 000 directory, so the folder would not be unreadable.
  it.skipIf(process.platform === "win32" || process.getuid?.() === 0)(
    "keeps a worktree whose folder cannot be read, rather than taking it for one deleted by hand",
    async () => {
      const { root, worktrees } = await repositoryWithWorktrees(temporary);
      const locked = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "unmounted" });
      // A parent the app cannot search: `stat` fails with EACCES, the way an
      // unmounted volume or a revoked permission fails it. git calls this
      // `prunable` too — it cannot see the folder either.
      await chmod(worktrees, 0o000);
      try {
        await expect(git.removeWorktree(locked.path, { repoPath: root })).rejects.toThrow(/could not read/);
        expect((await git.pruneWorktrees({ repoPath: root, parentDir: worktrees, keep: 0 })).removed).toEqual([]);
      } finally {
        await chmod(worktrees, 0o755);
      }
      expect((await git.listWorktrees(root)).map((worktree) => worktree.path)).toContain(locked.path);
      expect(await readdir(locked.path)).toContain("README.md");
    },
  );

  it("refuses the repository's own working tree", async () => {
    const { root } = await repositoryWithWorktrees(temporary);
    await expect(git.removeWorktree(root)).rejects.toThrow("the repository itself");
  });
});

describe("pruneWorktrees", () => {
  it("keeps the newest, and never touches what it did not create", async () => {
    const { root, worktrees } = await repositoryWithWorktrees(temporary);
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

  it("orders by the newest file written, not the folder's own mtime", async () => {
    const { root, worktrees } = await repositoryWithWorktrees(temporary);
    await mkdir(path.join(root, "src"));
    await writeFile(path.join(root, "src", "part.py"), "x = 1\n");
    await git_(root, "add", "-A");
    await git_(root, "commit", "--quiet", "-m", "src");
    const idle = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "idle" });
    const busy = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "busy" });
    const hourAgo = Date.now() - 3_600_000;
    for (const worktree of [idle, busy]) {
      await utimes(path.join(worktree.path, "src"), new Date(hourAgo), new Date(hourAgo));
      await utimes(path.join(worktree.path, "src", "part.py"), new Date(hourAgo), new Date(hourAgo));
      await touch(worktree.path, hourAgo);
    }
    // A scratch file made and removed at the idle one's top level: its
    // folder's mtime moved, nothing in it did.
    await utimes(idle.path, new Date(), new Date());
    // The busy one is being edited, deep down: its folder's mtime never moves.
    await writeFile(path.join(busy.path, "src", "part.py"), "x = 2\n");
    await git_(busy.path, "commit", "--quiet", "-am", "the edit");
    await utimes(busy.path, new Date(hourAgo - 60_000), new Date(hourAgo - 60_000));

    const { removed } = await git.pruneWorktrees({ repoPath: root, parentDir: worktrees, keep: 1 });
    expect(removed).toEqual([idle.path]);
  });

  it("dates nothing when the worktrees are within the limit", async () => {
    const { root, worktrees } = await repositoryWithWorktrees(temporary);
    for (const name of ["one", "two"]) {
      await git.createWorktree({ repoPath: root, parentDir: worktrees, name });
    }
    // A `git` first on PATH that writes down every argv it is given.
    const real = (await run("sh", ["-c", "command -v git"])).stdout.trim();
    const bin = await scratchDir("text-to-cad-git-log-", temporary);
    const log = path.join(bin, "calls");
    await writeFile(path.join(bin, "git"), `#!/bin/sh\necho "$*" >> "${log}"\nexec "${real}" "$@"\n`, { mode: 0o755 });
    const previous = process.env.PATH;
    process.env.PATH = `${bin}${path.delimiter}${previous ?? ""}`;
    try {
      expect((await git.pruneWorktrees({ repoPath: root, parentDir: worktrees, keep: 2 })).removed).toEqual([]);
    } finally {
      process.env.PATH = previous;
    }
    const calls = (await readFile(log, "utf8")).split("\n").filter(Boolean);
    expect(calls.some((call) => call.startsWith("worktree list"))).toBe(true);
    // Two worktrees and a limit of two: which is older does not matter.
    expect(calls.filter((call) => /ls-files|%ct|^status/.test(call))).toEqual([]);
  });

  it("never removes one with an open session or uncommitted work", async () => {
    const { root, worktrees } = await repositoryWithWorktrees(temporary);
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

  it("never sweeps a worktree whose ignored files it would delete", async () => {
    const { root, worktrees } = await repositoryWithWorktrees(temporary);
    await writeFile(path.join(root, ".gitignore"), ".env\n");
    await git_(root, "add", "-A");
    await git_(root, "commit", "--quiet", "-m", "ignore");
    const secrets = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "secrets" });
    await writeFile(path.join(secrets.path, ".env"), "TOKEN=1\n");

    const { removed } = await git.pruneWorktrees({ repoPath: root, parentDir: worktrees, keep: 0 });
    expect(removed).toEqual([]);
    expect(await readdir(secrets.path)).toContain(".env");
  });
});

describe("a check git could not answer", () => {
  /**
   * A `git` first on PATH that fails the ignored-files read the way a lock or
   * a timeout would, and passes everything else to the real one.
   */
  async function failingIgnoredCheck(): Promise<() => void> {
    const real = (await run("sh", ["-c", "command -v git"])).stdout.trim();
    const bin = await scratchDir("text-to-cad-git-wrapper-", temporary);
    await writeFile(
      path.join(bin, "git"),
      `#!/bin/sh\nfor arg in "$@"; do [ "$arg" = "--ignored=matching" ] && { echo "fatal: unable to read index" >&2; exit 128; }; done\nexec "${real}" "$@"\n`,
      { mode: 0o755 },
    );
    const previous = process.env.PATH;
    process.env.PATH = `${bin}${path.delimiter}${previous ?? ""}`;
    return () => {
      process.env.PATH = previous;
    };
  }

  it("is unknown, not clean, and nothing is removed on it", async () => {
    const { root, worktrees } = await repositoryWithWorktrees(temporary);
    await writeFile(path.join(root, ".gitignore"), ".env\n");
    await git_(root, "add", "-A");
    await git_(root, "commit", "--quiet", "-m", "ignore");
    const secrets = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "secrets" });
    await writeFile(path.join(secrets.path, ".env"), "TOKEN=1\n");

    const restore = await failingIgnoredCheck();
    try {
      const { removed } = await git.pruneWorktrees({ repoPath: root, parentDir: worktrees, keep: 0 });
      expect(removed).toEqual([]);
      await expect(git.removeWorktree(secrets.path)).rejects.toThrow(/could not check that worktree/);
      // What Settings is told: not clean, not dirty — unknown.
      expect(await git.hasUnsavedWork(secrets.path)).toBeNull();
    } finally {
      restore();
    }
    expect(await readdir(secrets.path)).toContain(".env");
  });
});

/** Set a worktree's mtimes — the folder and its one file — so the sweep's ordering is deterministic. */
async function touch(directory: string, at: number): Promise<void> {
  const { utimes } = await import("node:fs/promises");
  await utimes(path.join(directory, "README.md"), new Date(at), new Date(at));
  await utimes(directory, new Date(at), new Date(at));
}

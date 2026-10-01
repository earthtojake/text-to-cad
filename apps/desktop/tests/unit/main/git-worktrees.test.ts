/**
 * P7's half of `src/main/projects/git.ts` against real repositories: slugs,
 * parsers, repository detection and creating worktrees. Removing them and the
 * sweep are `git-worktree-sweep.test.ts`; review scopes and pull requests are
 * `git-review.test.ts`.
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
import { readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";

import { afterAll, afterEach, describe, expect, it } from "vitest";

import * as git from "@main/projects/git";

import { cleanGitTemplates, gitIn as git_, pushedRepository, repositoryWithWorktrees, scratchDir } from "./git-fixtures";

const temporary: string[] = [];

afterEach(async () => {
  for (const directory of temporary.splice(0)) {
    await rm(directory, { recursive: true, force: true });
  }
});
afterAll(cleanGitTemplates);

/**
 * {@link repositoryWithWorktrees}, with a bare `origin` beside it that `main` is pushed to;
 * `ahead`, someone else has since pushed `theirs.txt` (see `pushedRepository`).
 */
async function pushed(options: { ahead?: boolean } = {}) {
  const base = await scratchDir("text-to-cad-git-", temporary);
  const root = path.join(base, "project");
  const worktrees = path.join(base, "worktrees");
  const { serverTip } = await pushedRepository(root, path.join(base, "remote.git"), { readme: "one\ntwo\n", ...options });
  return { root, worktrees, serverTip: serverTip! };
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
      "branch refs/heads/text-to-cad/feature",
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
      branch: "text-to-cad/feature",
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
    expect(git.isUnder("/a/b", "/a/b/..keep")).toBe(true);
    expect(git.isUnder("/a/b", "/a/b/../escape")).toBe(false);
    expect(git.samePath("/a/b/", "/a/b")).toBe(true);
    expect(git.samePath("/a/b", "/a/c")).toBe(false);
  });
});

/* -------------------------------------------------------------------------- */
/* Repository detection                                                        */
/* -------------------------------------------------------------------------- */

describe("repoInfo", () => {
  it("answers empty for a directory that is not a repository", async () => {
    const plain = await scratchDir("text-to-cad-plain-", temporary);
    expect(await git.repoInfo(plain)).toEqual(git.emptyRepoInfo());
  });

  it("reports the branch, cleanliness and the absence of a remote", async () => {
    const { root } = await repositoryWithWorktrees(temporary);
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
    const base = await scratchDir("text-to-cad-unborn-", temporary);
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
    const { root, worktrees } = await repositoryWithWorktrees(temporary);

    const created = await git.createWorktree({
      repoPath: root,
      parentDir: worktrees,
      name: "Model the wrist",
      branchPrefix: "text-to-cad/",
    });

    expect(created.path).toBe(path.join(worktrees, "model-the-wrist"));
    expect(created.branch).toBe("text-to-cad/model-the-wrist");
    expect(created.base).toBe(await git.head(root));
    // It is a real checkout of the repository, not an empty folder.
    expect(await readdir(created.path)).toContain("README.md");

    const listed = await git.listWorktrees(root);
    expect(listed).toHaveLength(2);
    expect(listed[0]?.primary).toBe(true);
    expect(listed[1]).toMatchObject({
      path: created.path,
      branch: "text-to-cad/model-the-wrist",
      primary: false,
    });
  });

  it("generates a name when there is nothing to slugify", async () => {
    const { root, worktrees } = await repositoryWithWorktrees(temporary);
    const created = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "…" });
    expect(path.basename(created.path)).toMatch(/^session-[0-9a-f]{1,4}$/);
    expect(created.branch).toBe(`text-to-cad/${path.basename(created.path)}`);
  });

  it("suffixes a name whose directory or branch is taken", async () => {
    const { root, worktrees } = await repositoryWithWorktrees(temporary);
    const first = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "wrist" });
    const second = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "wrist" });
    expect(path.basename(first.path)).toBe("wrist");
    expect(path.basename(second.path)).toBe("wrist-2");
    expect(second.branch).toBe("text-to-cad/wrist-2");

    // A branch that exists without a worktree also has to be stepped over:
    // `git worktree add -b` would fail on it.
    await git_(root, "branch", "text-to-cad/wrist-3");
    const third = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "wrist" });
    expect(third.branch).toBe("text-to-cad/wrist-4");
  });

  it("refuses a prefix a branch is in the way of, naming it, and steps over a branch under a name", async () => {
    const { root, worktrees } = await repositoryWithWorktrees(temporary);
    await git_(root, "branch", "amy");
    await expect(
      git.createWorktree({ repoPath: root, parentDir: worktrees, name: "wrist", branchPrefix: "amy/" }),
    ).rejects.toThrow('already has a branch called "amy"');

    // `amy-wrist/old` existing makes `amy-wrist` impossible, but `amy-wrist-2` is fine.
    await git_(root, "branch", "amy-wrist/old");
    const created = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "wrist", branchPrefix: "amy-" });
    expect(created.branch).toBe("amy-wrist-2");
  });

  it("steps over a branch name someone else already has on the remote", async () => {
    const { root, worktrees } = await pushed();
    // Another machine pushed `text-to-cad/wrist`; only the fetch tells this checkout.
    await git_(root, "push", "--quiet", "origin", "main:refs/heads/text-to-cad/wrist");
    await git_(root, "update-ref", "-d", "refs/remotes/origin/text-to-cad/wrist");

    const fetched = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "wrist", fetch: true });
    expect(fetched.branch).toBe("text-to-cad/wrist-2");
    // Without a fetch, what the checkout already knows of the remote still counts.
    const known = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "wrist" });
    expect(known.branch).toBe("text-to-cad/wrist-3");
  });

  it("with fetch, starts from the fetched upstream rather than local HEAD, and tracks nothing", async () => {
    // Someone else has pushed a commit the checkout has not seen.
    const { root, worktrees, serverTip } = await pushed({ ahead: true });

    const created = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "fresh", fetch: true });
    expect(created.base).toBe(serverTip);
    expect(await readdir(created.path)).toContain("theirs.txt");
    // Local HEAD is untouched, and the new branch does not track main.
    expect(await git.head(root)).not.toBe(serverTip);
    await expect(git_(created.path, "rev-parse", "--abbrev-ref", "@{upstream}")).rejects.toThrow();

    // Without fetch it is still local HEAD.
    const local = await git.createWorktree({ repoPath: root, parentDir: worktrees, name: "local" });
    expect(local.base).toBe(await git.head(root));
  });

  it("refuses a directory that is not a repository, in words a person can act on", async () => {
    const plain = await scratchDir("text-to-cad-plain-", temporary);
    await expect(
      git.createWorktree({ repoPath: plain, parentDir: path.join(plain, "wt") }),
    ).rejects.toThrow("Project is not a git repository, worktree mode unavailable");
  });

  it("refuses a repository with nothing to branch from", async () => {
    const base = await scratchDir("text-to-cad-unborn-", temporary);
    await git_(base, "init", "--quiet", "--initial-branch=main");
    await expect(
      git.createWorktree({ repoPath: base, parentDir: path.join(base, "wt") }),
    ).rejects.toThrow(/no commits yet/i);
  });
});


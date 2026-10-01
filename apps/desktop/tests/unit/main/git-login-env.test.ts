/**
 * git's children run under the login shell's environment once `loginEnv` has
 * captured it (README, "Git modes and worktrees"): a Dock launch's PATH has no
 * Homebrew, and a hook that calls node or git-lfs fails under it.
 *
 * Real git and a real hook: the fact under test is what a hook sees.
 */
import { chmod, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterAll, afterEach, describe, expect, it } from "vitest";

import * as git from "@main/projects/git";

import { cleanGitTemplates, committedRepository } from "./git-fixtures";

const temporary: string[] = [];
afterEach(async () => {
  git.setLoginEnvForGit(null);
  for (const directory of temporary.splice(0)) await rm(directory, { recursive: true, force: true });
});
afterAll(cleanGitTemplates);

describe("the environment git runs under", () => {
  it("is the login shell's once it has been captured, and the process's until then", async () => {
    const base = await realpath(await mkdtemp(path.join(os.tmpdir(), "text-to-cad-login-env-")));
    temporary.push(base);
    const root = path.join(base, "project");
    await committedRepository(root, "one\n");
    const seen = path.join(base, "hook-path.txt");
    const hook = path.join(root, ".git", "hooks", "post-checkout");
    await writeFile(hook, `#!/bin/sh\nprintf '%s' "$PATH" > '${seen}'\n`);
    await chmod(hook, 0o755);

    // Before the capture lands: the process environment, and no waiting.
    await git.createWorktree({ repoPath: root, parentDir: path.join(base, "wt"), name: "before" });
    expect(await readFile(seen, "utf8")).not.toContain("login-shell-marker");

    git.setLoginEnvForGit({ ...(process.env as Record<string, string>), PATH: `/login-shell-marker/bin:${process.env.PATH}` });
    await git.createWorktree({ repoPath: root, parentDir: path.join(base, "wt"), name: "after" });
    expect(await readFile(seen, "utf8")).toContain("/login-shell-marker/bin");
  });

  it("drops the repository-location variables a login shell exports, so every call still finds the repository it was asked about", async () => {
    const base = await realpath(await mkdtemp(path.join(os.tmpdir(), "text-to-cad-login-env-")));
    temporary.push(base);
    const root = path.join(base, "project");
    await committedRepository(root, "one\n");
    git.setLoginEnvForGit({
      ...(process.env as Record<string, string>),
      GIT_DIR: "/nowhere",
      GIT_WORK_TREE: "/nowhere",
      GIT_INDEX_FILE: "/nowhere/index",
      GIT_NAMESPACE: "other",
      GIT_CEILING_DIRECTORIES: base,
    });
    expect(await git.repositoryRoot(root)).toBe(root);
  });

  it("pins the language git speaks (LC_ALL and LANG are C), whatever the login shell says", async () => {
    const base = await realpath(await mkdtemp(path.join(os.tmpdir(), "text-to-cad-login-env-")));
    temporary.push(base);
    const root = path.join(base, "project");
    await committedRepository(root, "one\n");
    const seen = path.join(base, "hook-locale.txt");
    const hook = path.join(root, ".git", "hooks", "post-checkout");
    await writeFile(hook, `#!/bin/sh\nprintf '%s|%s' "$LC_ALL" "$LANG" > '${seen}'\n`);
    await chmod(hook, 0o755);
    git.setLoginEnvForGit({ ...(process.env as Record<string, string>), LC_ALL: "de_DE.UTF-8", LANG: "de_DE.UTF-8" });
    await git.createWorktree({ repoPath: root, parentDir: path.join(base, "wt"), name: "locale" });
    expect(await readFile(seen, "utf8")).toBe("C|C");
  });
});

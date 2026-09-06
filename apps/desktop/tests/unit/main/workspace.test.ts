/**
 * Where a session runs, per git mode (plan §9), and what it takes with it when
 * it goes.
 *
 * Real repositories again: the question is what `resolveWorkspace` does with a
 * folder that is not a repository, a repository with no commits, and one that
 * is fine — and only git can answer the first two.
 */
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, realpath, rm, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import { afterEach, describe, expect, it } from "vitest";

import {
  projectWorktreeDir,
  releaseWorkspace,
  resolveWorkspace,
  worktreeRoot,
} from "@main/projects/workspace";
import { defaultSettings, type Project, type Settings } from "@shared/types";

const run = promisify(execFile);

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

/** A project directory, a worktree root beside it, and the settings pointing at both. */
async function fixture(options: { repository?: boolean; commit?: boolean } = {}) {
  const base = await realpath(await mkdtemp(path.join(os.tmpdir(), "hardcore-ws-")));
  temporary.push(base);
  const root = path.join(base, "text-to-cad");
  await mkdir(root, { recursive: true });

  if (options.repository !== false) {
    await run("git", ["init", "--quiet", "--initial-branch=main"], { cwd: root, env: GIT_ENV });
    if (options.commit !== false) {
      await writeFile(path.join(root, "README.md"), "one\n");
      await run("git", ["add", "-A"], { cwd: root, env: GIT_ENV });
      await run("git", ["commit", "--quiet", "-m", "first"], { cwd: root, env: GIT_ENV });
    }
  }

  const project: Project = {
    id: "project-1",
    name: "text-to-cad",
    path: root,
    createdAt: Date.now(),
  };
  const settings: Settings = {
    ...defaultSettings(),
    worktreeRoot: path.join(base, "worktrees"),
  };
  return { base, project, settings };
}

describe("worktreeRoot", () => {
  it("expands the stored null to ~/.hardcore/worktrees", () => {
    expect(worktreeRoot({ worktreeRoot: null })).toBe(
      path.join(os.homedir(), ".hardcore", "worktrees"),
    );
    expect(worktreeRoot({ worktreeRoot: "/tmp/wt" })).toBe("/tmp/wt");
  });

  it("names the per-project folder by a slug, so a rename cannot move it far", () => {
    const settings = { worktreeRoot: "/wt" };
    expect(
      projectWorktreeDir(settings, { name: "Robot arm (v2)", path: "/src/robot-arm" }),
    ).toBe(path.join("/wt", "robot-arm-v2"));
    // A name with nothing usable in it falls back to the directory's basename.
    expect(projectWorktreeDir(settings, { name: "…", path: "/src/robot-arm" })).toBe(
      path.join("/wt", "robot-arm"),
    );
  });
});

describe("resolveWorkspace", () => {
  it("`none` is the project directory, and never asks git anything", async () => {
    const { project, settings } = await fixture({ repository: false });
    expect(await resolveWorkspace({ project, settings, gitMode: "none" })).toEqual({
      cwd: project.path,
    });
  });

  it("`checkout` is the project directory, with the branch it is on", async () => {
    const { project, settings } = await fixture();
    expect(await resolveWorkspace({ project, settings, gitMode: "checkout" })).toEqual({
      cwd: project.path,
      branch: "main",
    });
  });

  it("`checkout` still runs in a folder that is not a repository", async () => {
    const { project, settings } = await fixture({ repository: false });
    expect(await resolveWorkspace({ project, settings, gitMode: "checkout" })).toEqual({
      cwd: project.path,
    });
  });

  it("`worktree` makes one under the root, named from the first prompt", async () => {
    const { project, settings } = await fixture();
    const workspace = await resolveWorkspace({
      project,
      settings,
      gitMode: "worktree",
      name: "Model the wrist path",
    });

    const expected = path.join(
      settings.worktreeRoot!,
      "text-to-cad",
      "model-the-wrist-path",
    );
    expect(workspace).toEqual({
      cwd: expected,
      branch: "hardcore/model-the-wrist-path",
      worktreePath: expected,
    });
    expect((await stat(expected)).isDirectory()).toBe(true);
  });

  it("`worktree` honours the branch prefix setting", async () => {
    const { project, settings } = await fixture();
    const workspace = await resolveWorkspace({
      project,
      settings: { ...settings, branchPrefix: "agents/" },
      gitMode: "worktree",
      name: "wrist",
    });
    expect(workspace.branch).toBe("agents/wrist");
  });

  it("`worktree` says what is wrong rather than throwing git's words", async () => {
    const plain = await fixture({ repository: false });
    await expect(
      resolveWorkspace({ project: plain.project, settings: plain.settings, gitMode: "worktree" }),
    ).rejects.toThrow("Project is not a git repository, worktree mode unavailable");

    const unborn = await fixture({ commit: false });
    await expect(
      resolveWorkspace({ project: unborn.project, settings: unborn.settings, gitMode: "worktree" }),
    ).rejects.toThrow(/no commits yet/i);
  });

  it("an explicit directory has to be the project or one of its worktrees", async () => {
    const { base, project, settings } = await fixture();
    const made = await resolveWorkspace({
      project,
      settings,
      gitMode: "worktree",
      name: "reuse",
    });

    // Settings' `New chat in this worktree`.
    expect(
      await resolveWorkspace({ project, settings, gitMode: "worktree", cwd: made.cwd }),
    ).toEqual({ cwd: made.cwd, branch: "hardcore/reuse", worktreePath: made.cwd });

    // The project itself is allowed, and is not a worktree.
    expect(
      await resolveWorkspace({ project, settings, gitMode: "checkout", cwd: project.path }),
    ).toEqual({ cwd: project.path, branch: "main" });

    // Anywhere else is a renderer asking main to run an agent somewhere it was
    // never shown.
    await expect(
      resolveWorkspace({ project, settings, gitMode: "checkout", cwd: base }),
    ).rejects.toThrow("does not belong to this project");
  });
});

describe("releaseWorkspace", () => {
  it("does nothing without the setting, and nothing for a session with no worktree", async () => {
    const { project, settings } = await fixture();
    const made = await resolveWorkspace({ project, settings, gitMode: "worktree", name: "keep" });

    expect(await releaseWorkspace({ worktreePath: undefined }, { autoDeleteWorktrees: true }))
      .toEqual({ removed: false });
    expect(
      await releaseWorkspace({ worktreePath: made.cwd }, { autoDeleteWorktrees: false }),
    ).toMatchObject({ removed: false });
    expect((await stat(made.cwd)).isDirectory()).toBe(true);
  });

  it("removes a clean worktree, and reports why it did not remove a dirty one", async () => {
    const { project, settings } = await fixture();
    const clean = await resolveWorkspace({ project, settings, gitMode: "worktree", name: "clean" });
    const dirty = await resolveWorkspace({ project, settings, gitMode: "worktree", name: "dirty" });
    await writeFile(path.join(dirty.cwd, "wip.txt"), "not committed\n");

    expect(
      await releaseWorkspace({ worktreePath: clean.cwd }, { autoDeleteWorktrees: true }),
    ).toEqual({ removed: true });
    await expect(stat(clean.cwd)).rejects.toThrow();

    const refused = await releaseWorkspace(
      { worktreePath: dirty.cwd },
      { autoDeleteWorktrees: true },
    );
    expect(refused.removed).toBe(false);
    expect(refused.reason).toMatch(/uncommitted/);
    expect((await stat(dirty.cwd)).isDirectory()).toBe(true);
  });
});

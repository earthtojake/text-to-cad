/**
 * Where a session runs, per git mode (plan §9), and what it takes with it when
 * it goes.
 *
 * Real repositories again: the question is what `resolveWorkspace` does with a
 * folder that is not a repository, a repository with no commits, and one that
 * is fine — and only git can answer the first two. The committed ones are
 * copies of a template this file builds once (`./git-fixtures`).
 */
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, realpath, rm, stat, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import { afterAll, afterEach, describe, expect, it } from "vitest";

import {
  legacyProjectWorktreeDir,
  projectWorktreeDir,
  releaseWorkspace,
  resolveProjectRoot,
  resolveWorkspace,
  rootBelongsToProject,
  worktreeRoot,
} from "@main/projects/workspace";
import { defaultSettings, type Project, type Settings } from "@shared/types";

import { cleanGitTemplates, committedRepository, GIT_ENV, pushedRepository } from "./git-fixtures";

const run = promisify(execFile);

const temporary: string[] = [];

afterEach(async () => {
  for (const directory of temporary.splice(0)) {
    await rm(directory, { recursive: true, force: true });
  }
});
afterAll(cleanGitTemplates);

/**
 * A project directory, a worktree root beside it, and the settings pointing at
 * both. `remote`: the project has a bare `origin` at `<base>/remote.git` that
 * is one commit ahead of it (see `pushedRepository`).
 */
async function fixture(options: { repository?: boolean; commit?: boolean; remote?: boolean } = {}) {
  const base = await realpath(await mkdtemp(path.join(os.tmpdir(), "text-to-cad-ws-")));
  temporary.push(base);
  const root = path.join(base, "text-to-cad");

  if (options.remote) {
    await pushedRepository(root, path.join(base, "remote.git"), { ahead: true });
  } else if (options.repository !== false && options.commit !== false) {
    await committedRepository(root);
  } else {
    await mkdir(root, { recursive: true });
    if (options.repository !== false) {
      await run("git", ["init", "--quiet", "--initial-branch=main"], { cwd: root, env: GIT_ENV });
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
  it("expands the stored null to ~/.text-to-cad/worktrees", () => {
    expect(worktreeRoot({ worktreeRoot: null })).toBe(
      path.join(os.homedir(), ".text-to-cad", "worktrees"),
    );
    expect(worktreeRoot({ worktreeRoot: "/tmp/wt" })).toBe("/tmp/wt");
  });

  it("names the per-project folder by a slug and a hash of the path", () => {
    const settings = { worktreeRoot: "/wt" };
    expect(
      projectWorktreeDir(settings, { name: "Robot arm (v2)", path: "/src/robot-arm" }),
    ).toMatch(new RegExp(`^${path.join("/wt", "robot-arm-v2")}-[0-9a-f]{8}$`));
    // A name with nothing usable in it falls back to the directory's basename.
    expect(projectWorktreeDir(settings, { name: "…", path: "/src/robot-arm" })).toMatch(
      new RegExp(`^${path.join("/wt", "robot-arm")}-[0-9a-f]{8}$`),
    );
    expect(legacyProjectWorktreeDir(settings, { name: "…", path: "/src/robot-arm" })).toBe(path.join("/wt", "robot-arm"));
  });

  it("gives two projects with the same name two folders", () => {
    const settings = { worktreeRoot: "/wt" };
    const work = projectWorktreeDir(settings, { name: "robot-arm", path: "/work/robot-arm" });
    const forks = projectWorktreeDir(settings, { name: "robot-arm", path: "/forks/robot-arm" });
    expect(work).not.toBe(forks);
    expect(rootBelongsToProject(settings, { name: "robot-arm", path: "/forks/robot-arm" }, path.join(work, "slug"))).toBe(false);
  });

  it("accepts a pre-hash folder's worktree only for the repository it belongs to", async () => {
    const base = await realpath(await mkdtemp(path.join(os.tmpdir(), "text-to-cad-legacy-")));
    temporary.push(base);
    const settings = { worktreeRoot: path.join(base, "worktrees") };
    const projects = [path.join(base, "work", "robot-arm"), path.join(base, "forks", "robot-arm")].map((root) => ({
      name: "robot-arm",
      path: root,
    }));
    for (const project of projects) {
      await committedRepository(project.path);
    }
    const [mine, theirs] = projects as [(typeof projects)[0], (typeof projects)[0]];
    const legacy = path.join(legacyProjectWorktreeDir(settings, mine), "wrist");
    await run("git", ["worktree", "add", "--quiet", "-b", "text-to-cad/wrist", legacy], { cwd: mine.path, env: GIT_ENV });

    expect(rootBelongsToProject(settings, mine, legacy)).toBe(true);
    expect(rootBelongsToProject(settings, mine, path.join(legacy, "sub"))).toBe(true);
    expect(rootBelongsToProject(settings, theirs, legacy)).toBe(false);
    expect(() => resolveProjectRoot(settings, theirs, legacy)).toThrow("does not belong to this project");
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

    // New worktrees go in the hashed folder, never the shared pre-hash one.
    const expected = path.join(projectWorktreeDir(settings, project), "model-the-wrist-path");
    expect(path.basename(path.dirname(expected))).toMatch(/^text-to-cad-[0-9a-f]{8}$/);
    expect(workspace).toEqual({
      cwd: expected,
      branch: "text-to-cad/model-the-wrist-path",
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

    // Settings' `New session in this worktree`.
    expect(
      await resolveWorkspace({ project, settings, gitMode: "worktree", cwd: made.cwd }),
    ).toEqual({ cwd: made.cwd, branch: "text-to-cad/reuse", worktreePath: made.cwd });

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

  it("an explicit directory spelled through a symlink is the one the project list stores", async () => {
    // `projects.add` stores real paths, so a project made from macOS's `/var/...` or `/tmp/...`
    // is recorded at `/private/...`, while the renderer may still name it the way it was chosen.
    const { base, project, settings } = await fixture();
    const made = await resolveWorkspace({ project, settings, gitMode: "worktree", name: "linked" });
    const link = `${base}-link`;
    temporary.push(link);
    await symlink(base, link, process.platform === "win32" ? "junction" : "dir");
    const spelled = (directory: string) => path.join(link, path.relative(base, directory));

    expect(
      await resolveWorkspace({ project, settings, gitMode: "none", cwd: spelled(project.path) }),
    ).toEqual({ cwd: project.path, branch: "main" });
    expect(rootBelongsToProject(settings, project, spelled(made.cwd))).toBe(true);
    expect(resolveProjectRoot(settings, project, spelled(project.path))).toBe(project.path);
    // The link to somewhere else is still somewhere else.
    await expect(
      resolveWorkspace({ project, settings, gitMode: "none", cwd: link }),
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

describe("releaseWorkspace for an abandoned create", () => {
  it("removes the worktree and its unmoved branch even with auto-delete off", async () => {
    const { project, settings } = await fixture();
    const made = await resolveWorkspace({ project, settings, gitMode: "worktree", name: "never opened" });

    expect(
      await releaseWorkspace({ worktreePath: made.cwd, branch: made.branch }, { autoDeleteWorktrees: false }, { abandoned: true }),
    ).toEqual({ removed: true });
    await expect(stat(made.cwd)).rejects.toThrow();
    const branches = await run("git", ["branch", "--list", made.branch!], { cwd: project.path, env: GIT_ENV });
    expect(branches.stdout.trim()).toBe("");
  });
});

describe("releaseWorkspace for an abandoned create cut from a fetched tip", () => {
  it("deletes the branch this create made while it is still at its base, even when local HEAD is behind it", async () => {
    // A remote one commit ahead of the checkout: the fetch before creating
    // cuts the branch from there, and `git branch -d` measures against the
    // checkout's HEAD, which does not contain it.
    const { project, settings } = await fixture({ remote: true });
    const git = (cwd: string, ...args: string[]) => run("git", args, { cwd, env: GIT_ENV });

    const fetching = { ...settings, fetchBeforeCreate: true };
    const made = await resolveWorkspace({ project, settings: fetching, gitMode: "worktree", name: "never opened" });
    const sessionHead = (await git(made.cwd, "rev-parse", "HEAD")).stdout.trim();
    expect(sessionHead).toBe((await git(project.path, "rev-parse", "origin/main")).stdout.trim());

    expect(
      await releaseWorkspace({ worktreePath: made.cwd, branch: made.branch, sessionHead }, { autoDeleteWorktrees: false }, { abandoned: true }),
    ).toEqual({ removed: true });
    expect((await git(project.path, "branch", "--list", made.branch!)).stdout.trim()).toBe("");

    // A branch with a commit beyond where it was cut holds work: it stays.
    const worked = await resolveWorkspace({ project, settings: fetching, gitMode: "worktree", name: "worked" });
    const cut = (await git(worked.cwd, "rev-parse", "HEAD")).stdout.trim();
    await writeFile(path.join(worked.cwd, "part.py"), "x = 1\n");
    await git(worked.cwd, "add", "-A");
    await git(worked.cwd, "commit", "--quiet", "-m", "work");
    expect(
      await releaseWorkspace({ worktreePath: worked.cwd, branch: worked.branch, sessionHead: cut }, { autoDeleteWorktrees: false }, { abandoned: true }),
    ).toEqual({ removed: true });
    expect((await git(project.path, "branch", "--list", worked.branch!)).stdout).toContain(worked.branch);
  });
});

/**
 * The explorer's root check (plan §9): a tab, a terminal or an agent may
 * name the project directory or one of its worktrees, and nothing else on
 * the machine. Pure path arithmetic — no repository is needed to say where a
 * worktree would be allowed to live.
 */
describe("resolveProjectRoot", () => {
  const settings: Pick<Settings, "worktreeRoot"> = { worktreeRoot: "/tmp/text-to-cad-worktrees" };
  const project: Pick<Project, "name" | "path"> = { name: "text-to-cad", path: "/Users/me/text-to-cad" };

  it("answers the project directory for no root, and for the project itself", () => {
    expect(resolveProjectRoot(settings, project, null)).toBe(project.path);
    expect(resolveProjectRoot(settings, project, undefined)).toBe(project.path);
    expect(resolveProjectRoot(settings, project, project.path)).toBe(project.path);
    expect(resolveProjectRoot(settings, project, "/Users/me/text-to-cad/")).toBe(project.path);
  });

  it("admits a directory under the project's worktree folder, resolved", () => {
    const worktree = path.join(projectWorktreeDir(settings, project), "model-the-wrist");
    expect(rootBelongsToProject(settings, project, worktree)).toBe(true);
    expect(resolveProjectRoot(settings, project, worktree)).toBe(worktree);
    expect(resolveProjectRoot(settings, project, `${worktree}/../model-the-wrist`)).toBe(worktree);
  });

  it("refuses everything else with a sentence", () => {
    expect(rootBelongsToProject(settings, project, "/etc")).toBe(false);
    expect(rootBelongsToProject(settings, project, "/Users/me/text-to-cad-other")).toBe(false);
    // Another project's worktrees are another project's.
    expect(rootBelongsToProject(settings, project, "/tmp/text-to-cad-worktrees/other/slug")).toBe(false);
    // The worktree folder itself is not a worktree.
    expect(rootBelongsToProject(settings, project, projectWorktreeDir(settings, project))).toBe(false);
    // Climbing out of the worktree folder is not in it.
    expect(rootBelongsToProject(settings, project, `${projectWorktreeDir(settings, project)}/slug/../../..`)).toBe(false);
    expect(() => resolveProjectRoot(settings, project, "/etc")).toThrow("does not belong to this project");
  });
});

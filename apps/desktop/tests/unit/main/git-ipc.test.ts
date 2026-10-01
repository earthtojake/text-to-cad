/**
 * `git.*` handlers: which directory a request is answered in, and which
 * worktrees a project may delete. A session id that matches nothing must not
 * quietly become the project's main checkout, and a worktree folder shared by
 * two same-named projects must not let one delete the other's work.
 */
import { execFile } from "node:child_process";
import { mkdir, mkdtemp, realpath, rm, stat, symlink, utimes, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";

import { afterAll, afterEach, beforeEach, expect, test, vi } from "vitest";

type Row = { id: string; projectId: string; cwd: string; worktreePath?: string; archived: boolean };
const state = vi.hoisted(() => ({
  projects: [] as { id: string; name: string; path: string; createdAt: number }[],
  sessions: [] as Row[],
  worktreeRoot: "",
  settings: {} as Record<string, unknown>,
}));
vi.mock("@main/telemetry", () => ({ track: () => {}, fileExtension: () => "none" }));
vi.mock("electron", () => ({ BrowserWindow: {}, dialog: {}, ipcMain: {}, shell: {} }));
vi.mock("@main/db/repositories", async () => {
  const { defaultSettings } = await import("@shared/types");
  return {
    projects: {
      get: (id: string) => state.projects.find((project) => project.id === id) ?? null,
      list: () => state.projects,
    },
    sessions: {
      get: (id: string) => state.sessions.find((session) => session.id === id) ?? null,
      list: (projectId?: string) => state.sessions.filter((session) => !projectId || session.projectId === projectId),
    },
    settings: { get: () => ({ ...defaultSettings(), worktreeRoot: state.worktreeRoot, ...state.settings }) },
    explorerTabs: {},
  };
});

import { gitHandlers, markCreating, pruneProjectWorktrees, sessionWorkspace, sessionWorkspaceSettled } from "@main/ipc/git";
import * as git from "@main/projects/git";
import { legacyProjectWorktreeDir, projectWorktreeDir } from "@main/projects/workspace";

import { cleanGitTemplates, committedRepository, GIT_ENV } from "./git-fixtures";

const run = promisify(execFile);
// `git.commit` runs through the app's own git, which reads the identity from the environment.
const previousEnv = { ...process.env };

let base = "";
beforeEach(async () => {
  Object.assign(process.env, GIT_ENV);
  base = await realpath(await mkdtemp(path.join(os.tmpdir(), "t2c-git-ipc-")));
  state.worktreeRoot = path.join(base, "worktrees");
  state.projects = [];
  state.sessions = [];
  state.settings = {};
});
afterEach(async () => {
  process.env = { ...previousEnv };
  await rm(base, { recursive: true, force: true });
});
afterAll(cleanGitTemplates);

/** A one-commit repository at `directory`, copied from this file's template, as a project. */
async function repository(id: string, directory: string) {
  await committedRepository(directory);
  const project = { id, name: path.basename(directory), path: directory, createdAt: 0 };
  state.projects.push(project);
  return project;
}

const exists = (target: string) => stat(target).then(() => true, () => false);

test("a session id that matches no session of the project is refused, not answered in the main checkout", async () => {
  const project = await repository("a", path.join(base, "robot-arm"));
  const other = await repository("b", path.join(base, "other"));
  state.sessions.push({ id: "elsewhere", projectId: other.id, cwd: other.path, archived: false });
  await writeFile(path.join(project.path, "wip.txt"), "not for main\n");
  const before = await git.head(project.path);

  for (const sessionId of ["deleted", "elsewhere"]) {
    const refused = { name: "IpcError", message: "that session is no longer open" };
    await expect(gitHandlers.git.commit({ projectId: project.id, sessionId, message: "x", push: true })).rejects.toMatchObject(refused);
    await expect(gitHandlers.git.status({ projectId: project.id, sessionId })).rejects.toMatchObject(refused);
  }
  expect(await git.head(project.path)).toBe(before);

  // No session at all is the project's checkout, as before.
  await expect(gitHandlers.git.status({ projectId: project.id })).resolves.toMatchObject({ isRepository: true });
});

test("a project cannot delete a same-named project's worktree from the shared legacy folder", async () => {
  const mine = await repository("mine", path.join(base, "work", "robot-arm"));
  const theirs = await repository("theirs", path.join(base, "forks", "robot-arm"));
  const settings = { worktreeRoot: state.worktreeRoot };
  expect(legacyProjectWorktreeDir(settings, mine)).toBe(legacyProjectWorktreeDir(settings, theirs));

  const created = await git.createWorktree({
    repoPath: mine.path,
    parentDir: legacyProjectWorktreeDir(settings, mine),
    name: "wrist",
  });

  await expect(gitHandlers.git.removeWorktree({ projectId: theirs.id, path: created.path })).rejects.toMatchObject({
    name: "IpcError",
    message: "that worktree does not belong to this project",
  });
  expect(await exists(created.path)).toBe(true);
  // Its own project still lists and removes it: old folders keep working.
  expect((await gitHandlers.git.worktrees({ projectId: mine.id })).map((row) => row.path)).toEqual([created.path]);
  expect(await gitHandlers.git.worktrees({ projectId: theirs.id })).toEqual([]);
  await gitHandlers.git.removeWorktree({ projectId: mine.id, path: created.path });
  expect(await exists(created.path)).toBe(false);
});

test("a worktree a session is using is not removed, even forced", async () => {
  const project = await repository("a", path.join(base, "robot-arm"));
  const created = await git.createWorktree({
    repoPath: project.path,
    parentDir: path.join(state.worktreeRoot, "unused"),
    name: "wrist",
  });
  state.sessions.push({ id: "s", projectId: project.id, cwd: created.path, worktreePath: created.path, archived: false });

  await expect(gitHandlers.git.removeWorktree({ projectId: project.id, path: created.path, force: true })).rejects.toMatchObject({
    name: "IpcError",
    message: "1 session is still using that worktree",
  });
  expect(await exists(created.path)).toBe(true);
});

test("the keep-limit sweep spares a worktree another project's session belongs to, or runs inside", async () => {
  const project = await repository("a", path.join(base, "robot-arm"));
  state.settings = { autoDeleteWorktrees: true, worktreeKeepLimit: 1 };
  const parentDir = projectWorktreeDir({ worktreeRoot: state.worktreeRoot }, project);
  const opened = await git.createWorktree({ repoPath: project.path, parentDir, name: "opened as a project" });
  const inside = await git.createWorktree({ repoPath: project.path, parentDir, name: "session in a subfolder" });
  const spare = await git.createWorktree({ repoPath: project.path, parentDir, name: "spare" });
  const newest = await git.createWorktree({ repoPath: project.path, parentDir, name: "newest" });
  const hourAgo = new Date(Date.now() - 3_600_000);
  await utimes(path.join(spare.path, "README.md"), hourAgo, hourAgo);
  await utimes(spare.path, hourAgo, hourAgo);
  await mkdir(path.join(inside.path, "parts"));
  // The worktree folder chosen as a project of its own, and a session of this
  // project running in a folder inside another worktree.
  state.sessions.push(
    { id: "s1", projectId: opened.path, cwd: opened.path, archived: false },
    { id: "s2", projectId: project.id, cwd: path.join(inside.path, "parts"), archived: false },
  );

  await pruneProjectWorktrees(project);
  expect(await exists(opened.path)).toBe(true);
  expect(await exists(inside.path)).toBe(true);
  // Of the two nobody uses, the older was past the limit and went.
  expect(await exists(newest.path)).toBe(true);
  expect(await exists(spare.path)).toBe(false);
});

test("two creates in flight at keep 1: neither sweep removes the other's worktree before its row exists", async () => {
  const project = await repository("a", path.join(base, "robot-arm"));
  state.settings = { autoDeleteWorktrees: true, worktreeKeepLimit: 1 };
  const parentDir = projectWorktreeDir({ worktreeRoot: state.worktreeRoot }, project);
  // Create A has its worktree and is waiting to write its row; create B makes
  // its own and sweeps.
  const first = await git.createWorktree({ repoPath: project.path, parentDir, name: "first" });
  const firstDone = markCreating(first.path);
  const hourAgo = new Date(Date.now() - 3_600_000);
  await utimes(path.join(first.path, "README.md"), hourAgo, hourAgo);
  await utimes(first.path, hourAgo, hourAgo);
  const second = await git.createWorktree({ repoPath: project.path, parentDir, name: "second" });
  const secondDone = markCreating(second.path);

  await pruneProjectWorktrees(project);
  expect(await exists(first.path)).toBe(true);
  expect(await exists(second.path)).toBe(true);

  // Both creates settle without a row (say both failed): each is now just a
  // worktree, and the older one is past the limit.
  secondDone();
  firstDone();
  await pruneProjectWorktrees(project);
  expect(await exists(first.path)).toBe(false);
  expect(await exists(second.path)).toBe(true);
});

test("a create does not wait on the keep-limit sweep, which runs once the row exists", async () => {
  const project = await repository("a", path.join(base, "robot-arm"));
  state.settings = { autoDeleteWorktrees: true, worktreeKeepLimit: 1 };
  const parentDir = projectWorktreeDir({ worktreeRoot: state.worktreeRoot }, project);
  // Two nobody uses, at a limit of one (a session's own never counts): the
  // older is past it.
  const old = await git.createWorktree({ repoPath: project.path, parentDir, name: "old" });
  const hourAgo = new Date(Date.now() - 3_600_000);
  await utimes(path.join(old.path, "README.md"), hourAgo, hourAgo);
  await utimes(old.path, hourAgo, hourAgo);
  const recent = await git.createWorktree({ repoPath: project.path, parentDir, name: "recent" });

  // A `git` whose `worktree list` — the sweep's first read — waits for a
  // gate file: a sweep over a large repository, as slow as it likes (thirty
  // seconds at most, so a failed run leaves nothing spinning). It leaves a `listed` marker when
  // the wait ends, so "the create did not wait for the sweep" is read from the files rather than
  // from a clock.
  const real = (await run("sh", ["-c", "command -v git"])).stdout.trim();
  const bin = path.join(base, "bin");
  await mkdir(bin);
  const gate = path.join(base, "gate");
  await writeFile(
    path.join(bin, "git"),
    `#!/bin/sh\ncase "$*" in *"worktree list"*) i=0; while [ ! -f "${gate}" ] && [ $i -lt 1500 ]; do sleep 0.02; i=$((i+1)); done; : > "${base}/listed";; esac\nexec "${real}" "$@"\n`,
    { mode: 0o755 },
  );
  process.env.PATH = `${bin}${path.delimiter}${process.env.PATH ?? ""}`;

  // The create returns while the sweep's `worktree list` is still waiting on the gate: had the
  // create awaited the sweep, the marker would be there (the gate only opens below).
  const created = await sessionWorkspace({ projectId: project.id, gitMode: "worktree", name: "new" });
  expect(await exists(path.join(base, "listed"))).toBe(false);
  // The row is written, and the create is told so — which starts the sweep.
  state.sessions.push({ id: "s", projectId: project.id, cwd: created.cwd, worktreePath: created.worktreePath!, archived: false });
  sessionWorkspaceSettled(created);
  expect(await exists(old.path)).toBe(true);

  await writeFile(gate, "");
  await vi.waitFor(async () => expect(await exists(old.path)).toBe(false), { timeout: 15_000, interval: 100 });
  expect(await exists(recent.path)).toBe(true);
  expect(await exists(created.cwd)).toBe(true);
}, 40_000);

test("a worktree whose folder was deleted by hand lists as deletable, not as unchecked", async () => {
  const project = await repository("a", path.join(base, "robot-arm"));
  const created = await git.createWorktree({
    repoPath: project.path,
    parentDir: projectWorktreeDir({ worktreeRoot: state.worktreeRoot }, project),
    name: "wrist",
  });
  await rm(created.path, { recursive: true, force: true });

  const rows = await gitHandlers.git.worktrees({ projectId: project.id });
  expect(rows.map((row) => [row.path, row.dirty])).toEqual([[created.path, false]]);
  await gitHandlers.git.removeWorktree({ projectId: project.id, path: created.path });
  expect(await gitHandlers.git.worktrees({ projectId: project.id })).toEqual([]);
});

test("a clean worktree on a detached commit no branch holds lists as stranded, not as dirty files", async () => {
  const project = await repository("a", path.join(base, "robot-arm"));
  const created = await git.createWorktree({
    repoPath: project.path,
    parentDir: projectWorktreeDir({ worktreeRoot: state.worktreeRoot }, project),
    name: "wrist",
  });
  await run("git", ["checkout", "--quiet", "--detach"], { cwd: created.path });
  await run("git", ["commit", "--quiet", "--allow-empty", "-m", "only here"], { cwd: created.path });

  const rows = await gitHandlers.git.worktrees({ projectId: project.id });
  expect(rows.map((row) => [row.path, row.dirty])).toEqual([[created.path, false]]);
  expect(rows.map((row) => [row.path, row.stranded])).toEqual([[created.path, true]]);
});

test("a push that failed after its commit is retried by asking again, without 'nothing to commit'", async () => {
  const project = await repository("a", path.join(base, "robot-arm"));
  const remote = path.join(base, "remote.git");
  await run("git", ["init", "--quiet", "--bare", "--initial-branch=main", remote], { env: process.env });
  await run("git", ["remote", "add", "origin", path.join(base, "not-there.git")], { cwd: project.path });
  await writeFile(path.join(project.path, "wrist.txt"), "wrist\n");

  // The commit lands, the push does not: a clean tree with a commit nobody has.
  await expect(gitHandlers.git.commit({ projectId: project.id, message: "add wrist", push: true })).rejects.toThrow();
  const committed = await git.head(project.path);
  // Two: the fixture's first commit was never pushed either.
  expect(await gitHandlers.git.status({ projectId: project.id })).toMatchObject({ workingFiles: 0, ahead: 2 });

  await run("git", ["remote", "set-url", "origin", remote], { cwd: project.path });
  const retried = await gitHandlers.git.commit({ projectId: project.id, message: "", push: true });
  expect(retried).toMatchObject({ sha: committed, pushedOnly: true, pushed: 2 });
  expect((await run("git", ["rev-parse", "main"], { cwd: remote })).stdout.trim()).toBe(committed);
  expect(await gitHandlers.git.status({ projectId: project.id })).toMatchObject({ ahead: 0 });
});

test("an archived thread does not hold a worktree, and one in a subfolder does", async () => {
  const project = await repository("a", path.join(base, "robot-arm"));
  const created = await git.createWorktree({
    repoPath: project.path,
    parentDir: projectWorktreeDir({ worktreeRoot: state.worktreeRoot }, project),
    name: "wrist",
  });
  const listed = async () => (await gitHandlers.git.worktrees({ projectId: project.id })).map((row) => [row.openSessions, row.dirty]);

  // Archived: not open, so Delete is on offer and main agrees.
  state.sessions.push({ id: "old", projectId: project.id, cwd: created.path, worktreePath: created.path, archived: true });
  expect(await listed()).toEqual([[0, false]]);

  // In a folder inside it: open in the list, and refused in main.
  await mkdir(path.join(created.path, "parts"));
  state.sessions.push({ id: "deep", projectId: project.id, cwd: path.join(created.path, "parts"), archived: false });
  expect(await listed()).toEqual([[1, false]]);
  await expect(gitHandlers.git.removeWorktree({ projectId: project.id, path: created.path })).rejects.toMatchObject({
    message: "1 session is still using that worktree",
  });

  state.sessions = state.sessions.filter((row) => row.id === "old");
  await gitHandlers.git.removeWorktree({ projectId: project.id, path: created.path });
  expect(await exists(created.path)).toBe(false);
});

test("a worktree made under a symlinked worktreeRoot is listed, counted by projectInfo, and deletable", async () => {
  const project = await repository("a", path.join(base, "robot-arm"));
  const realRoot = path.join(base, "real-worktrees");
  const linkRoot = path.join(base, "link-worktrees");
  await mkdir(realRoot);
  await symlink(realRoot, linkRoot);
  // The setting names the link; git reports the real spelling.
  state.worktreeRoot = linkRoot;
  const parentDir = projectWorktreeDir({ worktreeRoot: linkRoot }, project);
  expect(parentDir.startsWith(linkRoot)).toBe(true);
  const created = await git.createWorktree({ repoPath: project.path, parentDir, name: "wrist" });

  const listed = await gitHandlers.git.worktrees({ projectId: project.id });
  expect(listed.map((row) => row.path), "the Settings list must see a worktree under a symlinked root").toEqual([created.path]);
  const info = await gitHandlers.git.projectInfo({ projectId: project.id });
  expect(info.worktreeCount, "projectInfo must count it").toBe(1);

  // Deleted by the spelling the setting uses (git lists the real one).
  const spelledThroughLink = path.join(linkRoot, path.relative(realRoot, created.path));
  await gitHandlers.git.removeWorktree({ projectId: project.id, path: spelledThroughLink });
  expect(await exists(created.path)).toBe(false);
  expect(await gitHandlers.git.worktrees({ projectId: project.id })).toEqual([]);
});

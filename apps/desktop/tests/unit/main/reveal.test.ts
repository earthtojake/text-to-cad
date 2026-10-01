/**
 * `shell.showItemInFolder` takes a project, not a path: main resolves the
 * directory and refuses one that is not the project's own.
 */
import type * as NodeFs from "node:fs";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterAll, beforeAll, beforeEach, expect, test, vi } from "vitest";

const fixture = vi.hoisted(() => ({
  root: "",
  project: "",
  worktrees: "",
  sessions: [] as { projectId: string; cwd: string; worktreePath?: string }[],
}));
const showItemInFolder = vi.hoisted(() => vi.fn());
// realpathSync is synchronous on main's thread and rootOf runs for every
// stat/list/read/exists: the spy counts how often it reaches the disk.
const realpaths = vi.hoisted(() => ({ calls: [] as string[] }));
vi.mock("node:fs", async (importOriginal) => {
  const actual = await importOriginal<typeof NodeFs>();
  const realpathSync = ((target: string, ...rest: unknown[]) => {
    realpaths.calls.push(String(target));
    return (actual.realpathSync as (...args: unknown[]) => string)(target, ...rest);
  }) as typeof actual.realpathSync;
  return { ...actual, realpathSync, default: { ...actual, realpathSync } };
});
vi.mock("@main/telemetry", () => ({ track: () => {}, fileExtension: () => "none" }));
vi.mock("electron", () => ({ BrowserWindow: {}, dialog: {}, ipcMain: {}, shell: { showItemInFolder } }));
vi.mock("@main/db/repositories", () => ({
  projects: {
    get: (id: string) => id === "project" ? { id, name: "demo", path: fixture.project } : null,
    list: () => [{ id: "project", name: "demo", path: fixture.project }],
  },
  sessions: { list: () => fixture.sessions },
  settings: { get: () => ({ worktreeRoot: fixture.worktrees }) },
  explorerTabs: {},
}));
import { projectOfRoot, revealProjectDirectory, rootOf } from "@main/ipc/explorer";
import { IpcError } from "@main/ipc/register";
import { projectWorktreeDir } from "@main/projects/workspace";

/** The call is refused by main's IpcError with exactly this sentence — not any throw (a missing function's TypeError would pass a bare `toThrow()`). */
function expectRefused(call: () => unknown, message: string): void {
  let caught: unknown;
  try {
    call();
  } catch (error) {
    caught = error;
  }
  expect(caught).toBeInstanceOf(IpcError);
  expect((caught as Error).message).toBe(message);
}

/** The project's worktree folder: `<root>/demo-<hash of its path>`. */
const worktreeFolder = () => projectWorktreeDir({ worktreeRoot: fixture.worktrees }, { name: "demo", path: fixture.project });

beforeAll(async () => {
  fixture.root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), "reveal-")));
  fixture.project = path.join(fixture.root, "demo");
  fixture.worktrees = path.join(fixture.root, "worktrees");
  await fs.mkdir(path.join(worktreeFolder(), "feature"), { recursive: true });
  await fs.mkdir(path.join(fixture.root, "elsewhere"), { recursive: true });
  await fs.mkdir(fixture.project, { recursive: true });
});
afterAll(async () => { await fs.rm(fixture.root, { recursive: true, force: true }); });
beforeEach(() => { showItemInFolder.mockClear(); fixture.sessions = []; });

test("reveals the project, its worktree and its worktree folder", () => {
  revealProjectDirectory({ projectId: "project" });
  revealProjectDirectory({ projectId: "project", root: path.join(worktreeFolder(), "feature") });
  revealProjectDirectory({ projectId: "project", worktrees: true });
  expect(showItemInFolder.mock.calls.map(([target]) => target)).toEqual([
    fixture.project,
    path.join(worktreeFolder(), "feature"),
    worktreeFolder(),
  ]);
});

test("refuses a directory outside the project, and an unknown project", () => {
  expectRefused(() => revealProjectDirectory({ projectId: "project", root: path.join(fixture.root, "elsewhere") }), "that directory does not belong to this project");
  expectRefused(() => revealProjectDirectory({ projectId: "project", root: "/etc" }), "that directory does not belong to this project");
  expectRefused(() => revealProjectDirectory({ projectId: "other", worktrees: true }), "that project is no longer open");
  expect(showItemInFolder).not.toHaveBeenCalled();
});

test("a session's recorded worktree is handed on as the session recorded it, not as the caller spelled it", async () => {
  // A worktree an older layout made outside the worktree root, recorded
  // through a link (a dotfile-managed ~/.text-to-cad, /tmp on macOS). The
  // record keeps access, and the root that leaves main is the recorded
  // spelling: watchers, `files.changed` and the CAD viewer are keyed by it,
  // and the renderer compares it with the session's worktreePath by `===`.
  const real = path.join(fixture.root, "legacy-worktree");
  const linked = path.join(fixture.root, "linked-worktree");
  await fs.mkdir(real, { recursive: true });
  await fs.symlink(real, linked);
  fixture.sessions = [{ projectId: "project", cwd: linked, worktreePath: linked }];
  revealProjectDirectory({ projectId: "project", root: linked });
  // The caller's spelling differs (a trailing slash, the real path): the
  // recorded one is still what is handed on.
  revealProjectDirectory({ projectId: "project", root: `${linked}/` });
  revealProjectDirectory({ projectId: "project", root: real });
  expect(showItemInFolder.mock.calls.map(([target]) => target)).toEqual([linked, linked, linked]);
});

test("a root spelled as recorded is matched without touching the disk; another spelling realpaths each session once", async () => {
  const real = path.join(fixture.root, "cached-worktree");
  const linked = path.join(fixture.root, "cached-link");
  await fs.mkdir(real, { recursive: true });
  await fs.symlink(real, linked);
  const other = path.join(fixture.root, "other-worktree");
  await fs.mkdir(other, { recursive: true });
  fixture.sessions = [
    { projectId: "project", cwd: other, worktreePath: other },
    { projectId: "project", cwd: linked, worktreePath: linked },
  ];

  realpaths.calls = [];
  expect(rootOf("project", linked)).toBe(linked);
  expect(rootOf("project", `${linked}/`)).toBe(linked);
  expect(realpaths.calls).toEqual([]);

  // The symlink case still resolves to the recorded spelling, and the
  // sessions' realpaths are cached by spelling across calls.
  expect(rootOf("project", real)).toBe(linked);
  expect(rootOf("project", real)).toBe(linked);
  expect(realpaths.calls.filter((call) => call === linked)).toHaveLength(1);
  expect(realpaths.calls.filter((call) => call === other)).toHaveLength(1);

  // A change to the sessions invalidates: a new recorded spelling is found.
  const moved = path.join(fixture.root, "moved-link");
  await fs.symlink(real, moved);
  fixture.sessions = [{ projectId: "project", cwd: moved, worktreePath: moved }];
  expect(rootOf("project", real)).toBe(moved);
});

test("a watched worktree maps to its project from either worktree folder, the pre-hash one only when git links it", async () => {
  const { execFile } = await import("node:child_process");
  const { promisify } = await import("node:util");
  const env = {
    ...process.env,
    GIT_AUTHOR_NAME: "t", GIT_AUTHOR_EMAIL: "t@example.invalid",
    GIT_COMMITTER_NAME: "t", GIT_COMMITTER_EMAIL: "t@example.invalid",
    GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_SYSTEM: "/dev/null",
  };
  const git = (...args: string[]) => promisify(execFile)("git", args, { cwd: fixture.project, env });
  await git("init", "--quiet", "--initial-branch=main");
  await git("commit", "--quiet", "--allow-empty", "-m", "first");
  const legacy = path.join(fixture.worktrees, "demo", "old-layout");
  await git("worktree", "add", "--quiet", "-b", "old-layout", legacy);
  const stray = path.join(fixture.worktrees, "demo", "stray");
  await fs.mkdir(stray, { recursive: true });

  expect(projectOfRoot(path.join(worktreeFolder(), "feature"))).toEqual({ project: expect.objectContaining({ id: "project" }), root: path.join(worktreeFolder(), "feature") });
  expect(projectOfRoot(legacy)).toEqual({ project: expect.objectContaining({ id: "project" }), root: legacy });
  // A directory in the shared pre-hash folder that is not this repository's worktree is nobody's.
  expect(projectOfRoot(stray)).toBeNull();
});

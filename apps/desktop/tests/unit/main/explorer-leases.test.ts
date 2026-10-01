/**
 * A page's watches are given back for it when another document commits in
 * its place or its renderer goes — not when a navigation merely starts: the
 * window cancels every `will-navigate` (a stray link, a dropped file), and
 * `did-start-navigation` comes first.
 */
import { EventEmitter } from "node:events";
import { beforeEach, expect, test, vi } from "vitest";
import type { WebContents } from "electron";

const fixture = vi.hoisted(() => ({ root: "/projects/demo", gone: false }));
const watchers = vi.hoisted(() => ({ watch: vi.fn(async () => {}), unwatch: vi.fn(async () => {}) }));
vi.mock("@main/telemetry", () => ({ track: () => {}, fileExtension: () => "none" }));
vi.mock("electron", () => ({ BrowserWindow: {}, dialog: {}, ipcMain: {}, shell: {} }));
vi.mock("@main/explorer/fs", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  FileWatchers: class {
    watch = watchers.watch;
    unwatch = watchers.unwatch;
  },
}));
vi.mock("@main/db/repositories", () => ({
  projects: {
    get: (id: string) => id === "project" && !fixture.gone ? { id, name: "demo", path: fixture.root } : null,
    list: () => [{ id: "project", name: "demo", path: fixture.root }],
  },
  sessions: { get: () => null, list: () => [] },
  settings: { get: () => ({}) },
  explorerTabs: {},
}));
vi.mock("@main/projects/workspace", async (importOriginal) => ({ ...(await importOriginal<object>()), resolveProjectRoot: () => fixture.root }));
import { explorerHandlers, initExplorerServices } from "@main/ipc/explorer";

let nextId = 1;
function page() {
  const sender = Object.assign(new EventEmitter(), { id: nextId++ });
  return { sender, ctx: { sender: sender as unknown as WebContents } as Parameters<typeof explorerHandlers.explorer.watch>[1] };
}

beforeEach(() => {
  fixture.gone = false;
  fixture.root = "/projects/demo";
  initExplorerServices(() => {});
  watchers.watch.mockReset().mockImplementation(async () => {});
  watchers.unwatch.mockReset().mockImplementation(async () => {});
});

test("a navigation that starts and is cancelled keeps the page's watches", async () => {
  const { sender, ctx } = page();
  await explorerHandlers.explorer.watch({ projectId: "project" }, ctx);
  sender.emit("did-start-navigation", { isMainFrame: true, isSameDocument: false });
  expect(watchers.unwatch).not.toHaveBeenCalled();
  // The page still holds it, so its own unwatch still gives it back.
  await explorerHandlers.explorer.unwatch({ projectId: "project" }, ctx);
  expect(watchers.unwatch).toHaveBeenCalledTimes(1);
});

test("a committed navigation, a dead renderer and a destroyed page each give the watches back once", async () => {
  for (const event of ["did-navigate", "render-process-gone", "destroyed"]) {
    watchers.unwatch.mockClear();
    const { sender, ctx } = page();
    await explorerHandlers.explorer.watch({ projectId: "project" }, ctx);
    await explorerHandlers.explorer.watch({ projectId: "project" }, ctx);
    sender.emit(event);
    expect(watchers.unwatch).toHaveBeenCalledTimes(2);
    // The old page's late unwatch is already counted.
    await explorerHandlers.explorer.unwatch({ projectId: "project" }, ctx);
    expect(watchers.unwatch).toHaveBeenCalledTimes(2);
  }
});

test("a watch still setting up when the page navigates is not credited to the new page", async () => {
  const { sender, ctx } = page();
  // The page holds one watch already, so its listeners are in place.
  await explorerHandlers.explorer.watch({ projectId: "project" }, ctx);
  let finish!: () => void;
  watchers.watch.mockImplementationOnce(() => new Promise<void>((resolve) => { finish = resolve; }));
  const pending = explorerHandlers.explorer.watch({ projectId: "project" }, ctx);
  sender.emit("did-navigate");
  expect(watchers.unwatch).toHaveBeenCalledTimes(1);
  finish();
  await pending;
  // Given back at once: the document that asked for it is gone.
  expect(watchers.unwatch).toHaveBeenCalledTimes(2);
  // The new page holds nothing, so the next navigation gives back nothing.
  sender.emit("did-navigate");
  expect(watchers.unwatch).toHaveBeenCalledTimes(2);
});

test("an unwatch that overtakes its page's watch still gives that watch back", async () => {
  const { ctx } = page();
  let finish!: () => void;
  watchers.watch.mockImplementationOnce(() => new Promise<void>((resolve) => { finish = resolve; }));
  const pending = explorerHandlers.explorer.watch({ projectId: "project", paths: ["a.txt"] }, ctx);
  // The tab closed while its watch was still setting up: no lease yet to return.
  const unwatch = explorerHandlers.explorer.unwatch({ projectId: "project", paths: ["a.txt"] }, ctx);
  finish();
  await Promise.all([pending, unwatch]);
  expect(watchers.unwatch).toHaveBeenCalledTimes(1);
  expect(watchers.unwatch).toHaveBeenCalledWith(fixture.root, ["a.txt"]);
});

test("an unwatch after the project row is deleted still gives the watch back", async () => {
  const { ctx } = page();
  await explorerHandlers.explorer.watch({ projectId: "project" }, ctx);
  // The delete landed first: rootOf has no project to resolve the request against.
  fixture.gone = true;
  await explorerHandlers.explorer.unwatch({ projectId: "project" }, ctx);
  expect(watchers.unwatch).toHaveBeenCalledTimes(1);
});

test("one request that resolved to two roots gives each watch's own root back, oldest first", async () => {
  const { ctx } = page();
  await explorerHandlers.explorer.watch({ projectId: "project" }, ctx);
  // The session's worktree changed under the same (project, root) request.
  fixture.root = "/projects/demo-worktree";
  await explorerHandlers.explorer.watch({ projectId: "project" }, ctx);
  await explorerHandlers.explorer.unwatch({ projectId: "project" }, ctx);
  await explorerHandlers.explorer.unwatch({ projectId: "project" }, ctx);
  expect((watchers.unwatch.mock.calls as unknown as string[][]).map(([directory]) => directory)).toEqual(["/projects/demo", "/projects/demo-worktree"]);
  // Nothing is left to give back, and no stale entry answers for the request.
  fixture.gone = true;
  await expect(explorerHandlers.explorer.unwatch({ projectId: "project" }, ctx)).rejects.toThrow();
});

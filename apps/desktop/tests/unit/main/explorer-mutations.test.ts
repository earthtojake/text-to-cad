import { EventEmitter } from "node:events";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterAll, beforeAll, expect, test, vi } from "vitest";

import type * as Telemetry from "@main/telemetry";

const fixture = vi.hoisted(() => {
  // Compiled in by electron-vite; the real `fileExtension` is under test, so
  // the module is loaded with its key blank and Aptabase stubbed.
  (globalThis as { __APTABASE_KEY__?: string }).__APTABASE_KEY__ = "";
  return { root: "", track: vi.fn(), trash: vi.fn(async (_target: string) => {}) };
});
vi.mock("@aptabase/electron/main", () => ({ initialize: vi.fn(), trackEvent: vi.fn() }));
vi.mock("@main/telemetry", async (importOriginal) => ({
  ...(await importOriginal<typeof Telemetry>()),
  track: fixture.track,
}));
vi.mock("electron", () => ({ BrowserWindow: {}, dialog: {}, ipcMain: {}, shell: { trashItem: fixture.trash } }));
vi.mock("@main/db/repositories", () => ({
  projects: {
    get: (id: string) => id === "project" ? { id, path: fixture.root } : null,
    list: () => [{ id: "project", path: fixture.root }],
  },
  sessions: { list: () => [{ id: "session", projectId: "project", cwd: fixture.root }] },
  settings: { get: () => ({}) }, explorerTabs: {},
}));
// The real `realDirectory`: `explorer/fs` resolves new paths through it, and an
// identity stub would quietly turn that containment check back into a lexical one.
vi.mock("@main/projects/workspace", async (importOriginal) => ({ ...(await importOriginal<object>()), resolveProjectRoot: () => fixture.root, projectWorktreeDir: () => fixture.root }));
import { explorerHandlers, initExplorerServices, disposeExplorerServices } from "@main/ipc/explorer";
import { FileWatchers } from "@main/explorer/fs";
import type { IpcContext } from "@main/ipc/register";
import { fileExtension } from "@main/telemetry";
import { FileMutationResultSchema, TextWriteResultSchema } from "@shared/ipc/explorer";

beforeAll(async () => { fixture.root = await fs.mkdtemp(path.join(os.tmpdir(), "file-mutations-")); });
afterAll(async () => { await fs.rm(fixture.root, { recursive: true, force: true }); });
const at = { projectId: "project" };

test("IPC returns validated typed conflicts and never overwrites their contents", async () => {
  await fs.writeFile(path.join(fixture.root, "note.txt"), "external");
  const conflict = TextWriteResultSchema.parse(await explorerHandlers.explorer.writeText({ ...at, path: "note.txt", content: "stale", expectedRevision: "before" }));
  expect(conflict).toMatchObject({ status: "conflict", actualRevision: expect.any(String) });
  expect(await fs.readFile(path.join(fixture.root, "note.txt"), "utf8")).toBe("external");
  const denied = TextWriteResultSchema.parse(await explorerHandlers.explorer.writeText({ ...at, path: "../outside.txt", content: "refused" }));
  expect(denied).toMatchObject({ status: "error", code: "denied" });
});

test("IPC commits create/move receipts with exact identities and reports failures by code", async () => {
  const created = FileMutationResultSchema.parse(await explorerHandlers.explorer.createFile({ ...at, path: "", name: "created.txt" }));
  expect(created).toMatchObject({ status: "committed", path: "created.txt", change: { kind: "added", directory: false, mutationId: expect.any(String) } });
  const moved = FileMutationResultSchema.parse(await explorerHandlers.explorer.rename({ ...at, path: "created.txt", name: "moved.txt" }));
  expect(moved).toMatchObject({ status: "committed", path: "moved.txt", change: { kind: "moved", previousPath: "created.txt", path: "moved.txt" } });
  const conflict = FileMutationResultSchema.parse(await explorerHandlers.explorer.createFile({ ...at, path: "", name: "moved.txt" }));
  expect(conflict).toMatchObject({ status: "failed", code: "already-exists" });
  const missing = FileMutationResultSchema.parse(await explorerHandlers.explorer.rename({ ...at, path: "missing", name: "another" }));
  expect(missing).toMatchObject({ status: "failed", code: "not-found" });
});

test("a notification failure cannot turn a committed save or move into failure", async () => {
  initExplorerServices(() => { throw new Error("window disappeared"); });
  try {
    const saved = TextWriteResultSchema.parse(await explorerHandlers.explorer.writeText({ ...at, path: "receipt.txt", content: "committed" }));
    expect(saved).toMatchObject({ status: "saved", document: { content: "committed" } });
    const moved = FileMutationResultSchema.parse(await explorerHandlers.explorer.rename({ ...at, path: "receipt.txt", name: "receipt-moved.txt" }));
    expect(moved).toMatchObject({ status: "committed", path: "receipt-moved.txt" });
    expect(await fs.readFile(path.join(fixture.root, "receipt-moved.txt"), "utf8")).toBe("committed");
  } finally { disposeExplorerServices(); }
});

test("opening a file counts its extension and nothing else; a directory or a failed stat counts nothing", async () => {
  await fs.mkdir(path.join(fixture.root, "Secret Project"), { recursive: true });
  await fs.writeFile(path.join(fixture.root, "Secret Project", "Gripper.STL"), "solid");
  fixture.track.mockClear();
  await explorerHandlers.explorer.stat({ ...at, path: "Secret Project/Gripper.STL", intent: "open" });
  await explorerHandlers.explorer.stat({ ...at, path: "Secret Project", intent: "open" });
  await expect(explorerHandlers.explorer.stat({ ...at, path: "missing.step", intent: "open" })).rejects.toThrow();
  expect(fixture.track.mock.calls).toEqual([[{ name: "file_opened", extension: "stl" }]]);
});

test("a stat that is not a tab opening — an attachment check, an integration lookup — neither counts nor watches", async () => {
  await fs.mkdir(path.join(fixture.root, "attach"), { recursive: true });
  await fs.writeFile(path.join(fixture.root, "attach", "part.step"), "ISO-10303-21;");
  fixture.track.mockClear();
  const watchEntry = vi.spyOn(FileWatchers.prototype, "watchEntry").mockResolvedValue();
  initExplorerServices(() => {});
  try {
    await explorerHandlers.explorer.stat({ ...at, path: "attach/part.step" });
    expect(fixture.track).not.toHaveBeenCalled();
    expect(watchEntry).not.toHaveBeenCalled();
    await explorerHandlers.explorer.stat({ ...at, path: "attach/part.step", intent: "open" });
    expect(fixture.track).toHaveBeenCalledOnce();
    expect(watchEntry).toHaveBeenCalledOnce();
  } finally { disposeExplorerServices(); watchEntry.mockRestore(); }
});

test("file_opened's extension is a short alphanumeric suffix or \"other\", never a fragment of a name", () => {
  expect(fileExtension("a/Gripper.STL")).toBe("stl");
  expect(fileExtension("a/model.step")).toBe("step");
  expect(fileExtension("README")).toBe("none");
  expect(fileExtension(".env")).toBe("none");
  expect(fileExtension("plan.acme-q3-layoffs")).toBe("other");
  expect(fileExtension("notes.confidential")).toBe("other");
  expect(fileExtension("photo.jpg ")).toBe("other");
  expect(fileExtension("archive.tar.gz")).toBe("gz");
});

test("trash, rename and duplicate act on a symlink row itself, and report the link's path", async () => {
  const outside = await fs.mkdtemp(path.join(os.tmpdir(), "file-mutations-outside-"));
  try {
    const dir = path.join(fixture.root, "linked");
    await fs.mkdir(path.join(dir, "shared"), { recursive: true });
    await fs.writeFile(path.join(dir, "v3.step"), "v3");
    await fs.symlink("v3.step", path.join(dir, "current.step"));
    await fs.symlink("shared", path.join(dir, "vendor"));
    await fs.symlink(outside, path.join(dir, "out"));
    const real = await fs.realpath(dir);
    fixture.trash.mockClear();

    const file = FileMutationResultSchema.parse(await explorerHandlers.explorer.trash({ ...at, path: "linked/current.step" }));
    expect(file).toMatchObject({ status: "committed", path: "linked/current.step", change: { kind: "removed", directory: false } });
    const folder = FileMutationResultSchema.parse(await explorerHandlers.explorer.trash({ ...at, path: "linked/vendor" }));
    expect(folder).toMatchObject({ status: "committed", path: "linked/vendor", change: { kind: "removed", directory: true } });
    const away = FileMutationResultSchema.parse(await explorerHandlers.explorer.trash({ ...at, path: "linked/out" }));
    expect(away).toMatchObject({ status: "committed", path: "linked/out" });
    expect(fixture.trash.mock.calls.map(([target]) => target)).toEqual([
      path.join(real, "current.step"), path.join(real, "vendor"), path.join(real, "out"),
    ]);
    // Through a link that leaves the root is still refused.
    const through = FileMutationResultSchema.parse(await explorerHandlers.explorer.trash({ ...at, path: "linked/out/x" }));
    expect(through).toMatchObject({ status: "failed", code: "denied" });

    const renamed = FileMutationResultSchema.parse(await explorerHandlers.explorer.rename({ ...at, path: "linked/vendor", name: "deps" }));
    expect(renamed).toMatchObject({ status: "committed", path: "linked/deps", change: { kind: "moved", previousPath: "linked/vendor", directory: true } });
    expect(await fs.readlink(path.join(dir, "deps"))).toBe("shared");
    const copied = FileMutationResultSchema.parse(await explorerHandlers.explorer.duplicate({ ...at, path: "linked/current.step" }));
    expect(copied).toMatchObject({ status: "committed", path: "linked/current copy.step" });
    expect(await fs.readlink(path.join(dir, "current copy.step"))).toBe("v3.step");
  } finally { await fs.rm(outside, { recursive: true, force: true }); }
});

test("a page that reloads gives back the watches it never unwatched, and only those", async () => {
  const watch = vi.spyOn(FileWatchers.prototype, "watch").mockResolvedValue();
  const unwatch = vi.spyOn(FileWatchers.prototype, "unwatch").mockResolvedValue();
  initExplorerServices(() => {});
  try {
    const page = Object.assign(new EventEmitter(), { id: 7 });
    const ctx = { sender: page, event: {} } as unknown as IpcContext;
    await explorerHandlers.explorer.watch(at, ctx);
    await explorerHandlers.explorer.watch(at, ctx);
    await explorerHandlers.explorer.unwatch(at, ctx);
    expect(unwatch).toHaveBeenCalledTimes(1);

    // Cmd+R: the old page sends no unwatch for the watch it still holds.
    page.emit("did-navigate");
    expect(unwatch).toHaveBeenCalledTimes(2);
    // A late unwatch from the page that left is not counted twice.
    await explorerHandlers.explorer.unwatch(at, ctx);
    expect(unwatch).toHaveBeenCalledTimes(2);
    // The new page's watch is its own lease.
    await explorerHandlers.explorer.watch(at, ctx);
    page.emit("did-navigate-in-page");
    expect(unwatch).toHaveBeenCalledTimes(2);
    page.emit("destroyed");
    expect(unwatch).toHaveBeenCalledTimes(3);
    expect(watch).toHaveBeenCalledTimes(3);
  } finally { disposeExplorerServices(); watch.mockRestore(); unwatch.mockRestore(); }
});

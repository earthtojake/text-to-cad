import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterAll, beforeAll, expect, test, vi } from "vitest";

const fixture = vi.hoisted(() => ({ root: "" }));
vi.mock("electron", () => ({ BrowserWindow: {}, dialog: {}, ipcMain: {}, shell: {} }));
vi.mock("@main/db/repositories", () => ({ projects: { list: () => [{ id: "project", path: fixture.root }] }, settings: { get: () => ({}) }, explorerTabs: {} }));
vi.mock("@main/projects/workspace", () => ({ resolveProjectRoot: () => fixture.root, projectWorktreeDir: () => fixture.root }));
import { explorerHandlers, initExplorerServices, disposeExplorerServices } from "@main/ipc/explorer";
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

import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { toast } from "sonner";
import { desktopLiveDocuments } from "@renderer/state/live-documents";
import type { PromptContextPort } from "@text-to-cad/core/prompt";
import type { FileChanges } from "@text-to-cad/ui/file-viewer";
import type { FileMutationResult } from "@shared/ipc/explorer";
import { createDesktopFileActions, createDesktopFileSource } from "@renderer/features/explorer/adapters/fileSource";
import { readSessionStrip, useExplorer, treeKey } from "@renderer/state/explorer";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn(), dismiss: vi.fn() }) }));

beforeEach(() => {
  vi.useFakeTimers();
  useExplorer.setState({ sessionId: "file-source-owner", projectId: "p", ready: true, root: null, tabs: [], activeId: null, trees: {}, fsRevision: 0, changedPaths: [], changedEntries: [] });
});
afterEach(() => { vi.runOnlyPendingTimers(); vi.useRealTimers(); vi.restoreAllMocks(); });
const source = () => createDesktopFileSource({ sessionId: "file-source-owner", projectId: "p", projectName: "project", root: null });
const signal = () => new AbortController().signal;
const row = (path: string) => ({ path, name: path.split("/").pop()!, kind: "file" as const, size: 0, modifiedAt: 0, symlink: false });

test("reads reject cancellation, while an already committed rename reconciles every tab and cached subtree", async () => {
  const files = source(), controller = new AbortController();
  const own = useExplorer.getState().openFile("old/deep/note.txt", null)!;
  const sibling = useExplorer.getState().openFile("old/sibling.txt", null)!;
  const otherRoot = useExplorer.getState().openFile("old/deep/note.txt", "/worktree")!;
  useExplorer.getState().setTreeOpen(null, () => new Set(["", "old", "old/deep"]));
  useExplorer.getState().setTreeListing(null, "old/deep", [row("old/deep/note.txt")]);
  let finish!: (result: FileMutationResult) => void;
  vi.mocked(window.textToCad.explorer.rename).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = files.rename!("old", { name: "new", signal: controller.signal });
  controller.abort();
  finish({ status: "committed", path: "new", change: { kind: "moved", previousPath: "old", path: "new", directory: true, mutationId: "move-1" } });
  expect(await pending).toMatchObject({ status: "committed", change: { kind: "moved", from: "old", to: "new" } });
  const state = useExplorer.getState();
  expect(state.tabs.find(tab => tab.id === own.id)).toMatchObject({ path: "new/deep/note.txt" });
  expect(state.tabs.find(tab => tab.id === sibling.id)).toMatchObject({ path: "new/sibling.txt" });
  expect(state.tabs.find(tab => tab.id === otherRoot.id)).toMatchObject({ path: "old/deep/note.txt" });
  expect(state.trees[treeKey(null)]!.listings["new/deep"]).toEqual([row("new/deep/note.txt")]);
  expect([...state.trees[treeKey(null)]!.open]).toEqual(["", "new", "new/deep"]);
  await expect(files.list!("", { signal: controller.signal })).rejects.toMatchObject({ name: "AbortError" });
});

test("duplicate mutation broadcasts are idempotent and late receipts cannot alter a different project", async () => {
  const files = source();
  const receipt: FileMutationResult = { status: "committed", path: "new", change: { kind: "moved", previousPath: "old", path: "new", directory: true, mutationId: "move-2" } };
  useExplorer.getState().receiveChanges("p", null, [receipt.change]);
  const replacement = useExplorer.getState().openFile("old/newly-created.txt")!;
  vi.mocked(window.textToCad.explorer.rename).mockResolvedValueOnce(receipt);
  await files.rename!("old", { name: "new", signal: signal() });
  expect(useExplorer.getState().tabs.find(tab => tab.id === replacement.id)).toMatchObject({ path: "old/newly-created.txt" });
  useExplorer.setState({ projectId: "another" });
  vi.mocked(window.textToCad.explorer.rename).mockResolvedValueOnce({ ...receipt, change: { ...receipt.change, mutationId: "late-other-project" } });
  await files.rename!("old", { name: "new", signal: signal() });
  expect(useExplorer.getState().tabs.find(tab => tab.id === replacement.id)).toMatchObject({ path: "old/newly-created.txt" });
});

test("write conflict semantics are typed and subscription leases stay balanced", async () => {
  const files = source();
  vi.mocked(window.textToCad.explorer.writeText).mockResolvedValueOnce({ status: "conflict", message: "any locale", actualRevision: "r2" });
  expect(await files.writeText!("note", { content: "draft", expectedRevision: "r1", signal: signal() })).toEqual({ status: "conflict", message: "any locale", actualRevision: "r2" });
  const changes: FileChanges[] = [];
  const watch = vi.mocked(window.textToCad.explorer.watch).mockClear();
  const unwatch = vi.mocked(window.textToCad.explorer.unwatch).mockClear();
  const off1 = files.subscribe!(change => changes.push(change)), off2 = files.subscribe!(() => {});
  useExplorer.getState().receiveChanges("p", null, [{ kind: "changed", path: "ignored.unknown", directory: false, revision: "r2" }]);
  expect(changes).toEqual([{ sourceId: files.id, changes: [{ kind: "content", path: "ignored.unknown", revision: "r2" }] }]);
  off1(); expect(unwatch).not.toHaveBeenCalled(); off2();
  expect(watch).toHaveBeenCalledTimes(1); expect(unwatch).toHaveBeenCalledTimes(1);
});

test("a tab gives back the files it opened when it leaves, follows their moves, and holds them again on a remount", async () => {
  const files = source();
  const stat = (path: string) => ({ path, name: path, kind: "file" as const, size: 1, modifiedAt: 0, symlink: false, fileKind: "text" as const, mime: "text/plain", extension: "txt" });
  vi.mocked(window.textToCad.explorer.stat).mockResolvedValueOnce(stat("a.txt")).mockResolvedValueOnce(stat("b.txt"));
  await files.stat("a.txt", { signal: signal() });
  await files.stat("b.txt", { signal: signal() });
  const watch = vi.mocked(window.textToCad.explorer.watch).mockClear();
  const unwatch = vi.mocked(window.textToCad.explorer.unwatch).mockClear();
  const off = files.subscribe!(() => {});
  expect(watch).toHaveBeenLastCalledWith({ projectId: "p" });
  useExplorer.getState().receiveChanges("p", null, [{ kind: "moved", previousPath: "b.txt", path: "c.txt", directory: false }]);
  off();
  expect(unwatch).toHaveBeenLastCalledWith({ projectId: "p", paths: ["a.txt", "c.txt"] });
  const again = files.subscribe!(() => {});
  expect(watch).toHaveBeenLastCalledWith({ projectId: "p", paths: ["a.txt", "c.txt"] });
  again();
  expect(unwatch).toHaveBeenLastCalledWith({ projectId: "p", paths: ["a.txt", "c.txt"] });
});

test("a file restatted on every reload is given back once, however many times it was opened", async () => {
  const files = source();
  const stat = { path: "a.txt", name: "a.txt", kind: "file" as const, size: 1, modifiedAt: 0, symlink: false, fileKind: "text" as const, mime: "text/plain", extension: "txt" };
  vi.mocked(window.textToCad.explorer.stat).mockResolvedValue(stat);
  for (let index = 0; index < 10_001; index += 1) await files.stat("a.txt", { signal: signal() });
  const unwatch = vi.mocked(window.textToCad.explorer.unwatch).mockClear();
  files.subscribe!(() => {})();
  expect(unwatch.mock.calls[0]![0].paths!.length).toBeLessThanOrEqual(1);
});

test("only the first stat of a path is an open: main holds once, and one unwatch path gives it back", async () => {
  const files = source();
  const stat = { path: "a.txt", name: "a.txt", kind: "file" as const, size: 1, modifiedAt: 0, symlink: false, fileKind: "text" as const, mime: "text/plain", extension: "txt" };
  const statCall = vi.mocked(window.textToCad.explorer.stat).mockClear().mockResolvedValue(stat);
  for (let index = 0; index < 3; index += 1) await files.stat("a.txt", { signal: signal() });
  expect(statCall.mock.calls.filter(([request]) => request.intent === "open")).toHaveLength(1);
  const unwatch = vi.mocked(window.textToCad.explorer.unwatch).mockClear();
  files.subscribe!(() => {})();
  expect(unwatch).toHaveBeenCalledTimes(1);
  expect(unwatch.mock.calls[0]![0].paths).toEqual(["a.txt"]);
});

test("Copy reference preserves clipboard text and uses the injected draft destination", async () => {
  const deliver = vi.fn<PromptContextPort["deliver"]>(async () => ({ status: "added" as const, partIds: ["reference"] }));
  const writeText = vi.fn(async () => {});
  const files = source();
  const actions = createDesktopFileActions({ sessionId: "file-source-owner", projectId: "p", root: null, sourceId: files.id,
    clipboard: { writeText, readText: async () => "", writeImage: async () => {} },
    promptContext: { deliver, getSnapshot: () => ({ kind: "composer", available: true }), subscribe: () => () => {} } });
  let copied!: () => void;
  writeText.mockImplementationOnce(() => new Promise<void>(resolve => { copied = resolve; }));
  const copying = actions.perform!["copy-reference"]!({ path: "README.md", kind: "file" });
  expect(deliver.mock.calls[0]![0]).toMatchObject({ parts: [{ kind: "reference", reference: { resource: { kind: "workspace-file", workspaceId: files.id, path: "README.md" }, target: { kind: "whole-resource" } } }] });
  expect(writeText).toHaveBeenCalledWith("README.md");
  copied();
  await copying;
  writeText.mockClear();
  await actions.perform!["copy-relative-path"]!({ path: "README.md", kind: "file" });
  expect(writeText).toHaveBeenCalledWith("README.md");
  expect(deliver).toHaveBeenCalledTimes(1);
  expect("actions" in files).toBe(false);
});

test("managed binary leases keep workspace identity and bytes without extra metadata reads", async () => {
  const createObjectURL = vi.fn(() => "blob:fixture"), revokeObjectURL = vi.fn();
  const BaseURL = URL;
  vi.stubGlobal("URL", class extends BaseURL {
    static override createObjectURL = createObjectURL;
    static override revokeObjectURL = revokeObjectURL;
  });
  try {
    const stat = vi.mocked(window.textToCad.explorer.stat).mockClear();
    vi.mocked(window.textToCad.explorer.readBinary).mockResolvedValueOnce({ path: "images/sample.png", size: 3, mime: "image/png", dataUrl: "data:image/png;base64,AQID" });
    const files = source();
    const lease = await files.readAsset!("images/sample.png", { signal: signal() });
    expect(lease).toMatchObject({ url: "blob:fixture", mime: "image/png" });
    expect(lease.bytes).toEqual(new Uint8Array([1, 2, 3]));
    expect(stat).not.toHaveBeenCalled();
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    lease.release();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:fixture");
  } finally { vi.unstubAllGlobals(); }
});

test("a delayed file duplicate reveals only in its original session after switching within a directory", async () => {
  const files = source();
  let finish!: (result: FileMutationResult) => void;
  vi.mocked(window.textToCad.explorer.duplicate).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = files.duplicate!("part.step", { signal: signal() });
  await useExplorer.getState().bindSession("duplicate-other-session", "p", null);
  finish({ status: "committed", path: "part-copy.step", change: { kind: "added", path: "part-copy.step", directory: false } });
  expect(await pending).toMatchObject({ status: "committed" });
  expect((await readSessionStrip("file-source-owner")).reveal).toMatchObject({ path: "part-copy.step" });
  expect(useExplorer.getState().sessionId).toBe("duplicate-other-session");
  expect(useExplorer.getState().tabs).toEqual([]);
  expect(useExplorer.getState().reveal).toBeNull();
});

test("opening a terminal after async path resolution cannot target a different session", async () => {
  const files = source();
  const actions = createDesktopFileActions({ sessionId: "file-source-owner", projectId: "p", root: null, sourceId: files.id,
    clipboard: { writeText: async () => {}, readText: async () => "", writeImage: async () => {} },
    promptContext: { deliver: async () => ({ status: "added", partIds: [] }), getSnapshot: () => ({ kind: "composer", available: true }), subscribe: () => () => {} } });
  let finish!: (value: { path: string }) => void;
  vi.mocked(window.textToCad.explorer.absolutePath).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = actions.perform!["open-terminal"]!({ path: "src", kind: "directory" });
  await useExplorer.getState().bindSession("terminal-other-session", "p", null);
  finish({ path: "/workspace/src" });
  await pending;
  expect((await readSessionStrip("file-source-owner")).tabs).toEqual(expect.arrayContaining([expect.objectContaining({ sessionId: "file-source-owner", kind: "terminal", cwd: "/workspace/src" })]));
  expect(useExplorer.getState().sessionId).toBe("terminal-other-session");
  expect(useExplorer.getState().tabs).toEqual([]);
});

test("trashing a folder closes every tab under it, and names the one with unsaved changes that stayed open", async () => {
  const files = source();
  const dirty = useExplorer.getState().openFile("a/dirty.txt", null)!;
  const clean = useExplorer.getState().openFile("a/clean.txt", null)!;
  const elsewhere = useExplorer.getState().openFile("b/other.txt", null)!;
  desktopLiveDocuments(dirty.id, { projectId: "p", root: null }).documents!.drafts
    .put(JSON.stringify(["desktop", "p", null]), "a/dirty.txt", { base: { content: "x", revision: "r1" }, value: "unsaved", stale: false });
  vi.mocked(window.textToCad.explorer.trash).mockResolvedValueOnce({ status: "committed", path: "a", change: { kind: "removed", path: "a", directory: true, mutationId: "trash-1" } });
  await files.trash!("a", { signal: signal() });
  await vi.waitFor(() => expect(toast.error).toHaveBeenCalled());
  const ids = useExplorer.getState().tabs.map(tab => tab.id);
  expect(ids).not.toContain(clean.id);
  expect(ids).toContain(elsewhere.id);
  expect(vi.mocked(toast.error).mock.calls[0]![0]).toBe("Moved to Trash, but 1 open tab could not be closed: a/dirty.txt (Save or explicitly discard the document before closing its tab.)");
});

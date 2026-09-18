import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { PromptContextPort } from "@hardcore/core/prompt";
import type { FileChanges } from "@hardcore/ui/file-viewer";
import type { FileMutationResult } from "@shared/ipc/explorer";
import { createDesktopFileActions, createDesktopFileSource } from "@renderer/features/explorer/adapters/fileSource";
import { useExplorer, treeKey } from "@renderer/state/explorer";

beforeEach(() => {
  vi.useFakeTimers();
  useExplorer.setState({ projectId: "p", ready: true, root: null, tabs: [], activeId: null, trees: {}, fsRevision: 0, changedPaths: [], changedEntries: [] });
});
afterEach(() => { vi.runOnlyPendingTimers(); vi.useRealTimers(); vi.restoreAllMocks(); });
const source = () => createDesktopFileSource({ projectId: "p", projectName: "project", root: null });
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
  vi.mocked(window.hardcore.explorer.rename).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
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
  vi.mocked(window.hardcore.explorer.rename).mockResolvedValueOnce(receipt);
  await files.rename!("old", { name: "new", signal: signal() });
  expect(useExplorer.getState().tabs.find(tab => tab.id === replacement.id)).toMatchObject({ path: "old/newly-created.txt" });
  useExplorer.setState({ projectId: "another" });
  vi.mocked(window.hardcore.explorer.rename).mockResolvedValueOnce({ ...receipt, change: { ...receipt.change, mutationId: "late-other-project" } });
  await files.rename!("old", { name: "new", signal: signal() });
  expect(useExplorer.getState().tabs.find(tab => tab.id === replacement.id)).toMatchObject({ path: "old/newly-created.txt" });
});

test("write conflict semantics are typed and subscription leases stay balanced", async () => {
  const files = source();
  vi.mocked(window.hardcore.explorer.writeText).mockResolvedValueOnce({ status: "conflict", message: "any locale", actualRevision: "r2" });
  expect(await files.writeText!("note", { content: "draft", expectedRevision: "r1", signal: signal() })).toEqual({ status: "conflict", message: "any locale", actualRevision: "r2" });
  const changes: FileChanges[] = [];
  const watch = vi.mocked(window.hardcore.explorer.watch).mockClear();
  const unwatch = vi.mocked(window.hardcore.explorer.unwatch).mockClear();
  const off1 = files.subscribe!(change => changes.push(change)), off2 = files.subscribe!(() => {});
  useExplorer.getState().receiveChanges("p", null, [{ kind: "changed", path: "ignored.unknown", directory: false, revision: "r2" }]);
  expect(changes).toEqual([{ sourceId: files.id, changes: [{ kind: "content", path: "ignored.unknown", revision: "r2" }] }]);
  off1(); expect(unwatch).not.toHaveBeenCalled(); off2();
  expect(watch).toHaveBeenCalledTimes(1); expect(unwatch).toHaveBeenCalledTimes(1);
});

test("Copy reference preserves clipboard text and uses the injected draft destination", async () => {
  const deliver = vi.fn<PromptContextPort["deliver"]>(async () => ({ status: "added" as const, partIds: ["reference"] }));
  const writeText = vi.fn(async () => {});
  const files = source();
  const actions = createDesktopFileActions({ projectId: "p", root: null, sourceId: files.id,
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
    const stat = vi.mocked(window.hardcore.explorer.stat).mockClear();
    vi.mocked(window.hardcore.explorer.readBinary).mockResolvedValueOnce({ path: "images/sample.png", size: 3, mime: "image/png", dataUrl: "data:image/png;base64,AQID" });
    const files = source();
    const lease = await files.readAsset!("images/sample.png", { signal: signal() });
    expect(lease).toMatchObject({ url: "blob:fixture", byteLength: 3, resource: { kind: "workspace-file", workspaceId: files.id, path: "images/sample.png" } });
    expect(stat).not.toHaveBeenCalled();
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    lease.release();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:fixture");
  } finally { vi.unstubAllGlobals(); }
});

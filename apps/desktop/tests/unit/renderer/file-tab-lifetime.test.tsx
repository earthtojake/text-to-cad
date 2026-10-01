import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { FileTab, worktreeMark } from "@renderer/features/explorer/FileTab";
import { readSessionStrip, useExplorer } from "@renderer/state/explorer";
import { useProjects } from "@renderer/state/projects";
import { createDesktopFileSource } from "@renderer/features/explorer/adapters/fileSource";
import type { Project } from "@shared/types";

let delayedOpen: (() => void) | undefined;

vi.mock("@renderer/features/explorer/renderers", async () => {
  const { defineFileRenderer } = await import("@text-to-cad/ui/file-viewer");
  const renderers = [defineFileRenderer({
    id: "text-lifetime", priority: 0, matches: () => true,
    prepare: async ({ file, source, signal }) => ({ data: null, text: await source.readText!(file.path, { signal }) }),
    load: async () => ({ default: ({ document, source, onOpenFile }) => <>
      <p>{source.rootName}</p>
      <input aria-label="Draft" value={document?.value ?? ""} onChange={event => document?.setValue(event.target.value)} />
      <button onClick={() => void document?.save()}>Save</button>
      <button onClick={() => { delayedOpen = () => onOpenFile("later.txt", { target: "new" }); }}>Queue navigation</button>
    </> }),
  })];
  return { createDesktopRenderers: () => ({ renderers, dispose() {} }) };
});

const project: Project = { id: "rename-project", name: "Original project", path: "/tmp/rename-project", createdAt: 0 };
function stub(name: keyof typeof window.textToCad.explorer, implementation: unknown) {
  (window.textToCad.explorer as unknown as Record<string, unknown>)[name] = vi.fn(implementation as never);
}
beforeEach(() => {
  localStorage.clear();
  useProjects.setState({ projects: [project] });
  useExplorer.setState({ sessionId: "file-tab-owner", projectId: project.id, root: null, tabs: [], activeId: null, ready: true, trees: {}, panelWidth: 248 });
  stub("stat", async () => ({ path: "notes.txt", name: "notes.txt", kind: "file", fileKind: "text", extension: "txt", size: 8 }));
  stub("readText", async () => ({ content: "original", revision: "r1" }));
  stub("writeText", async ({ content }: { content: string }) => ({ status: "saved", document: { content, revision: "r2" } }));
  stub("list", async () => []);
  stub("watch", async () => ({}));
  stub("unwatch", async () => ({}));
});

it("preserves the dirty editor and its save revision when a project label changes", async () => {
  const tab = useExplorer.getState().open("file", { path: "notes.txt" })!;
  const props = { sessionId: "file-tab-owner", tabId: tab.id, project, root: null, path: "notes.txt", panel: null };
  const view = render(<FileTab {...props} />);
  const editor = await screen.findByRole("textbox", { name: "Draft" });
  fireEvent.change(editor, { target: { value: "unsaved draft" } });
  await screen.findByLabelText("Unsaved changes");
  useProjects.setState({ projects: [{ ...project, name: "Renamed project" }] });
  view.rerender(<FileTab {...props} project={{ ...project, name: "Renamed project" }} />);
  await screen.findByText("Renamed project");
  expect(editor).toHaveValue("unsaved draft");
  expect(window.textToCad.explorer.readText).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(window.textToCad.explorer.writeText).toHaveBeenCalledWith(expect.objectContaining({ content: "unsaved draft", expectedRevision: "r1" })));
  await waitFor(() => expect(screen.queryByLabelText("Unsaved changes")).not.toBeInTheDocument());
  // The explorer owns a debounced IPC write; finish it before jsdom is torn down.
  await waitFor(() => expect(window.textToCad.explorer.saveTabs).toHaveBeenCalledWith(
    expect.objectContaining({ sessionId: "file-tab-owner", tabs: expect.arrayContaining([expect.objectContaining({ path: "notes.txt" })]) }),
  ));
});

it("creates and releases an image asset without a data-URL network fetch", async () => {
  stub("readBinary", async () => ({ mime: "image/png", dataUrl: "data:image/png;base64,AQID" }));
  const originalFetch = globalThis.fetch;
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;
  const create = vi.fn((_blob: Blob) => "blob:managed-image");
  const revoke = vi.fn();
  try {
    globalThis.fetch = vi.fn(async () => { throw new Error("CSP blocks data: fetch"); });
    URL.createObjectURL = create;
    URL.revokeObjectURL = revoke;
    const source = createDesktopFileSource({ sessionId: "file-tab-owner", projectId: project.id, projectName: project.name, root: null });
    const asset = await source.readAsset!("image.png", { signal: new AbortController().signal });
    const blob = create.mock.calls[0]?.[0] as Blob;
    expect(blob.size).toBe(3);
    expect(blob.type).toBe("image/png");
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(asset.url).toBe("blob:managed-image");
    asset.release();
    expect(revoke).toHaveBeenCalledWith("blob:managed-image");
  } finally {
    globalThis.fetch = originalFetch;
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
  }
});

it("a retained file callback opens only its owner session after the user switches sessions", async () => {
  const tab = useExplorer.getState().open("file", { path: "notes.txt" })!;
  const view = render(<FileTab sessionId="file-tab-owner" tabId={tab.id} project={project} root={null} path="notes.txt" panel={null} />);
  fireEvent.click(await screen.findByRole("button", { name: "Queue navigation" }));
  view.unmount();
  await act(async () => { await useExplorer.getState().bindSession("other-file-owner", project.id, null); });
  expect(useExplorer.getState().tabs).toEqual([]);
  await act(async () => delayedOpen!());
  await waitFor(async () => expect((await readSessionStrip("file-tab-owner")).tabs).toEqual(expect.arrayContaining([expect.objectContaining({ path: "later.txt", sessionId: "file-tab-owner" })])));
  expect(useExplorer.getState().sessionId).toBe("other-file-owner");
  expect(useExplorer.getState().tabs).toEqual([]);
});

it("a worktree tab names its worktree before the crumbs, with its path as a hint rather than a native title", async () => {
  expect(worktreeMark("/home/me/.text-to-cad/worktrees/p/wrist")).toEqual({ label: "wrist", path: "/home/me/.text-to-cad/worktrees/p/wrist" });
  expect(worktreeMark("C:\\Users\\me\\.text-to-cad\\worktrees\\p\\wrist")?.label).toBe("wrist");
  expect(worktreeMark(null)).toBeNull();
  const tab = useExplorer.getState().open("file", { path: "notes.txt" })!;
  render(<FileTab sessionId="file-tab-owner" tabId={tab.id} project={project} root="/home/me/.text-to-cad/worktrees/p/wrist" path="notes.txt" panel={null} />);
  await screen.findByRole("textbox", { name: "Draft" });
  const mark = document.querySelector("[data-crumb=worktree]")!;
  expect(mark.textContent).toBe("wrist");
  expect(mark.getAttribute("title")).toBeNull();
  expect(mark.getAttribute("data-slot")).toBe("tooltip-trigger");
});

it("the watcher's echo of a save is not a change on disk: no reload, and no banner over later typing", async () => {
  const tab = useExplorer.getState().open("file", { path: "notes.txt" })!;
  render(<FileTab sessionId="file-tab-owner" tabId={tab.id} project={project} root={null} path="notes.txt" panel={null} />);
  const editor = await screen.findByRole("textbox", { name: "Draft" });
  fireEvent.change(editor, { target: { value: "saved text" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(screen.queryByLabelText("Unsaved changes")).not.toBeInTheDocument());
  // Main stamps the watcher's event with the revision of what is on disk —
  // the revision the save itself returned.
  const echo = () => act(() => useExplorer.getState().receiveChanges(project.id, null, [{ kind: "changed", path: "notes.txt", directory: false, revision: "r2" }]));
  echo();
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)); });
  expect(window.textToCad.explorer.readText).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("textbox", { name: "Draft" })).toBe(editor);
  fireEvent.change(editor, { target: { value: "saved text, then more" } });
  echo();
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)); });
  expect(screen.queryByText("This file changed on disk since you opened it.")).not.toBeInTheDocument();
  expect(editor).toHaveValue("saved text, then more");
  // Someone else's edit still is one.
  act(() => useExplorer.getState().receiveChanges(project.id, null, [{ kind: "changed", path: "notes.txt", directory: false, revision: "r3" }]));
  await screen.findByText("This file changed on disk since you opened it.");
  await waitFor(() => expect(window.textToCad.explorer.saveTabs).toHaveBeenCalled());
});

it("a file that opens read-only says why, in the tab rather than in a native title", async () => {
  for (const [document, reason, words] of [
    [{ content: "caf�", revision: "r1", readOnly: true }, "encoding", /not UTF-8/],
    [{ content: "the first 4 MB", revision: "r1", truncated: true }, "truncated", /too large to edit here/],
  ] as const) {
    stub("readText", async () => document);
    const tab = useExplorer.getState().open("file", { path: "notes.txt" })!;
    const view = render(<FileTab sessionId="file-tab-owner" tabId={tab.id} project={project} root={null} path="notes.txt" panel={null} />);
    await screen.findByRole("textbox", { name: "Draft" });
    const notice = await screen.findByText(words);
    expect(notice.closest("[role=status]")).toHaveAttribute("data-read-only-reason", reason);
    expect(notice.closest("[title]")).toBeNull();
    view.unmount();
  }
  stub("readText", async () => ({ content: "plain", revision: "r1" }));
  const tab = useExplorer.getState().open("file", { path: "notes.txt" })!;
  render(<FileTab sessionId="file-tab-owner" tabId={tab.id} project={project} root={null} path="notes.txt" panel={null} />);
  await screen.findByRole("textbox", { name: "Draft" });
  expect(document.querySelector("[data-read-only-reason]")).toBeNull();
  await waitFor(() => expect(window.textToCad.explorer.saveTabs).toHaveBeenCalled());
});

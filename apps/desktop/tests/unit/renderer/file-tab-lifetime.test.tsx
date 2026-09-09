import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { FileTab } from "@renderer/features/explorer/FileTab";
import { useExplorer } from "@renderer/state/explorer";
import { useProjects } from "@renderer/state/projects";
import { createDesktopFileSource } from "@renderer/features/explorer/adapters/fileSource";
import type { Project } from "@shared/types";

vi.mock("@renderer/features/explorer/renderers", async () => {
  const { defineFileRenderer } = await import("@hardcore/ui/file-viewer");
  const renderers = [defineFileRenderer({
    id: "text-lifetime", priority: 0, matches: () => true,
    prepare: async ({ file, source, signal }) => ({ data: null, text: await source.readText!(file.path, { signal }) }),
    load: async () => ({ default: ({ document, source }) => <>
      <p>{source.rootName}</p>
      <input aria-label="Draft" value={document?.value ?? ""} onChange={event => document?.setValue(event.target.value)} />
      <button onClick={() => void document?.save()}>Save</button>
    </> }),
  })];
  return { createDesktopRenderers: () => ({ renderers, dispose() {} }) };
});

const project: Project = { id: "rename-project", name: "Original project", path: "/tmp/rename-project", createdAt: 0 };
function stub(name: keyof typeof window.hardcore.explorer, implementation: unknown) {
  (window.hardcore.explorer as unknown as Record<string, unknown>)[name] = vi.fn(implementation as never);
}
beforeEach(() => {
  localStorage.clear();
  useProjects.setState({ projects: [project] });
  useExplorer.setState({ projectId: project.id, root: null, tabs: [], activeId: null, ready: true, trees: {}, panelWidth: 248 });
  stub("stat", async () => ({ path: "notes.txt", name: "notes.txt", kind: "file", fileKind: "text", extension: "txt", size: 8 }));
  stub("readText", async () => ({ content: "original", revision: "r1" }));
  stub("writeText", async ({ content }: { content: string }) => ({ content, revision: "r2" }));
  stub("list", async () => []);
  stub("watch", async () => ({}));
  stub("unwatch", async () => ({}));
});

it("preserves the dirty editor and its save revision when a project label changes", async () => {
  const tab = useExplorer.getState().open("file", { path: "notes.txt" })!;
  const props = { tabId: tab.id, project, root: null, path: "notes.txt", panel: null };
  const view = render(<FileTab {...props} />);
  const editor = await screen.findByRole("textbox", { name: "Draft" });
  fireEvent.change(editor, { target: { value: "unsaved draft" } });
  await screen.findByLabelText("Unsaved changes");
  useProjects.setState({ projects: [{ ...project, name: "Renamed project" }] });
  view.rerender(<FileTab {...props} project={{ ...project, name: "Renamed project" }} />);
  await screen.findByText("Renamed project");
  expect(editor).toHaveValue("unsaved draft");
  expect(window.hardcore.explorer.readText).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(window.hardcore.explorer.writeText).toHaveBeenCalledWith(expect.objectContaining({ content: "unsaved draft", expectedRevision: "r1" })));
  await waitFor(() => expect(screen.queryByLabelText("Unsaved changes")).not.toBeInTheDocument());
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
    const source = createDesktopFileSource({ projectId: project.id, projectName: project.name, root: null });
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

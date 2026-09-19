import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { toast } from "sonner";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { emptyDrawingDocument } from "@hardcore/core/drawing";
import type { DrawingEditorProps } from "@hardcore/ui/drawing";
import DrawingSurface from "@renderer/features/explorer/drawing/DrawingSurface";
import { getDrawingScene } from "@renderer/state/drawings";
import { useExplorer } from "@renderer/state/explorer";
import { useComposer } from "@renderer/state/composer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import type { Project, Session } from "@shared/types";

const editor = vi.hoisted(() => ({
  hasContent: true,
  controller: { serialize: vi.fn<() => string>(), exportPng: vi.fn<() => Promise<Blob>>() },
}));
vi.mock("@hardcore/ui/drawing", () => ({
  DrawingEditor: ({ onReady, onContentChange }: DrawingEditorProps) => {
    useEffect(() => {
      onReady(editor.controller);
      onContentChange?.(editor.hasContent);
      return () => onReady(null);
    }, [onReady, onContentChange]);
    return <div data-testid="drawing-editor" />;
  },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() } }));

const project: Project = { id: "sketch", path: "/sketch", name: "Sketch", createdAt: 0 };
const session = (id: string, projectId = project.id, cwd = project.path) => ({ id, projectId, cwd } as Session);
const png = () => new Blob([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])], { type: "image/png" });
const originalArrayBuffer = Object.getOwnPropertyDescriptor(Blob.prototype, "arrayBuffer");
let tabId: string;

beforeEach(() => {
  vi.clearAllMocks();
  editor.hasContent = true;
  editor.controller.serialize.mockReset().mockReturnValue(JSON.stringify(emptyDrawingDocument()));
  editor.controller.exportPng.mockReset().mockImplementation(async () => png());
  if (!Blob.prototype.arrayBuffer) Object.defineProperty(Blob.prototype, "arrayBuffer", { configurable: true, value: function(this: Blob) {
    return new Promise<ArrayBuffer>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as ArrayBuffer);
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(this);
    });
  } });
  useProjects.setState({ projects: [project, { ...project, id: "other", path: "/other" }], activeId: project.id });
  useSessions.setState({ sessions: [session("source"), session("other-chat", "other", "/other")], activeId: "source" });
  useComposer.setState({ drafts: {}, pendingFiles: {}, draftRoots: {}, acceptedContexts: {}, focusRequest: null, referenceLabels: {}, queues: {} });
  useExplorer.setState({ sessionId: "source", projectId: project.id, root: null, tabs: [], activeId: null, ready: true });
  tabId = useExplorer.getState().open("drawing")!.id;
});
afterEach(async () => {
  useExplorer.getState().discardSessionResources("source");
  await useExplorer.getState().bindSession(null, null);
  if (originalArrayBuffer) Object.defineProperty(Blob.prototype, "arrayBuffer", originalArrayBuffer);
  else Reflect.deleteProperty(Blob.prototype, "arrayBuffer");
});
const mount = () => render(<DrawingSurface sessionId="source" project={project} tabId={tabId} root={null} title="Bracket sketch" />);

it("binds the selected chat while encoding and attaches a PNG without navigating or submitting", async () => {
  let resolve!: (blob: Blob) => void;
  editor.controller.exportPng.mockImplementation(() => new Promise<Blob>(done => { resolve = done; }));
  const { unmount } = mount();
  fireEvent.click(screen.getByRole("button", { name: "Add to prompt" }));
  expect(editor.controller.exportPng).toHaveBeenCalledTimes(1);
  expect(useComposer.getState().pendingFiles).toEqual({});
  act(() => {
    useProjects.getState().setActive("other");
    useSessions.getState().setActive("other-chat");
  });
  resolve(png());
  await waitFor(() => expect(useComposer.getState().pendingFiles.source).toHaveLength(1));
  expect(useComposer.getState().pendingFiles.source?.[0]).toMatchObject({ name: "Bracket_sketch.png", type: "image/png" });
  expect(useComposer.getState().drafts.source).toContain("Drawing: Bracket sketch.");
  expect(useComposer.getState().drafts["other-chat"]).toBeUndefined();
  expect(useComposer.getState().queues).toEqual({});
  expect(useComposer.getState().focusRequest).toBeNull();
  expect(useProjects.getState().activeId).toBe("other");
  expect(useSessions.getState().activeId).toBe("other-chat");
  expect(toast.success).toHaveBeenCalledWith("Drawing added to prompt");
  unmount();
});

it("cancels delivery if its destination project is removed while encoding", async () => {
  let resolve!: (blob: Blob) => void;
  editor.controller.exportPng.mockImplementation(() => new Promise<Blob>(done => { resolve = done; }));
  const { unmount } = mount();
  fireEvent.click(screen.getByRole("button", { name: "Add to prompt" }));
  act(() => useSessions.getState().receive(useSessions.getState().sessions.filter(item => item.id !== "source")));
  resolve(png());
  await waitFor(() => expect(toast.error).toHaveBeenCalled());
  expect(useComposer.getState().pendingFiles).toEqual({});
  expect(useComposer.getState().drafts).toEqual({});
  unmount();
  expect(getDrawingScene(tabId)).toBeNull();
});

it("an empty drawing cannot be attached", () => {
  editor.hasContent = false;
  mount();
  expect(screen.getByRole("button", { name: "Add to prompt" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Save drawing copy" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Open drawing file" })).not.toBeInTheDocument();
  expect(editor.controller.exportPng).not.toHaveBeenCalled();
});

it("reports a failed PNG encoder and keeps the drawing available to retry", async () => {
  editor.controller.exportPng.mockRejectedValueOnce(new Error("Encoder failed"));
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Add to prompt" }));
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Encoder failed"));
  expect(screen.getByRole("button", { name: "Add to prompt" })).toBeEnabled();
  expect(useComposer.getState().drafts).toEqual({});
  expect(useComposer.getState().pendingFiles).toEqual({});
  fireEvent.click(screen.getByRole("button", { name: "Add to prompt" }));
  await waitFor(() => expect(useComposer.getState().pendingFiles.source).toHaveLength(1));
});

it("reports a synchronous capture failure and resets its pending state", async () => {
  editor.controller.exportPng.mockImplementationOnce(() => { throw new Error("Snapshot failed"); });
  mount();
  fireEvent.click(screen.getByRole("button", { name: "Add to prompt" }));
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Snapshot failed"));
  expect(screen.getByRole("button", { name: "Add to prompt" })).toBeEnabled();
  expect(useComposer.getState().pendingFiles).toEqual({});
});

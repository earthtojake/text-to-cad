import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { emptyDrawingDocument } from "@hardcore/core/drawing";
import { deleteDrawingScene, getDrawingScene, retainDrawingScene } from "@renderer/state/drawings";
import { useExplorer } from "@renderer/state/explorer";
import { useProjects } from "@renderer/state/projects";
import type { Project } from "@shared/types";

const tabId = "scene-lifecycle";
const document = (color: string) => JSON.stringify({ ...emptyDrawingDocument(), appState: { viewBackgroundColor: color } });

beforeEach(() => {
  vi.useFakeTimers();
  deleteDrawingScene(tabId);
  useExplorer.setState({ sessionId: "scene-project", projectId: "scene-project", tabs: [], activeId: null, ready: true, root: null });
});
afterEach(async () => {
  deleteDrawingScene(tabId);
  useExplorer.getState().discardSessionResources("scene-project");
  await useExplorer.getState().bindSession(null, null);
  await vi.runOnlyPendingTimersAsync();
  vi.useRealTimers();
});

it("reads the live scene on demand and freezes the last edit when its editor leaves", () => {
  let scene = document("#ffffff");
  const read = vi.fn(() => scene);
  const leave = retainDrawingScene(tabId, read);
  // Hundreds of edits retain a reader rather than repeatedly encoding JSON.
  for (let i = 0; i < 300; i++) scene = document(i % 2 ? "#000000" : "#ffffff");
  expect(read).not.toHaveBeenCalled();
  expect(getDrawingScene(tabId)).toBe(scene);
  scene = document("#abcdef");
  leave();
  expect(getDrawingScene(tabId)).toBe(scene);
  leave();
  expect(read).toHaveBeenCalledTimes(2);
});

it("closing a drawing releases content and ignores its editor's late unmount", () => {
  const drawing = useExplorer.getState().open("drawing")!;
  const read = vi.fn(() => document("#abcdef"));
  const leave = retainDrawingScene(drawing.id, read);
  useExplorer.getState().close(drawing.id);
  leave();
  expect(getDrawingScene(drawing.id)).toBeNull();
  expect(read).not.toHaveBeenCalled();
});

it("a stale editor cannot overwrite a replacement scene", () => {
  const oldRead = vi.fn(() => document("#abcdef"));
  const leave = retainDrawingScene(tabId, oldRead);
  retainDrawingScene(tabId, () => document("#123456"));
  leave();
  expect(JSON.parse(getDrawingScene(tabId)!).appState.viewBackgroundColor).toBe("#123456");
  expect(oldRead).not.toHaveBeenCalled();
});

it("disposing while a final snapshot is read cannot resurrect the drawing", () => {
  const leave = retainDrawingScene(tabId, () => {
    deleteDrawingScene(tabId);
    return document("#abcdef");
  });
  leave();
  expect(getDrawingScene(tabId)).toBeNull();
});

it("removing an inactive project disposes its drawings without reviving them on unmount", async () => {
  useProjects.setState({ projects: [{ id: "scene-project", path: "/scene" }, { id: "other", path: "/other" }] as Project[], activeId: "scene-project" });
  const drawing = useExplorer.getState().open("drawing")!;
  const leave = retainDrawingScene(drawing.id, () => document("#abcdef"));
  await useExplorer.getState().bindSession("other", "other");
  expect(getDrawingScene(drawing.id)).not.toBeNull();
  useExplorer.getState().discardSessionResources("scene-project");
  leave();
  expect(getDrawingScene(drawing.id)).toBeNull();
});

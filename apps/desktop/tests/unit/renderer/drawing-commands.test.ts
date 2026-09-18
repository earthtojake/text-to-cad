import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { emptyDrawingDocument } from "@hardcore/core/drawing";
import { performCadCommand } from "@renderer/state/cad-commands";
import { useExplorer } from "@renderer/state/explorer";
import { getDrawingScene, setDrawingScene } from "@renderer/state/drawings";
import { useProjects } from "@renderer/state/projects";
import { useUi } from "@renderer/state/ui";

let projectId: string;
let sequence = 0;
beforeEach(() => {
  vi.useFakeTimers();
  projectId = `drawing-project-${++sequence}`;
  useProjects.setState({ projects: [projectId, "other"].map(id => ({ id, name: id, path: `/projects/${id}`, createdAt: 0 })), activeId: projectId });
  useExplorer.setState({ projectId, root: null, tabs: [], activeId: null, ready: true });
  useUi.setState({ route: "app" });
});
afterEach(() => { vi.runOnlyPendingTimers(); vi.useRealTimers(); });

it("opens a normalized temporary canvas and describes its root and title", async () => {
  const root = "/worktrees/sketch";
  const result = await performCadCommand({ requestId: "r", kind: "open-drawing", projectId, root, title: "Plan" }) as { tabId: string };
  expect(getDrawingScene(result.tabId)).toBe(JSON.stringify(emptyDrawingDocument()));
  expect(await performCadCommand({ requestId: "r", kind: "list-tabs", projectId })).toMatchObject({
    active: result.tabId, tabs: [{ id: result.tabId, kind: "drawing", title: "Plan", root, ephemeral: true }],
  });
});

it("reads the latest background drawing without changing project, tab, root or Settings", async () => {
  const tab = useExplorer.getState().open("drawing", { root: "/worktrees/sketch", title: "Plan" })!;
  const scene = JSON.stringify({ ...emptyDrawingDocument(), appState: { viewBackgroundColor: "#ffeedd" } });
  setDrawingScene(tab.id, scene);
  await useExplorer.getState().bindProject("other");
  useProjects.getState().setActive("other");
  useUi.getState().openSettings();
  const active = useExplorer.getState().activeId;
  const root = useExplorer.getState().root;
  const result = await performCadCommand({ requestId: "r", kind: "drawing-scene", projectId, root: "/worktrees/sketch", tabId: tab.id });
  expect(result).toEqual({ scene });
  expect(useProjects.getState().activeId).toBe("other");
  expect(useExplorer.getState()).toMatchObject({ projectId: "other", activeId: active, root });
  expect(useUi.getState().route).toBe("settings");
});

it("refuses other projects, other roots and closed drawing tabs", async () => {
  const tab = useExplorer.getState().open("drawing", { root: "/worktrees/sketch" })!;
  const base = { requestId: "r", kind: "drawing-scene" as const, projectId, tabId: tab.id };
  await expect(performCadCommand({ ...base, root: null })).rejects.toThrow("another workspace root");
  await expect(performCadCommand({ ...base, projectId: "other", root: "/worktrees/sketch" })).rejects.toThrow("another project");
  useExplorer.getState().close(tab.id);
  await expect(performCadCommand({ ...base, root: "/worktrees/sketch" })).rejects.toThrow("closed");
});

it("invalid loaded JSON leaves no scratch tab behind", async () => {
  await expect(performCadCommand({ requestId: "r", kind: "open-drawing", projectId, scene: "{}" })).rejects.toThrow();
  expect(useExplorer.getState().tabs).toEqual([]);
});

/**
 * An agent's tool call, performed against the stores (plan §8).
 *
 * Main cannot open a tab: the strip is renderer state. So the Hardcore MCP
 * server's `open_file`, `reveal`, `open_url`, `list_open_tabs` and
 * `viewer_state` arrive here as `cad.command` events, are carried out on the
 * same stores a click would use, and the outcome goes back on `cad.reply`
 * (src/shared/ipc/cad.ts). Every command names its project; the explorer
 * switches to it before opening, the way clicking the project in the sidebar
 * would. Reading a drawing for an explicit save instead inspects its own
 * project's retained metadata without changing navigation.
 */
import { isCadFile } from "@hardcore/core/lib/fileFormats.js";
import { emptyDrawingDocument, MAX_DRAWING_BYTES, parseDrawingScene } from "@hardcore/core/drawing";
import { markdownRenderer } from "@hardcore/ui/renderers/markdown";
import type { CadCommand } from "@shared/ipc/cad";

import { getDrawingTab, hostOf, tabTitle, useExplorer } from "./explorer";
import { getDrawingScene, setDrawingScene } from "./drawings";
import { useProjects } from "./projects";
import { useUi } from "./ui";

function rendererIdForPath(path: string): "cad" | "markdown" | "code" {
  if (isCadFile(path)) return "cad";
  const name = path.split("/").at(-1) ?? path;
  const extension = name.includes(".") ? (name.split(".").at(-1) ?? "").toLowerCase() : "";
  return markdownRenderer.matches({ path, name, extension, kind: "file", size: 0, mediaType: "text" })
    ? "markdown"
    : "code";
}

/** Bring the explorer for `projectId` on screen and wait until its strip is bound. */
async function focusProject(projectId: string): Promise<void> {
  const projects = useProjects.getState();
  if (!projects.projects.some((project) => project.id === projectId)) {
    throw new Error("that project is no longer open in Hardcore");
  }
  if (projects.activeId !== projectId) {
    projects.setActive(projectId);
  }
  await useExplorer.getState().bindProject(projectId);
  useUi.getState().closeSettings();
  // An agent asking for a file is a reason to show the pane, not a preference
  // about it: `show` leaves the person's own choice for this project alone.
  useExplorer.getState().show();
}

function describeTabs() {
  const { tabs, activeId } = useExplorer.getState();
  return {
    active: activeId,
    tabs: tabs.map((tab) => ({
      id: tab.id,
      kind: tab.kind,
      title: tabTitle(tab),
      ...(tab.kind === "file" ? { path: tab.path, root: tab.root, renderer: tab.path ? rendererIdForPath(tab.path) : null } : {}),
      ...(tab.kind === "browser" ? { url: tab.url } : {}),
      ...(tab.kind === "terminal" ? { cwd: tab.cwd } : {}),
      ...(tab.kind === "review" ? { scope: tab.scope } : {}),
      ...(tab.kind === "drawing" ? { root: tab.root, ephemeral: true } : {}),
    })),
  };
}

export async function performCadCommand(command: CadCommand): Promise<unknown> {
  switch (command.kind) {
    case "open-file": {
      if (!command.path) {
        throw new Error("open-file needs a path");
      }
      await focusProject(command.projectId);
      // The session's root, not the explorer's: an agent in a worktree names
      // a file in that worktree whichever thread the person is looking at.
      const tab = useExplorer.getState().openFile(command.path, command.root ?? null);
      if (!tab) {
        throw new Error("the explorer could not open a tab");
      }
      return {
        opened: command.path,
        root: command.root ?? null,
        tabId: tab.id,
        renderer: rendererIdForPath(command.path),
        note:
          rendererIdForPath(command.path) === "cad"
            ? "Rendered by the CAD Viewer; the person can orbit, section and measure it there."
            : undefined,
      };
    }

    case "reveal": {
      if (!command.path) {
        throw new Error("reveal needs a path");
      }
      await focusProject(command.projectId);
      const root = command.root ?? null;
      useExplorer.getState().revealPath(command.path, command.directory ?? false, root);
      return { revealed: command.path, root };
    }

    case "open-url": {
      if (!command.url) {
        throw new Error("open-url needs a url");
      }
      await focusProject(command.projectId);
      const tab = useExplorer.getState().open("browser", { url: command.url });
      return { opened: command.url, tabId: tab?.id ?? null, title: hostOf(command.url) };
    }

    case "open-drawing": {
      // Validate before opening a tab so a bad file never leaves an empty tab.
      const scene = command.scene === undefined
        ? JSON.stringify(emptyDrawingDocument())
        : JSON.stringify(parseDrawingScene(command.scene));
      await focusProject(command.projectId);
      const tab = useExplorer.getState().open("drawing", { root: command.root ?? null, title: command.title ?? "Drawing" });
      if (!tab) throw new Error("the explorer could not open a drawing tab");
      setDrawingScene(tab.id, scene);
      return { tabId: tab.id, title: tabTitle(tab), root: command.root ?? null, ephemeral: true,
        ...(command.path ? { loaded: command.path } : {}) };
    }

    case "drawing-scene": {
      if (!command.tabId) throw new Error("drawing-scene needs a tabId");
      if (!useProjects.getState().projects.some(project => project.id === command.projectId)) {
        throw new Error("that project is no longer open in Hardcore");
      }
      const tab = getDrawingTab(command.tabId, command.projectId);
      if (!tab || tab.projectId !== command.projectId) throw new Error("that drawing tab is closed or belongs to another project");
      if (tab.root !== (command.root ?? null)) throw new Error("that drawing belongs to another workspace root");
      const serialized = getDrawingScene(tab.id) ?? JSON.stringify(emptyDrawingDocument());
      if (new TextEncoder().encode(serialized).byteLength > MAX_DRAWING_BYTES) {
        throw new Error("drawing scenes must be JSON no larger than 20 MiB");
      }
      return { scene: JSON.stringify(parseDrawingScene(serialized)) };
    }

    case "list-tabs":
      return describeTabs();

    case "viewer-state": {
      const { tabs, activeId } = useExplorer.getState();
      const active = tabs.find((tab) => tab.id === activeId) ?? null;
      const file = active?.kind === "file" ? active.path : null;
      const renderer = file ? rendererIdForPath(file) : null;
      return {
        file,
        root: active?.kind === "file" ? active.root : null,
        renderer,
        viewer: renderer === "cad",
        // The viewer surface keeps selection and camera to itself for now;
        // saying so is better than inventing values.
        selection: null,
        camera: null,
        activeTab: active ? { id: active.id, kind: active.kind, title: tabTitle(active) } : null,
      };
    }
  }
}

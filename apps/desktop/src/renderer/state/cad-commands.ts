/**
 * An agent's tool call, performed against the stores (plan §8).
 *
 * Main cannot open a tab: the strip is renderer state. So the Hardcore MCP
 * server's `open_file`, `reveal`, `open_url`, `list_open_tabs` and
 * `viewer_state` arrive here as `cad.command` events, are carried out on the
 * same stores a click would use, and the outcome goes back on `cad.reply`
 * (src/shared/ipc/cad.ts). Every command names its project; the explorer
 * switches to it first, the way clicking the project in the sidebar would,
 * because a tab opened into the wrong project's strip is a tab nobody sees.
 */
import { rendererForPath } from "@renderer/features/explorer/renderers/registry";
import type { CadCommand } from "@shared/ipc/cad";

import { hostOf, tabTitle, useExplorer } from "./explorer";
import { useProjects } from "./projects";
import { useUi } from "./ui";

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
      ...(tab.kind === "file" ? { path: tab.path, renderer: tab.path ? rendererForPath(tab.path).id : null } : {}),
      ...(tab.kind === "browser" ? { url: tab.url } : {}),
      ...(tab.kind === "terminal" ? { cwd: tab.cwd } : {}),
      ...(tab.kind === "review" ? { scope: tab.scope } : {}),
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
      const tab = useExplorer.getState().openFile(command.path);
      if (!tab) {
        throw new Error("the explorer could not open a tab");
      }
      return {
        opened: command.path,
        tabId: tab.id,
        renderer: rendererForPath(command.path).id,
        note:
          rendererForPath(command.path).id === "cad"
            ? "Rendered by the CAD Viewer; the person can orbit, section and measure it there."
            : undefined,
      };
    }

    case "reveal": {
      if (!command.path) {
        throw new Error("reveal needs a path");
      }
      await focusProject(command.projectId);
      const explorer = useExplorer.getState();
      // The tree lives in a file tab: make sure one is showing.
      const fileTab = explorer.tabs.find((tab) => tab.id === explorer.activeId && tab.kind === "file")
        ?? explorer.tabs.find((tab) => tab.kind === "file");
      if (fileTab) {
        explorer.setActive(fileTab.id);
      } else {
        explorer.open("file");
      }
      if (explorer.treeCollapsed) {
        explorer.setTreeCollapsed(false);
      }
      useExplorer.getState().setReveal({ path: command.path, directory: command.directory ?? false });
      return { revealed: command.path };
    }

    case "open-url": {
      if (!command.url) {
        throw new Error("open-url needs a url");
      }
      await focusProject(command.projectId);
      const tab = useExplorer.getState().open("browser", { url: command.url });
      return { opened: command.url, tabId: tab?.id ?? null, title: hostOf(command.url) };
    }

    case "list-tabs":
      return describeTabs();

    case "viewer-state": {
      const { tabs, activeId } = useExplorer.getState();
      const active = tabs.find((tab) => tab.id === activeId) ?? null;
      const file = active?.kind === "file" ? active.path : null;
      const renderer = file ? rendererForPath(file).id : null;
      return {
        file,
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

/** Authenticated integration commands. Background reads never change project or focus. */
import { isCadFile } from "@hardcore/core/lib/fileFormats.js";
import { emptyDrawingDocument, parseDrawingScene } from "@hardcore/core/drawing";
import { selectRenderer } from "@hardcore/ui/file-viewer";
import { rendererPlugins } from "@plugins/renderer";
import { imageResult } from "@plugins/results";
import { createDesktopRenderers } from "@renderer/features/explorer/renderers";
import type { IntegrationCommand } from "@shared/ipc/integrations";
import type { ExplorerTab } from "@shared/types";
import { readSessionStrip, renameDrawingTab, tabTitle, openSessionTab, closeSessionTab, selectSessionTab, revealSessionPath } from "./explorer";
import { getDrawingScene } from "./drawings";
import { useProjects } from "./projects";
import { useSessions } from "./sessions";
import { hasDirtyDocument, performDocumentCommand } from "./live-documents";
import { performCadViewerCommand } from "./live-cad";

async function rendererIdForPath(projectId: string, root: string | null, path: string, tabId: string) {
  const composition = createDesktopRenderers(projectId, root, tabId);
  try {
    const metadata = await window.hardcore.explorer.stat({ projectId, ...(root ? { root } : {}), path });
    return selectRenderer(composition.renderers, { ...metadata, mediaType: metadata.fileKind }).id;
  } catch { return null; } // Deleted or unavailable resources have no current renderer.
  finally { composition.dispose(); }
}

function inScope(tab: ExplorerTab, command: IntegrationCommand) {
  if (tab.sessionId !== command.sessionId || tab.projectId !== command.projectId) return false;
  if ("root" in tab) return tab.root === (command.root ?? null);
  if (tab.kind === "terminal") {
    const root = command.rootDirectory?.replace(/\\/g, "/").replace(/\/$/, "");
    const cwd = (tab.cwd ?? useProjects.getState().projects.find(project => project.id === tab.projectId)?.path)?.replace(/\\/g, "/").replace(/\/$/, "");
    return Boolean(root && cwd && (cwd === root || cwd.startsWith(`${root}/`)));
  }
  // Review tabs lack root identity; do not reveal a different worktree's review.
  if (tab.kind !== "review") return false;
  const session = useSessions.getState().sessions.find(candidate => candidate.id === tab.sessionId);
  const project = useProjects.getState().projects.find(candidate => candidate.id === command.projectId);
  return Boolean(session && session.cwd === (command.rootDirectory ?? project?.path));
}

async function scopedTabs(command: IntegrationCommand, signal?: AbortSignal) {
  signal?.throwIfAborted();
  if (!useProjects.getState().projects.some(project => project.id === command.projectId)) throw new Error("that project is no longer open in Hardcore");
  const session = useSessions.getState().sessions.find(session => session.id === command.sessionId && session.projectId === command.projectId && !session.archived);
  if (!session) throw new Error("This session is no longer active.");
  const strip = await readSessionStrip(command.sessionId);
  signal?.throwIfAborted();
  return { tabs: strip.tabs.filter(tab => inScope(tab, command)), activeId: strip.activeId };
}
async function scopedTab(command: IntegrationCommand, signal?: AbortSignal) {
  const strip = await scopedTabs(command, signal);
  signal?.throwIfAborted();
  const tab = strip.tabs.find(tab => tab.id === (command.tabId ?? strip.activeId));
  if (!tab) throw new Error("that tab is closed or belongs to another workspace");
  return tab;
}

export async function performIntegrationCommand(command: IntegrationCommand, signal?: AbortSignal): Promise<unknown> {
  signal?.throwIfAborted();
  const owner = useSessions.getState().sessions.find(session => session.id === command.sessionId && session.projectId === command.projectId && !session.archived);
  if (!owner) throw new Error("This session is no longer active.");
  const scope = { projectId: command.projectId, root: command.root ?? null };
  const params: Record<string, unknown> = { ...command.params, ...(command.tabId ? { tabId: command.tabId } : {}) };
  if (command.kind.startsWith("document-")) {
    const tab = await scopedTab(command, signal);
    signal?.throwIfAborted();
    if (tab.kind !== "file" || !tab.path) throw new Error("This is not a document tab.");
    return performDocumentCommand(command.kind, { ...params, tabId: tab.id }, { ...scope, path: tab.path });
  }
  const plugin = rendererPlugins.find(candidate => Object.values(candidate.manifest.commands).includes(command.kind));
  if (plugin) {
    const tab = await scopedTab(command, signal);
    signal?.throwIfAborted();
    if (tab.kind !== "file" || !tab.path) throw new Error(`This is not a ${plugin.manifest.name} tab.`);
    return plugin.perform(command.kind, { ...params, tabId: tab.id }, { ...scope, path: tab.path });
  }
  switch (command.kind) {
    case "open-file": {
      if (!command.path) throw new Error("open-file needs a path");
      const tab = await openSessionTab(command.sessionId, command.projectId, scope.root, "file", { path: command.path }, signal);
      if (!tab) throw new Error("the explorer could not open a tab");
      return { opened: command.path, root: scope.root, tabId: tab.id, renderer: await rendererIdForPath(command.projectId, scope.root, command.path, tab.id) };
    }
    case "reveal": {
      if (!command.path) throw new Error("reveal needs a path");
      await revealSessionPath(command.sessionId, command.projectId, scope.root, command.path, command.directory ?? false, signal);
      return { revealed: command.path, root: scope.root };
    }
    case "open-url": {
      if (!command.url) throw new Error("open-url needs a URL");
      const tab = await openSessionTab(command.sessionId, command.projectId, scope.root, "browser", { url: command.url, root: scope.root }, signal);
      if (!tab) throw new Error("the explorer could not open a browser tab");
      return { opened: command.url, tabId: tab.id, root: scope.root };
    }
    case "open-drawing": {
      const tab = await openSessionTab(command.sessionId, command.projectId, scope.root, "drawing", { root: scope.root, title: command.title ?? "Drawing" }, signal);
      if (!tab) throw new Error("the explorer could not open a drawing tab");
      return { tabId: tab.id, title: tabTitle(tab), root: scope.root, ephemeral: true };
    }
    case "drawing-rename": {
      const tab = await scopedTab(command, signal);
      signal?.throwIfAborted();
      if (tab.kind !== "drawing") throw new Error("this is not a drawing tab");
      renameDrawingTab(tab.id, tab.sessionId, command.title ?? "");
      return { tabId: tab.id, title: command.title!.trim(), root: tab.root };
    }
    case "drawing-state":
    case "drawing-capture": {
      const tab = await scopedTab(command, signal);
      signal?.throwIfAborted();
      if (tab.kind !== "drawing") throw new Error("this is not a drawing tab");
      const scene = getDrawingScene(tab.id) ?? JSON.stringify(emptyDrawingDocument());
      const document = parseDrawingScene(scene);
      const state = { tabId: tab.id, title: tab.title, root: tab.root, ephemeral: true, elementCount: document.elements.filter(element => !element.isDeleted).length };
      if (command.kind === "drawing-state") return state;
      const { exportDrawingScenePng } = await import("@hardcore/ui/drawing");
      signal?.throwIfAborted();
      return imageResult(await exportDrawingScenePng(scene), state);
    }
    case "list-tabs": {
      const { tabs, activeId } = await scopedTabs(command, signal);
      signal?.throwIfAborted();
      return { active: tabs.some(tab => tab.id === activeId) ? activeId : null,
        tabs: await Promise.all(tabs.map(async tab => ({ ...tab, title: tabTitle(tab), ...(tab.kind === "drawing" ? { ephemeral: true } : {}), ...(tab.kind === "file" ? { renderer: tab.path ? await rendererIdForPath(tab.projectId, tab.root, tab.path, tab.id) : null } : {}) }))) };
    }
    case "tab-resource": return scopedTab(command, signal);
    case "show-tab": {
      const tab = await scopedTab(command, signal);
      signal?.throwIfAborted();
      await selectSessionTab(command.sessionId, tab.id, signal, tab);
      return { tabId: tab.id, shown: true };
    }
    case "close-tab": {
      const tab = await scopedTab(command, signal);
      signal?.throwIfAborted();
      if (hasDirtyDocument(tab.id)) throw new Error("Save or explicitly discard the document before closing its tab.");
      // Close only this session’s strip; another session stays selected.
      await closeSessionTab(command.sessionId, tab.id, signal, tab);
      return { tabId: tab.id, closed: true };
    }
    case "terminal-open": {
      const tab = await openSessionTab(command.sessionId, command.projectId, scope.root, "terminal", { cwd: String(params.cwd ?? command.rootDirectory), ptyId: String(params.ptyId) }, signal);
      if (!tab) throw new Error("the explorer could not open a terminal tab");
      return { tabId: tab.id, ptyId: params.ptyId, cwd: params.cwd };
    }
    case "viewer-state":
    case "select-reference":
    case "cad-clear-selection":
    case "cad-camera":
    case "cad-reset-camera":
    case "cad-render-mode":
    case "capture-view": {
      const tab = await scopedTab(command, signal);
      signal?.throwIfAborted();
      if (tab.kind !== "file" || !tab.path || !isCadFile(tab.path)) throw new Error("this tab does not contain a CAD model");
      return performCadViewerCommand(command.kind, { ...params, tabId: tab.id }, { ...scope, path: tab.path });
    }
  }
}

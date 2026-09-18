/** Authenticated integration commands. Background reads never change project or focus. */
import { isCadFile } from "@hardcore/core/lib/fileFormats.js";
import { emptyDrawingDocument, parseDrawingScene } from "@hardcore/core/drawing";
import { selectRenderer } from "@hardcore/ui/file-viewer";
import { createDesktopRenderers } from "@renderer/features/explorer/renderers";
import type { IntegrationCommand } from "@shared/ipc/integrations";
import type { ExplorerTab } from "@shared/types";
import { readProjectStrip, renameDrawingTab, tabTitle, useExplorer } from "./explorer";
import { getDrawingScene } from "./drawings";
import { useProjects } from "./projects";
import { useSessions } from "./sessions";
import { useUi } from "./ui";
import { hasDirtyDocument, performDocumentCommand, performPdfCommand } from "./live-documents";
import { performCadViewerCommand } from "./live-cad";
import { explorerRootFor } from "./workspace-root";

async function rendererIdForPath(projectId: string, root: string | null, path: string, tabId: string) {
  const composition = createDesktopRenderers(projectId, root, tabId);
  try {
    const metadata = await window.hardcore.explorer.stat({ projectId, ...(root ? { root } : {}), path });
    return selectRenderer(composition.renderers, { ...metadata, mediaType: metadata.fileKind }).id;
  } catch { return null; } // Deleted or unavailable resources have no current renderer.
  finally { composition.dispose(); }
}

async function focusProject(projectId: string, signal?: AbortSignal) {
  signal?.throwIfAborted();
  const projects = useProjects.getState();
  if (!projects.projects.some(project => project.id === projectId)) throw new Error("that project is no longer open in Hardcore");
  const current = useExplorer.getState();
  const root = current.projectId === projectId ? current.root : explorerRootFor(projectId);
  if (projects.activeId !== projectId) projects.setActive(projectId);
  await useExplorer.getState().bindProject(projectId, root);
  signal?.throwIfAborted();
  const restored = useExplorer.getState();
  // bindProject quietly drops superseded loads. An older command must not act
  // against the new project's strip after the user (or another command) switches.
  if (useProjects.getState().activeId !== projectId || restored.projectId !== projectId || !restored.ready) {
    throw new Error("The active project changed while opening this tab. Try again in the intended project.");
  }
  useUi.getState().closeSettings();
  useExplorer.getState().show();
}

function inScope(tab: ExplorerTab, command: IntegrationCommand) {
  if (tab.projectId !== command.projectId) return false;
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
  return session ? session.cwd === (command.rootDirectory ?? project?.path) : tab.sessionId === null && (command.root ?? null) === null;
}

async function scopedTabs(command: IntegrationCommand, signal?: AbortSignal) {
  signal?.throwIfAborted();
  if (!useProjects.getState().projects.some(project => project.id === command.projectId)) throw new Error("that project is no longer open in Hardcore");
  const strip = await readProjectStrip(command.projectId);
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

/** Recheck identity after project restoration; closed/replaced tabs cannot be acted on. */
function currentTab(previous: ExplorerTab, command: IntegrationCommand) {
  const current = useExplorer.getState().tabs.find(tab => tab.id === previous.id);
  if (!current || !inScope(current, command) || current.kind !== previous.kind
    || (current.kind === "file" && previous.kind === "file" && current.path !== previous.path)
    || (current.kind === "terminal" && previous.kind === "terminal" && current.ptyId !== previous.ptyId)) {
    throw new Error("That tab closed or changed while the project was opening.");
  }
  return current;
}

async function imageResult(blob: Blob, metadata: Record<string, unknown>) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = ""; for (const byte of bytes) binary += String.fromCharCode(byte);
  return { ...metadata, mimeType: blob.type, base64: btoa(binary) };
}

export async function performIntegrationCommand(command: IntegrationCommand, signal?: AbortSignal): Promise<unknown> {
  signal?.throwIfAborted();
  const scope = { projectId: command.projectId, root: command.root ?? null };
  const params: Record<string, unknown> = { ...command.params, ...(command.tabId ? { tabId: command.tabId } : {}) };
  if (command.kind.startsWith("document-")) {
    const tab = await scopedTab(command, signal);
    signal?.throwIfAborted();
    if (tab.kind !== "file" || !tab.path) throw new Error("This is not a document tab.");
    return performDocumentCommand(command.kind, params, { ...scope, path: tab.path });
  }
  if (command.kind.startsWith("pdf-")) {
    const tab = await scopedTab(command, signal);
    signal?.throwIfAborted();
    if (tab.kind !== "file" || !tab.path) throw new Error("This is not a PDF tab.");
    return performPdfCommand(command.kind, params, { ...scope, path: tab.path });
  }
  switch (command.kind) {
    case "open-file": {
      if (!command.path) throw new Error("open-file needs a path");
      await focusProject(command.projectId, signal);
      signal?.throwIfAborted();
      const tab = useExplorer.getState().openFile(command.path, scope.root);
      if (!tab) throw new Error("the explorer could not open a tab");
      return { opened: command.path, root: scope.root, tabId: tab.id, renderer: await rendererIdForPath(command.projectId, scope.root, command.path, tab.id) };
    }
    case "reveal": {
      if (!command.path) throw new Error("reveal needs a path");
      await focusProject(command.projectId, signal);
      signal?.throwIfAborted();
      useExplorer.getState().revealPath(command.path, command.directory ?? false, scope.root);
      return { revealed: command.path, root: scope.root };
    }
    case "open-url": {
      if (!command.url) throw new Error("open-url needs a URL");
      await focusProject(command.projectId, signal);
      signal?.throwIfAborted();
      const tab = useExplorer.getState().open("browser", { url: command.url, root: scope.root });
      if (!tab) throw new Error("the explorer could not open a browser tab");
      return { opened: command.url, tabId: tab.id, root: scope.root };
    }
    case "open-drawing": {
      await focusProject(command.projectId, signal);
      signal?.throwIfAborted();
      const tab = useExplorer.getState().open("drawing", { root: scope.root, title: command.title ?? "Drawing" });
      if (!tab) throw new Error("the explorer could not open a drawing tab");
      return { tabId: tab.id, title: tabTitle(tab), root: scope.root, ephemeral: true };
    }
    case "drawing-rename": {
      const tab = await scopedTab(command, signal);
      signal?.throwIfAborted();
      if (tab.kind !== "drawing") throw new Error("this is not a drawing tab");
      renameDrawingTab(tab.id, tab.projectId, command.title ?? "");
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
      await focusProject(command.projectId, signal);
      signal?.throwIfAborted();
      currentTab(tab, command);
      useExplorer.getState().setActive(tab.id);
      return { tabId: tab.id, shown: true };
    }
    case "close-tab": {
      const tab = await scopedTab(command, signal);
      signal?.throwIfAborted();
      if (hasDirtyDocument(tab.id)) throw new Error("Save or explicitly discard the document before closing its tab.");
      // Close uses the ordinary UI path and its lifecycle policy; focus is explicit.
      await focusProject(command.projectId, signal);
      signal?.throwIfAborted();
      currentTab(tab, command);
      if (hasDirtyDocument(tab.id)) throw new Error("Save or explicitly discard the document before closing its tab.");
      useExplorer.getState().close(tab.id);
      return { tabId: tab.id, closed: true };
    }
    case "terminal-open": {
      await focusProject(command.projectId, signal);
      signal?.throwIfAborted();
      const tab = useExplorer.getState().open("terminal", { cwd: String(params.cwd ?? command.rootDirectory) });
      if (!tab) throw new Error("the explorer could not open a terminal tab");
      useExplorer.getState().update(tab.id, { ptyId: String(params.ptyId) });
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

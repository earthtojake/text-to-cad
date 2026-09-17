import type { FileViewerState, JsonValue } from "@hardcore/ui/file-viewer";
import { useCallback, useMemo, useState } from "react";
import { useExplorer, useTree } from "@renderer/state/explorer";
import type { ExplorerRoot } from "@shared/types";
import { migrateCadFileStates } from "./cadPersistence";
import { mergeChangedRecords } from "./statePatch";
export { mergeChangedRecords as mergeRendererState } from "./statePatch";

const KEY = "hardcore.fileViewer.v1";
type RendererStates = NonNullable<FileViewerState["renderers"]>;
function read(sourceId: string, rootPath: string): RendererStates {
  try {
    migrateCadFileStates(sourceId, rootPath, localStorage, sessionStorage);
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (!parsed || typeof parsed !== "object" || !(sourceId in parsed)) return {};
    const entry = (parsed as Record<string, unknown>)[sourceId];
    return entry && typeof entry === "object" && !Array.isArray(entry) ? entry as Record<string, JsonValue> : {};
  } catch { return {}; }
}
function write(sourceId: string, renderers: RendererStates) {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? "{}");
    const previous = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    localStorage.setItem(KEY, JSON.stringify({ ...previous, [sourceId]: renderers }));
  } catch { /* A blocked storage backend does not prevent opening or editing files. */ }
}

/** Keep existing panel/width/tree preferences; add one versioned root-scoped renderer record. */
export function useDesktopViewState(sourceId: string, tabId: string, root: ExplorerRoot, panel: string | null, rootPath: string) {
  const panelWidth = useExplorer((state) => state.panelWidth);
  const { open } = useTree(root);
  const [stored, setStored] = useState(() => ({ id: sourceId, renderers: read(sourceId, rootPath) }));
  const renderers = useMemo(() => stored.id === sourceId ? stored.renderers : read(sourceId, rootPath), [sourceId, rootPath, stored]);
  const state = useMemo<FileViewerState>(() => ({ panel, panelWidth, expandedDirectories: [...open], renderers }), [panel, panelWidth, open, renderers]);
  const onStateChange = useCallback((next: FileViewerState) => {
    const explorer = useExplorer.getState();
    const tab = explorer.tabs.find((candidate) => candidate.id === tabId);
    if (tab?.kind !== "file" || tab.root !== root) return;
    if (state.panel !== next.panel) explorer.update(tabId, { panel: next.panel });
    if (state.panelWidth !== next.panelWidth) explorer.setPanelWidth(next.panelWidth);
    if (next.expandedDirectories && JSON.stringify(state.expandedDirectories) !== JSON.stringify(next.expandedDirectories)) explorer.setTreeOpen(root, (previous) => {
      const expanded = new Set(next.expandedDirectories);
      return previous.size === expanded.size && [...previous].every((directory) => expanded.has(directory)) ? previous : expanded;
    });
    if (next.renderers !== renderers) {
      const value = mergeChangedRecords(read(sourceId, rootPath), renderers, next.renderers ?? {});
      setStored({ id: sourceId, renderers: value }); write(sourceId, value);
    }
  }, [sourceId, rootPath, root, tabId, renderers, state]);
  return { state, onStateChange };
}

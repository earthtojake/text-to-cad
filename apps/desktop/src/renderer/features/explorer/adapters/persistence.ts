import type { FileViewerState } from "@hardcore/ui/file-viewer";
import { useCallback, useMemo, useState } from "react";
import { useExplorer, useTree } from "@renderer/state/explorer";
import type { ExplorerRoot } from "@shared/types";
import { mergeChangedRecords } from "./statePatch";
import { readViewState as read, writeViewState as write, viewStateKey } from "./viewStateStore";
export { mergeChangedRecords as mergeRendererState } from "./statePatch";

/** Keep existing panel/width/tree preferences; add one versioned root-scoped renderer record. */
export function useDesktopViewState(sourceId: string, tabId: string, root: ExplorerRoot, panel: string | null) {
  // View choices belong to this persisted tab; immutable geometry caches still share resources.
  const stateKey = viewStateKey(sourceId, tabId);
  const panelWidth = useExplorer((state) => state.panelWidth);
  const { open } = useTree(root);
  const [stored, setStored] = useState(() => ({ id: stateKey, renderers: read(stateKey) }));
  const renderers = useMemo(() => stored.id === stateKey ? stored.renderers : read(stateKey), [stateKey, stored]);
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
      const value = mergeChangedRecords(read(stateKey), renderers, next.renderers ?? {});
      setStored({ id: stateKey, renderers: value }); write(stateKey, value);
    }
  }, [stateKey, root, tabId, renderers, state]);
  return { state, onStateChange };
}

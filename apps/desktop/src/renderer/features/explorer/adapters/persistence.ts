import type { FileViewerState } from "@text-to-cad/ui/file-viewer";
import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useExplorer, useTree } from "@renderer/state/explorer";
import type { ExplorerRoot } from "@shared/types";
import { desktopTabStore } from "./tabStore";

/**
 * `FileViewer`'s controlled state for one desktop tab: the explorer's chrome (the open panel from
 * the tab, the column's width from the window, the root's open folders from the tree) and the
 * tab's file views from its tab store.
 */
export function useDesktopViewState(sourceId: string, tabId: string, root: ExplorerRoot, panel: string | null) {
  const store = desktopTabStore(tabId);
  // Subscribe to the tab record so a write re-renders; `forRoot` is memoised per snapshot itself.
  useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const panelWidth = useExplorer((state) => state.panelWidth);
  const { open } = useTree(root);
  // View choices belong to this persisted tab; immutable geometry caches still share resources.
  const renderers = store.files.forRoot(sourceId);
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
    // Only what this view changed lands, so a stale view never overwrites another's entries.
    if (next.renderers !== renderers) store.files.merge(sourceId, renderers, next.renderers ?? {});
  }, [store, sourceId, root, tabId, renderers, state]);
  return { state, onStateChange };
}

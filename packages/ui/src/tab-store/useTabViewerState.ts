import { useCallback, useMemo, useState, useSyncExternalStore } from 'react';
import type { FileViewerState } from '../file-viewer/types.js';
import type { TabStore } from './tabStore.js';

/**
 * `FileViewer`'s controlled state for one root, from and into the tab store: the panel column's
 * width, the explorer's height cap and the root's open folders from `settings.fileTree`, the root's file views from
 * `files`, and the open panel — which is never stored: a page load, or a new tab, opens a file
 * on its own default (`panel: null`).
 */
export function useTabViewerState(store: TabStore, rootId: string): {
  state: FileViewerState;
  onStateChange: (next: FileViewerState) => void;
  setPanel: (panel: string | null) => void;
} {
  const record = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const [panel, setPanel] = useState<string | null>(null);
  const state = useMemo<FileViewerState>(() => ({
    panel,
    panelWidth: record.settings.fileTree.width,
    panelHeight: record.settings.fileTree.height,
    expandedDirectories: record.settings.fileTree.expanded[rootId] ?? [],
    renderers: store.files.forRoot(rootId),
  }), [record, panel, rootId, store]);
  const onStateChange = useCallback((next: FileViewerState) => {
    setPanel(next.panel);
    const { fileTree } = store.settings.getSnapshot();
    const expanded = next.expandedDirectories ? [...next.expandedDirectories] : fileTree.expanded[rootId] ?? [];
    // A root with nothing open has no entry: a tab that opened nothing is still at its defaults.
    const expandedByRoot = { ...fileTree.expanded };
    if (expanded.length) expandedByRoot[rootId] = expanded; else delete expandedByRoot[rootId];
    store.settings.update({ fileTree: { width: next.panelWidth, ...(next.panelHeight === undefined ? {} : { height: next.panelHeight }), expanded: expandedByRoot } });
    store.files.merge(rootId, store.files.forRoot(rootId), next.renderers ?? {});
  }, [store, rootId]);
  return { state, onStateChange, setPanel };
}

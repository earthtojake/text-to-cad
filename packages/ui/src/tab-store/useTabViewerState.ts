import { useCallback, useMemo, useState, useSyncExternalStore } from 'react';
import type { FileViewerState } from '../file-viewer/types.js';
import type { TabStore } from './tabStore.js';

/**
 * `FileViewer`'s controlled state, from and into the tab store: the panel column's width from
 * `settings`, the file views from `files`, and the open panel — which is never stored: a page
 * load, or a new tab, opens a file on its own default (`panel: null`).
 */
export function useTabViewerState(store: TabStore): {
  state: FileViewerState;
  onStateChange: (next: FileViewerState) => void;
  setPanel: (panel: string | null) => void;
} {
  const record = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const [panel, setPanel] = useState<string | null>(null);
  const state = useMemo<FileViewerState>(() => ({ panel, panelWidth: record.settings.panelWidth, renderers: store.files.all() }), [record, panel, store]);
  const onStateChange = useCallback((next: FileViewerState) => {
    setPanel(next.panel);
    store.settings.update({ panelWidth: next.panelWidth });
    store.files.merge(store.files.all(), next.renderers ?? {});
  }, [store]);
  return { state, onStateChange, setPanel };
}

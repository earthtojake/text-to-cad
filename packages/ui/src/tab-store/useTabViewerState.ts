import { useCallback, useMemo, useSyncExternalStore } from 'react';
import type { FileViewerState } from '../file-viewer/types.js';
import type { TabStore } from './tabStore.js';

/** `FileViewer`'s controlled state, from and into the tab store: the file views, from `files`. */
export function useTabViewerState(store: TabStore): {
  state: FileViewerState;
  onStateChange: (next: FileViewerState) => void;
} {
  const record = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const state = useMemo<FileViewerState>(() => ({ renderers: record.files }), [record]);
  const onStateChange = useCallback((next: FileViewerState) => {
    store.files.merge(store.files.all(), next.renderers ?? {});
  }, [store]);
  return { state, onStateChange };
}

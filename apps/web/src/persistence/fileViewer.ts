import { clampPanelWidth, PANEL_DEFAULT_WIDTH } from '@hardcore/ui/navigation';
import type { FileViewerState, JsonValue } from '@hardcore/ui/file-viewer';
import { mergeChangedRecords } from './statePatch';

const keyFor = (rootId: string) => `hardcore:file-viewer:v1:${encodeURIComponent(rootId)}`;
// A page load is a file opened directly (an address, a link): it opens with the file's own
// default panel, never with whichever panel the last page had open. So the open panel is
// not stored at all; its width and the tree's expanded folders are.
export function readViewState(rootId: string, storage: Storage = sessionStorage): FileViewerState {
  const defaults: FileViewerState = { panel: null, panelWidth: PANEL_DEFAULT_WIDTH, expandedDirectories: [] };
  try {
    const value = JSON.parse(storage.getItem(keyFor(rootId)) || 'null');
    if (!value || typeof value !== 'object' || Array.isArray(value)) return defaults;
    return {
      panel: null,
      panelWidth: Number.isFinite(value.panelWidth) ? clampPanelWidth(value.panelWidth) : defaults.panelWidth,
      expandedDirectories: Array.isArray(value.expandedDirectories) ? value.expandedDirectories.filter((v: unknown) => typeof v === 'string') : defaults.expandedDirectories,
      renderers: value.renderers && typeof value.renderers === 'object' && !Array.isArray(value.renderers) ? value.renderers : {},
    };
  } catch { return defaults; }
}
export function writeViewState(rootId: string, viewer: FileViewerState, storage: Storage = sessionStorage, baseline?: FileViewerState): void {
  try {
    if (!baseline) { storage.setItem(keyFor(rootId), JSON.stringify({ ...viewer, panel: null })); return; }
    const latest = readViewState(rootId, storage);
    const next = { ...latest };
    if (viewer.panelWidth !== baseline.panelWidth) next.panelWidth = viewer.panelWidth;
    if (JSON.stringify(viewer.expandedDirectories) !== JSON.stringify(baseline.expandedDirectories)) next.expandedDirectories = viewer.expandedDirectories;
    next.renderers = mergeChangedRecords(latest.renderers ?? {}, baseline.renderers ?? {}, viewer.renderers ?? {});
    storage.setItem(keyFor(rootId), JSON.stringify(next));
  } catch { /* Storage failure does not prevent viewing. */ }
}

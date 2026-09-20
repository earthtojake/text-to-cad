import { clampPanelWidth } from '@hardcore/ui/navigation';
import type { FileViewerState, JsonValue } from '@hardcore/ui/file-viewer';
import type { CadEntry } from '@hardcore/core/client';
import { readFileSessionState } from '@hardcore/ui/renderers/cad/state';
import { cadWorkspaceDefaultFileSheetWidthForViewport, readCadDirectorySessionState } from '../client/workbench/persistence.js';
import { mergeChangedRecords } from './statePatch';

const keyFor = (rootId: string) => `hardcore:file-viewer:v1:${encodeURIComponent(rootId)}`;
export function readViewState(rootId: string, storage: Storage = sessionStorage): FileViewerState {
  const defaultWidth = cadWorkspaceDefaultFileSheetWidthForViewport(window.innerWidth);
  const legacy = readCadDirectorySessionState({ storage, defaultFileSheetWidthPx: defaultWidth });
  const defaults: FileViewerState = {
    panel: legacy.fileViewerOpen === true ? 'tree' : legacy.fileSheetOpen === true ? 'cad-file-sheet'
      : legacy.fileViewerOpen === false && legacy.fileSheetOpen === false ? ''
        : legacy.fileSheetOpen === false || window.innerWidth < 520 ? 'tree' : null,
    panelWidth: clampPanelWidth(legacy.fileSheetWidthPx || defaultWidth),
    expandedDirectories: legacy.fileViewerExpandedDirectoryIds || [],
  };
  try {
    const value = JSON.parse(storage.getItem(keyFor(rootId)) || 'null');
    if (!value || typeof value !== 'object' || Array.isArray(value)) return defaults;
    return {
      panel: value.panel === 'cad-theme' ? null : value.panel === null || typeof value.panel === 'string' ? value.panel : defaults.panel,
      panelWidth: Number.isFinite(value.panelWidth) ? clampPanelWidth(value.panelWidth) : defaults.panelWidth,
      expandedDirectories: Array.isArray(value.expandedDirectories) ? value.expandedDirectories.filter((v: unknown) => typeof v === 'string') : defaults.expandedDirectories,
      renderers: value.renderers && typeof value.renderers === 'object' && !Array.isArray(value.renderers) ? value.renderers : {},
    };
  } catch { return defaults; }
}
export function writeViewState(rootId: string, viewer: FileViewerState, storage: Storage = sessionStorage, baseline?: FileViewerState): void {
  try {
    if (!baseline) { storage.setItem(keyFor(rootId), JSON.stringify(viewer)); return; }
    const latest = readViewState(rootId, storage);
    const next = { ...latest };
    if (viewer.panel !== baseline.panel) next.panel = viewer.panel;
    if (viewer.panelWidth !== baseline.panelWidth) next.panelWidth = viewer.panelWidth;
    if (JSON.stringify(viewer.expandedDirectories) !== JSON.stringify(baseline.expandedDirectories)) next.expandedDirectories = viewer.expandedDirectories;
    next.renderers = mergeChangedRecords(latest.renderers ?? {}, baseline.renderers ?? {}, viewer.renderers ?? {});
    storage.setItem(keyFor(rootId), JSON.stringify(next));
  } catch { /* Storage failure does not prevent viewing. */ }
}
/** Old web sessions used this origin's sessionStorage, with the default namespace. Only the `cad` renderer's files had one. */
export function restoreCadFileStates(state: FileViewerState, entries: CadEntry[], storage: Storage = sessionStorage): FileViewerState {
  const renderers = { ...state.renderers };
  let changed = false;
  for (const entry of entries) {
    if (/\.glb$/i.test(entry.file)) continue;
    const key = JSON.stringify([entry.rootRelativeFile || entry.file, 'cad']);
    if (key in renderers) continue;
    const session = readFileSessionState('', entry.file, entry, { storage });
    if (!session) continue;
    renderers[key] = { version: 1, fileSession: { ...session } } as JsonValue;
    changed = true;
  }
  return changed ? { ...state, renderers } : state;
}

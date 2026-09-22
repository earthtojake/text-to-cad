// What a host still needs of the STEP renderer's stored state: the directory session's storage
// key and the width of the panel column, which the host lays out.
//
// This module used to hold the per-tab snapshot schema as well — selection, expansion, hidden
// parts, the camera, the tool — normalized, cloned and compared field by field. The per-file
// record is the shell's now (`kit/shell/shellState.js`, with STEP's own slice in
// `stepSessionRecord.js`), so that schema had no reader left but its own test, and went with it.

export const CAD_DIRECTORY_SESSION_STORAGE_VERSION = 1;
export const CAD_DIRECTORY_SESSION_STORAGE_KEY = `cad-viewer:directory-session:v${CAD_DIRECTORY_SESSION_STORAGE_VERSION}`;

// The one breakpoint left of the old layout-mode module: between these widths the panel
// column takes the narrower default, because the pane beside it would otherwise have nothing
// left to show. Everything else that module carried described a mobile layout this viewer no
// longer has — the surface always laid out as desktop — and went with it.
const FILE_SHEET_COMPACT_MIN_PX = 520;
const FILE_SHEET_COMPACT_MAX_PX = 1024;

function isCompactFileSheetViewport(width) {
  const numeric = Number(width);
  return Number.isFinite(numeric) && numeric >= FILE_SHEET_COMPACT_MIN_PX && numeric < FILE_SHEET_COMPACT_MAX_PX;
}

export const CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH = 365;
export const CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH = 280;

function positiveInteger(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? Math.round(numeric) : null;
}

/** The sheet width worth storing, or null when it is the default (nothing to remember). */
export function fileSheetWidthPxForSessionState(value, defaultWidth = CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH) {
  const width = positiveInteger(value);
  const fallback = positiveInteger(defaultWidth) || positiveInteger(CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH);
  return !width || width === fallback ? null : width;
}

export function cadWorkspaceDefaultFileSheetWidthForViewport(width) {
  return isCompactFileSheetViewport(width)
    ? CAD_WORKSPACE_COMPACT_TAB_TOOLS_WIDTH
    : CAD_WORKSPACE_DEFAULT_TAB_TOOLS_WIDTH;
}

/**
 * How the CAD surface is laid out inside the explorer's pane.
 *
 * The viewer's own layout is measured against its root and drops into compact
 * mode — the file sheet as a drawer over the model — below 1024px. Every
 * explorer pane is narrower than that, so the desktop pins the desktop layout
 * (`layout="desktop"`, apps/viewer/docs/file-view.md) and sizes the sheet
 * itself from the pane: the sheet is a column beside the model at any width
 * the shell can give the pane, and the file tree gets out of the way when
 * there is not room for all three.
 */

/** The narrowest surface worth drawing a model and a sheet side by side in. */
export const CAD_SURFACE_MIN_WIDTH = 560;

/** The sheet's share of the pane, and where it stops growing. */
const SHEET_SHARE = 0.36;
const SHEET_MIN = 240;
const SHEET_MAX = 365;

/** The sheet's width for a surface `width` px wide; null before a measurement. */
export function cadSheetWidthFor(width: number): number | null {
  if (!Number.isFinite(width) || width <= 0) {
    return null;
  }
  return Math.round(Math.min(SHEET_MAX, Math.max(SHEET_MIN, width * SHEET_SHARE)));
}

/**
 * Whether a CAD tab should hide the file tree: the pane minus the tree is
 * narrower than a usable surface. `paneWidth` of zero means unmeasured, and
 * an unmeasured pane hides nothing.
 */
export function cadTabHidesTree(paneWidth: number, treeWidth: number): boolean {
  return paneWidth > 0 && paneWidth - treeWidth < CAD_SURFACE_MIN_WIDTH;
}

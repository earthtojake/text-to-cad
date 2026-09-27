// The panel column's range: the one place its width is bounded, read by the column that draws
// it (`FilePanelColumn.jsx`) and by the tab store that keeps the width a person dragged it to
// (`tab-store/tabRecord.ts`), which is why these numbers live apart from the component.
// Narrow by default: the model is the page. At the minimum a name truncates early; the column
// gives way before the viewer does.
export const PANEL_MIN_WIDTH = 140;
export const PANEL_MAX_WIDTH = 480;
export const PANEL_DEFAULT_WIDTH = 220;

/** Whatever a caller has, clamped into the column's range. */
export function clampPanelWidth(width) {
  const numeric = Number(width);
  if (!Number.isFinite(numeric)) {
    return PANEL_DEFAULT_WIDTH;
  }
  return Math.round(Math.max(PANEL_MIN_WIDTH, Math.min(PANEL_MAX_WIDTH, numeric)));
}

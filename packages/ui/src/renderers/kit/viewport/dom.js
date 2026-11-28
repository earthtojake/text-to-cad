export function isEditableTarget(target) {
  if (!(target instanceof Element)) {
    return false;
  }
  return !!target.closest("input, textarea, select, [contenteditable=''], [contenteditable='true'], [role='textbox']");
}

/** The page's primary pointer is coarse (a touch screen): read in one place, `lib/coarsePointer.js`. */
export { prefersCoarsePointer } from "../../../lib/coarsePointer.js";

/** How far a touch reaches a mark — ink, a measurement, the eraser's ring — about a fingertip; a cursor's is a few px. */
export const TOUCH_HIT_PX = 16;

/**
 * Whether a double-click on this canvas fits the view: only while Select is in hand, in every view, 2D
 * or 3D (`docs/viewer-ux.md`, "Selection and gestures": a double-click on empty space under Select). The view's one frame says
 * which tool is in hand on its root (`ViewFrame.jsx`'s `data-cad-selecting`); a canvas outside a frame,
 * which has no tools, fits.
 * @param {Element | null} element
 */
export function doubleClickFits(element) {
  const frame = element?.closest?.("[data-slot=cad-file-view]");
  return !frame || frame.hasAttribute("data-cad-selecting");
}

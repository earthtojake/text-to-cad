import { CHROME_INSET_PX, CORNER_INSET_PX } from "../../../lib/chromeInset.js";

// The chrome's inset from the viewer's edges: the gap between the tool strip and the stack under
// it, so the strip sits as far from the corner as the panels sit from the strip.
export const VIEWPORT_INSET_PX = CHROME_INSET_PX;
// One tool strip's height, shared by the toolbar and status row: 32px tiles in a 46px row, and its
// border (`FloatingToolBar.js`).
export const VIEWPORT_TOP_BAR_PX = 48;
// The cube, in the TOP-right corner, so the bottom row is Quick Edit's alone. A host whose own control floats over that
// corner lowers it clear by setting `--cad-viewport-corner-top`, the room that control takes from the top edge. Hosts can
// also choose the left corner with `--cad-viewport-corner-left` and `--cad-viewport-corner-right` (ViewPlaneControl),
// and a flat view's zoom follows it (`viewCornerLayout`); the default is the right.
// The cube's box is 6rem, the whole drawing (`ViewPlaneControl.js`'s 0–100 view box: the cube, its axes outside it and
// their letters, which never leave the box): it hugs the right edge (the host's corner variable, 2px unset), its top on
// the strip's, 8px down. The cube itself stands well inside its box: at rest its right edge is 22px from the view's and
// the Z letter's top 16px down, a little inside a flat view's zoom (`CORNER_INSET_PX`, 12px, from the right; 14px down).
export const VIEWPORT_CUBE_SIZE = "6rem";
export const VIEWPORT_CORNER_INSET_PX = 2;
export const VIEWPORT_CUBE_TOP_PX = CHROME_INSET_PX;
export const VIEWPORT_CUBE_TOP = `calc(${VIEWPORT_CUBE_TOP_PX}px + var(--cad-viewport-corner-top, 0px))`;
// Where the tool stack under the strip stops: 84px off the bottom, clear of Quick Edit's bar there.
export const VIEWPORT_STACK_BOTTOM = "84px";
// A flat view's zoom stands with its outer edge the corner's inset (`CORNER_INSET_PX`) in from the edge, measured as the
// cube's box is, from the host's corner variable, so a host that moves the corner moves the zoom with it.
const PILL_FROM_CORNER_PX = CORNER_INSET_PX - VIEWPORT_CORNER_INSET_PX;
// The tool strip's bar (`FloatingToolBar.js`: 28px tiles, 5px in, its 1px border), 8px from the view's top; the zoom,
// 28px tall (`ZoomControl.jsx`), stands on the strip's middle line.
export const STRIP_BAR_PX = 40;
export const ZOOM_CONTROL_PX = 28;
const ZOOM_TOP_PX = CHROME_INSET_PX + (STRIP_BAR_PX - ZOOM_CONTROL_PX) / 2;
const TOP = "var(--cad-viewport-corner-top, 0px)";

/**
 * Where the corner's control stands (`ViewCorner.jsx`), at the view's top-right: a 3D view's is the cube alone (its box
 * placed by the viewport, `VIEWPORT_CUBE_TOP`); a flat view's zoom (`pill`) has its outer edge the corner's inset (12px)
 * from the right edge, measured from the host's corner variable (`--cad-viewport-corner-right`, its 2px unset), and its
 * middle on the tool strip's; or, where the host anchors the corner at the left
 * (`--cad-viewport-corner-left`, `ViewPlaneControl`), mirrored there; lowered by `--cad-viewport-corner-top` either way.
 * `side`: "right" or "left" (`viewCornerSide`).
 * @returns {{ pill: object }}
 */
export function viewCornerLayout(side = "right") {
  const edge = side === "left" ? "var(--cad-viewport-corner-left, 0px)" : `var(--cad-viewport-corner-right, ${VIEWPORT_CORNER_INSET_PX}px)`;
  const at = offset => (side === "left" ? { left: `calc(${edge} + ${offset})`, right: "auto" } : { right: `calc(${edge} + ${offset})` });
  return {
    // A flat view's zoom, its corner's one control.
    pill: { ...at(`${PILL_FROM_CORNER_PX}px`), top: `calc(${ZOOM_TOP_PX}px + ${TOP})` }
  };
}

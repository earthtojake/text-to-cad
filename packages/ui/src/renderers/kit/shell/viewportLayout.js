import { CHROME_INSET_PX, CORNER_INSET_PX } from "../../../lib/chromeInset.js";

// The chrome's inset from the viewer's edges: the gap between the tool strip and the stack under
// it, so the strip sits as far from the corner as the panels sit from the strip.
export const VIEWPORT_INSET_PX = CHROME_INSET_PX;
// One tool strip's height, shared by the toolbar and status row: 24px tiles in a 32px row, and its
// border (`FloatingToolBar.js`).
export const VIEWPORT_TOP_BAR_PX = 34;
// The cube, in the bottom-right corner: its box hugs the right edge, and sits far enough off the
// bottom that the axes drawn in its lower corner never touch the viewer's edge. A host whose own
// control floats over that corner (a chat's button) lifts it clear by setting
// `--cad-viewport-corner-bottom`, the room that control takes from the bottom edge. Hosts can also
// choose the left corner with `--cad-viewport-corner-left` and `--cad-viewport-corner-right`
// (ViewPlaneControl), and the corner's pill follows it (`viewCornerLayout`); the default is the right.
export const VIEWPORT_CUBE_SIZE = "6rem";
export const VIEWPORT_CORNER_INSET_PX = 2;
export const VIEWPORT_CUBE_BOTTOM_PX = 8;
export const VIEWPORT_CUBE_BOTTOM = `calc(${VIEWPORT_CUBE_BOTTOM_PX}px + var(--cad-viewport-corner-bottom, 0px))`;
// Where the tool stack stops: an inset above the cube's line.
export const VIEWPORT_STACK_BOTTOM = `calc(${VIEWPORT_CUBE_SIZE} + ${VIEWPORT_CUBE_BOTTOM_PX + CHROME_INSET_PX}px)`;
// A flat view's zoom pill stands the corner's inset from the edges (`CORNER_INSET_PX`), measured as the cube's box is,
// from the host's corner variable, so a host that moves the corner moves the pill with it.
const PILL_FROM_CUBE_BOX_PX = CORNER_INSET_PX - VIEWPORT_CORNER_INSET_PX;

/**
 * Where the corner's control stands (`ViewCorner.jsx`): a flat view's zoom pill, at the bottom-right from the cube's
 * box (`--cad-viewport-corner-right`, its 2px unset), or, where the host anchors the cube at the bottom-left
 * (`--cad-viewport-corner-left`, `ViewPlaneControl`), mirrored there, from the box's left; lifted by
 * `--cad-viewport-corner-bottom` either way. `side`: "right" or "left" (`viewCornerSide`).
 * @returns {{ pill: object }}
 */
export function viewCornerLayout(side = "right") {
  const edge = side === "left" ? "var(--cad-viewport-corner-left, 0px)" : `var(--cad-viewport-corner-right, ${VIEWPORT_CORNER_INSET_PX}px)`;
  const at = offset => (side === "left" ? { left: `calc(${edge} + ${offset})`, right: "auto" } : { right: `calc(${edge} + ${offset})` });
  return {
    // A flat view's zoom pill, the one thing in its corner.
    pill: { ...at(`${PILL_FROM_CUBE_BOX_PX}px`), bottom: `calc(${CORNER_INSET_PX}px + var(--cad-viewport-corner-bottom, 0px))` }
  };
}

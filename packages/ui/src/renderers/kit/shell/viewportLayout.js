import { CHROME_INSET_PX, CORNER_INSET_PX } from "../../../lib/chromeInset.js";
import { cubeInkBox } from "../camera/ViewPlaneControl.js";
import { DEFAULT_VIEW_DIRECTION } from "../camera/viewportCameraKit.js";

// The chrome's inset from the viewer's edges: the gap between the tool strip and the stack under
// it, so the strip sits as far from the corner as the panels sit from the strip.
export const VIEWPORT_INSET_PX = CHROME_INSET_PX;
// One tool strip's height, shared by the toolbar and status row: 32px tiles in a 46px row, and its
// border (`FloatingToolBar.js`).
export const VIEWPORT_TOP_BAR_PX = 48;
// The cube, in the TOP-right corner, so the bottom row is Quick Edit's alone: its box hugs the right edge, 8px off the
// top, as the strip is. A host whose own control floats over that corner lifts the corner clear by setting
// `--cad-viewport-corner-top`, the room that control takes from the top edge. Hosts can also choose the left corner
// with `--cad-viewport-corner-left` and `--cad-viewport-corner-right` (ViewPlaneControl), and the corner's pill and
// stack follow it (`viewCornerLayout`); the default is the right.
// The cube's box is 68px, its drawing cropped to the cube (`ViewPlaneControl.js`), at the corner's 12px inset from the
// right and the top: the host's corner variable is its box's edge (2px unset), and 10px in from it (`CUBE_GUTTER_PX`).
export const VIEWPORT_CUBE_SIZE = "68px";
export const VIEWPORT_CUBE_PX = 68;
export const VIEWPORT_CORNER_INSET_PX = 2;
export const CUBE_GUTTER_PX = CORNER_INSET_PX - VIEWPORT_CORNER_INSET_PX;
export const VIEWPORT_CUBE_TOP_PX = CORNER_INSET_PX;
export const VIEWPORT_CUBE_TOP = `calc(${VIEWPORT_CUBE_TOP_PX}px + var(--cad-viewport-corner-top, 0px))`;
// Where the tool stack under the strip stops: clear of Quick Edit's bar at the view's bottom.
export const VIEWPORT_STACK_BOTTOM = `calc(${VIEWPORT_CUBE_SIZE} + ${2 * CHROME_INSET_PX}px)`;
// The gap between the cube's box and the corner's stack under it: what the cube draws (its axes and their labels, kept
// inside its box: `ViewPlaneControl.js`'s label clamp) ends just above the box's bottom, so 4px more is the stack's own gap.
export const CUBE_STACK_GAP_PX = 4;
// A flat view's zoom pill stands the corner's inset from the edges (`CORNER_INSET_PX`), measured as the cube's box is,
// from the host's corner variable, so a host that moves the corner moves the pill with it.
const PILL_FROM_CUBE_BOX_PX = CORNER_INSET_PX - VIEWPORT_CORNER_INSET_PX;
// The zoom's height: its row of bare 24px buttons (`ZoomControl.jsx`), drawn as the corner's stack is.
const ZOOM_PILL_PX = 24;
// Home, against the cube: 4px from the cube's drawing (not its box), at its left, top-aligned with its top face, as the
// cube is drawn from the view the file opens with (the camera's default direction), which Home goes back to. The cube's
// drawing is inset in its box (`ViewPlaneControl.js`'s `cubeInkBox`), so Home stands a little over the box's edge.
const HOME_FROM_CUBE_PX = 4;
export const HOME_BUTTON_PX = 24;
export const CUBE_HOME_INK = Object.freeze(cubeInkBox(DEFAULT_VIEW_DIRECTION, VIEWPORT_CUBE_PX));
// Home's outer edge from the cube's box's outer edge (its right, at the right), and its top under the box's.
export const CUBE_HOME_FROM_BOX_PX = Math.round(VIEWPORT_CUBE_PX - CUBE_HOME_INK.left + HOME_FROM_CUBE_PX);
export const CUBE_HOME_TOP_PX = Math.round(CUBE_HOME_INK.top);
// A flat view's camera Home stands beside its zoom pill, 4px from it.
const HOME_FROM_PILL_PX = 4;
// The zoom pill's width: −, the 40px percentage and + (`ZoomControl.jsx`).
const ZOOM_PILL_WIDTH_PX = 88;
const TOP = "var(--cad-viewport-corner-top, 0px)";

/**
 * Where the corner's controls stand (`ViewCorner.jsx`), at the view's top-right: a flat view's zoom pill, the corner's
 * inset (12px) from the right edge, measured from the cube's box (`--cad-viewport-corner-right`, its 2px unset), and from
 * the top; or, where the host anchors the cube at the left (`--cad-viewport-corner-left`, `ViewPlaneControl`), mirrored
 * there, from the box's left; lowered by `--cad-viewport-corner-top` either way. `side`: "right" or "left" (`viewCornerSide`).
 * The view's controls' stack (`ViewCornerStack.jsx`: Display, Projection, Home) stands at the same inset from that edge
 * as the pill, under the cube (`stack`: its box's top and size, and a 4px gap), or under a flat view's zoom pill
 * (`stackUnderPill`: the pill's inset and height, and the chrome's 8px), mirrored with it.
 * `home`: the cube's Home, against the cube's drawing on its inner side (its left; mirrored, its right), 4px from it and
 * level with its top face's top (`CUBE_HOME_INK`), so the two read as one.
 * @returns {{ pill: object, stack: object, stackUnderPill: object, home: object }}
 */
export function viewCornerLayout(side = "right") {
  const edge = side === "left" ? "var(--cad-viewport-corner-left, 0px)" : `var(--cad-viewport-corner-right, ${VIEWPORT_CORNER_INSET_PX}px)`;
  const at = offset => (side === "left" ? { left: `calc(${edge} + ${offset})`, right: "auto" } : { right: `calc(${edge} + ${offset})` });
  return {
    // A flat view's zoom pill, first in its corner.
    pill: { ...at(`${PILL_FROM_CUBE_BOX_PX}px`), top: `calc(${CORNER_INSET_PX}px + ${TOP})` },
    // Under the cube: its box's top, its size and the gap.
    stack: { ...at(`${PILL_FROM_CUBE_BOX_PX}px`), top: `calc(${VIEWPORT_CUBE_TOP_PX + CUBE_STACK_GAP_PX}px + ${VIEWPORT_CUBE_SIZE} + ${TOP})` },
    // Under a flat view's zoom pill: its inset, its height, then the chrome's 8px.
    stackUnderPill: { ...at(`${PILL_FROM_CUBE_BOX_PX}px`), top: `calc(${CORNER_INSET_PX + ZOOM_PILL_PX + CHROME_INSET_PX}px + ${TOP})` },
    // Home, against the cube's drawing, never over it.
    home: { ...at(`${PILL_FROM_CUBE_BOX_PX + CUBE_HOME_FROM_BOX_PX}px`), top: `calc(${VIEWPORT_CUBE_TOP_PX + CUBE_HOME_TOP_PX}px + ${TOP})` },
    // A flat view's camera Home (a board's in 3D), beside its zoom pill, as the cube's beside the cube.
    pillHome: { ...at(`${PILL_FROM_CUBE_BOX_PX + ZOOM_PILL_WIDTH_PX + HOME_FROM_PILL_PX}px`), top: `calc(${CORNER_INSET_PX}px + ${TOP})` }
  };
}

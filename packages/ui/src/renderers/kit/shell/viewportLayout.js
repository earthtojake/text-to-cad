import { CHROME_INSET_PX } from "../../../lib/chromeInset.js";

// The chrome's inset from the viewer's edges: the gap between the tool strip and the stack under
// it, so the strip sits as far from the corner as the panels sit from the strip.
export const VIEWPORT_INSET_PX = CHROME_INSET_PX;
// One tool strip's height, shared by the toolbar and status row: 24px tiles in a 32px row, and its
// border (`FloatingToolBar.js`).
export const VIEWPORT_TOP_BAR_PX = 34;
// The cube, in the bottom-right corner, its drawing (the cube, its axes and their labels) 8px from both
// edges, as every corner control stands: its box is wider and taller than the drawing, so the box
// overhangs the right edge (its right is negative) and sits 2px off the bottom. A host whose own
// control floats over that corner (a chat's button) lifts it clear by setting
// `--cad-viewport-corner-bottom`, the room that control takes from the bottom edge. Hosts can also
// choose the left corner with `--cad-viewport-corner-left` and `--cad-viewport-corner-right`
// (ViewPlaneControl), and every corner control follows it (`viewCornerLayout`); the default is the right.
export const VIEWPORT_CUBE_SIZE = "6rem";
export const VIEWPORT_CORNER_INSET_PX = -6;
export const VIEWPORT_CUBE_BOTTOM_PX = 2;
export const VIEWPORT_CUBE_BOTTOM = `calc(${VIEWPORT_CUBE_BOTTOM_PX}px + var(--cad-viewport-corner-bottom, 0px))`;
// Where the tool stack stops: an inset above the cube's line.
export const VIEWPORT_STACK_BOTTOM = `calc(${VIEWPORT_CUBE_SIZE} + ${VIEWPORT_CUBE_BOTTOM_PX + CHROME_INSET_PX}px)`;
// The cube's drawing inside its box: its right face's edge stands this far in from the box's right,
// its top vertex this far down from the box's top (the box is wider and taller for its axis labels).
export const VIEWPORT_CUBE_FACE_RIGHT_PX = 20;
export const VIEWPORT_CUBE_FACE_TOP_PX = 19;
// The gap between the view corner's controls. Over the cube the lowest stands on the top of the cube's
// box, not on the cube: the cube turns with the camera and may reach almost to its box's top, so only
// the box keeps the gap under the column clear at every angle. Over the pill, which never turns, the
// lowest stands this gap above it.
export const VIEWPORT_CORNER_GAP_PX = 6;
// The corner's controls (`ViewCorner.jsx`): the strip's 24px tiles 4px inside their box and 4px apart
// (`tools/stripTouch.js`), so a one-button toolbar is 32px square, without the strip's border.
export const VIEWPORT_CORNER_TILE_PX = 24;
export const VIEWPORT_CORNER_PAD_PX = 4;
export const VIEWPORT_CORNER_CONTROL_PX = VIEWPORT_CORNER_TILE_PX + 2 * VIEWPORT_CORNER_PAD_PX;
// The pill (`ZoomControl.jsx`'s): −, the 48px percentage and +, 32px tall and 112px wide.
export const VIEWPORT_PILL_PX = VIEWPORT_CORNER_CONTROL_PX;
// The corner's controls stand off the cube's box, wherever the host anchors it: the cube's right (or
// left) face 20px inside its box, the pill's outer edge where the cube's drawing ends (14px inside it).
// At the default bottom-right, whose box overhangs the edge by 6px, those are 14px and 8px from the
// right edge. A column stands over its anchor flush with the anchor's outer edge, its controls a gap
// apart: a 3D view's over the cube on the box's top, a flat view's over the pill a gap above it (the
// pill 8px off the bottom, its 32px, then the gap: 46px), so a view that draws its picture flat or in 3D
// keeps one corner, and not one control moves when it switches.
// The cube's drawing, its axes' labels included, ends this far inside its box.
const CORNER_PILL_PX = 14;
const CORNER_BOTTOM = `calc(${VIEWPORT_INSET_PX}px + var(--cad-viewport-corner-bottom, 0px))`;
const PILL_COLUMN_BOTTOM = `calc(${VIEWPORT_INSET_PX + VIEWPORT_PILL_PX + VIEWPORT_CORNER_GAP_PX}px + var(--cad-viewport-corner-bottom, 0px))`;

/**
 * Where the corner's controls stand (`ViewCorner.jsx`): at the bottom-right, from the cube's box
 * (`--cad-viewport-corner-right`, the box's right, -6px unset), or, where the host anchors the cube at
 * the bottom-left (`--cad-viewport-corner-left`, `ViewPlaneControl`), mirrored there as one group, from
 * the box's left; lifted by `--cad-viewport-corner-bottom` either way. `side`: "right" or "left"
 * (`viewCornerSide`).
 * @returns {{ cubeColumn: object, pill: object, pillColumn: object }}
 */
export function viewCornerLayout(side = "right") {
  const edge = side === "left" ? "var(--cad-viewport-corner-left, 0px)" : `var(--cad-viewport-corner-right, ${VIEWPORT_CORNER_INSET_PX}px)`;
  const at = px => (side === "left" ? { left: `calc(${edge} + ${px}px)`, right: "auto" } : { right: `calc(${edge} + ${px}px)` });
  return {
    // A 3D view's column over the cube: flush with the cube's outer face, on its box's top.
    cubeColumn: { ...at(VIEWPORT_CUBE_FACE_RIGHT_PX), bottom: `calc(${VIEWPORT_CUBE_BOTTOM} + ${VIEWPORT_CUBE_SIZE})` },
    // A flat view's zoom pill, where the cube would stand, lifted as the cube is.
    pill: { ...at(CORNER_PILL_PX), bottom: CORNER_BOTTOM },
    // A flat view's column over the pill: flush with the pill's outer edge, a gap above it.
    pillColumn: { ...at(CORNER_PILL_PX), bottom: PILL_COLUMN_BOTTOM }
  };
}

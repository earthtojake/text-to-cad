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
// The gap between the view corner's controls. The lowest stands on the top of the cube's box, not
// on the cube: the cube turns with the camera and may reach almost to its box's top, so only the box
// keeps the gap under the column clear at every angle.
export const VIEWPORT_CORNER_GAP_PX = 6;
// The corner's controls (`ViewCorner.jsx`): the strip's 24px tiles 4px inside their box and 4px apart
// (`tools/stripTouch.js`), so a one-button toolbar is 32px square, without the strip's border.
export const VIEWPORT_CORNER_TILE_PX = 24;
export const VIEWPORT_CORNER_PAD_PX = 4;
export const VIEWPORT_CORNER_CONTROL_PX = VIEWPORT_CORNER_TILE_PX + 2 * VIEWPORT_CORNER_PAD_PX;
// The pill (`ZoomControl.jsx`'s): −, the 48px percentage and +, 32px tall and 112px wide, and the column over it.
const PILL_PERCENT_PX = 48;
export const VIEWPORT_PILL_PX = VIEWPORT_CORNER_CONTROL_PX;
// Its two tiles and the percentage, the box's 4px either end and the 4px either side of the percentage.
export const VIEWPORT_PILL_WIDTH_PX = 2 * VIEWPORT_CORNER_TILE_PX + PILL_PERCENT_PX + 4 * VIEWPORT_CORNER_PAD_PX;
// The corner's controls stand off the cube's box, wherever the host anchors it: the cube's right (or
// left) face 20px inside its box, the pill's outer edge where the cube's drawing ends (14px inside it),
// and the bottom row a gap past the pill (its 112px), 132px from the box's edge. At the default
// bottom-right, whose box overhangs the edge by 6px, those are 14px, 8px and 126px from the right edge.
// The cube's box ends 90px from the right edge (96px wide), so the row clears it by 36px and stands where
// it stands whether the pill or the cube is in the corner; its controls are the pill's height, so their
// bottoms are the pill's.
// The cube's drawing, its axes' labels included, ends this far inside its box.
const CORNER_PILL_PX = 14;
const CORNER_ROW_PX = CORNER_PILL_PX + VIEWPORT_PILL_WIDTH_PX + VIEWPORT_CORNER_GAP_PX;
const CORNER_BOTTOM = `calc(${VIEWPORT_INSET_PX}px + var(--cad-viewport-corner-bottom, 0px))`;

/**
 * Where the corner's controls stand (`ViewCorner.jsx`): at the bottom-right, from the cube's box
 * (`--cad-viewport-corner-right`, the box's right, -6px unset), or, where the host anchors the cube at
 * the bottom-left (`--cad-viewport-corner-left`, `ViewPlaneControl`), mirrored there as one group, from
 * the box's left; lifted by `--cad-viewport-corner-bottom` either way. `side`: "right" or "left"
 * (`viewCornerSide`).
 * @returns {{ cubeColumn: object, pill: object, row: object }}
 */
export function viewCornerLayout(side = "right") {
  const edge = side === "left" ? "var(--cad-viewport-corner-left, 0px)" : `var(--cad-viewport-corner-right, ${VIEWPORT_CORNER_INSET_PX}px)`;
  const at = px => (side === "left" ? { left: `calc(${edge} + ${px}px)`, right: "auto" } : { right: `calc(${edge} + ${px}px)` });
  return {
    // A 3D view's column over the cube: flush with the cube's outer face, on its box's top.
    cubeColumn: { ...at(VIEWPORT_CUBE_FACE_RIGHT_PX), bottom: `calc(${VIEWPORT_CUBE_BOTTOM} + ${VIEWPORT_CUBE_SIZE})` },
    // A flat view's zoom pill, where the cube would stand, lifted as the cube is.
    pill: { ...at(CORNER_PILL_PX), bottom: CORNER_BOTTOM },
    // The bottom row, past the pill: read from the corner outwards, so mirrored it runs the other way.
    row: { ...at(CORNER_ROW_PX), bottom: CORNER_BOTTOM, flexDirection: side === "left" ? "row-reverse" : "row" }
  };
}

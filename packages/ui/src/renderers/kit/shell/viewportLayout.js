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
// (ViewPlaneControl); the default remains the right.
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
// The gap between the view corner's round buttons. The lowest stands on the top of the cube's box, not
// on the cube: the cube turns with the camera and may reach almost to its box's top, so only the box
// keeps the gap under the column clear at every angle.
export const VIEWPORT_CORNER_GAP_PX = 6;
// A 3D view's corner column (`ViewCorner.jsx`): flush with the cube's right face, on its box's top.
export const VIEWPORT_CUBE_COLUMN_POSITION = Object.freeze({
  right: `calc(var(--cad-viewport-corner-right, ${VIEWPORT_CORNER_INSET_PX}px) + ${VIEWPORT_CUBE_FACE_RIGHT_PX}px)`,
  bottom: `calc(${VIEWPORT_CUBE_BOTTOM} + ${VIEWPORT_CUBE_SIZE})`
});
// A flat view's corner: its zoom pill where the cube would stand, at the inset, lifted as the cube is.
export const VIEWPORT_PILL_POSITION = Object.freeze({
  right: `${VIEWPORT_INSET_PX}px`, bottom: `calc(${VIEWPORT_INSET_PX}px + var(--cad-viewport-corner-bottom, 0px))`
});
// The 28px pill (`ZoomControl.jsx`'s), 104px wide, and the column over it.
export const VIEWPORT_PILL_PX = 28;
export const VIEWPORT_PILL_WIDTH_PX = 104;
// The corner's bottom row (`ViewCorner.jsx`'s `ViewCornerRow`): left of the pill, a gap from it, on its
// line. The cube's box ends 90px from the right edge (96px wide, overhanging it by 6), so the row clears
// it by 28px and stands where it stands whether the pill or the cube is in the corner.
export const VIEWPORT_CORNER_ROW_POSITION = Object.freeze({
  right: `${VIEWPORT_INSET_PX + VIEWPORT_PILL_WIDTH_PX + VIEWPORT_CORNER_GAP_PX}px`,
  bottom: `calc(${VIEWPORT_INSET_PX}px + var(--cad-viewport-corner-bottom, 0px))`
});
export const VIEWPORT_PILL_COLUMN_POSITION = Object.freeze({
  right: `${VIEWPORT_INSET_PX}px`, bottom: `calc(${VIEWPORT_INSET_PX + VIEWPORT_PILL_PX + VIEWPORT_CORNER_GAP_PX}px + var(--cad-viewport-corner-bottom, 0px))`
});

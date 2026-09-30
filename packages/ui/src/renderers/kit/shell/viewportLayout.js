import { CHROME_INSET_PX } from "../../../lib/chromeInset.js";

// The line preview's playbars centre on. A host whose own control floats over the view's bottom
// edge (a chat's composer) lines them up with it by setting `--cad-viewport-bottom-center`.
export const VIEWPORT_BOTTOM_CENTER = "var(--cad-viewport-bottom-center, 3.5rem)";

// The chrome's inset from the viewer's edges: the gap between the tool strip and the stack under
// it, so the strip sits as far from the corner as the panels sit from the strip — and where the
// file explorer floats over the view.
export const VIEWPORT_INSET_PX = CHROME_INSET_PX;
// One tool strip's height, shared by the toolbar and status row.
export const VIEWPORT_TOP_BAR_PX = 34;
// The cube, in the bottom-left corner, and the row of view actions on top of it (Display
// settings, Reset view, Preview) share a width, so their centres line up.
export const VIEWPORT_CUBE_SIZE = "6rem";
export const VIEWPORT_CORNER_INSET_PX = 2;
export const VIEWPORT_ACTION_HEIGHT_PX = 24;
// Where the tool stack stops: an inset above the cube and its actions in the bottom-left corner.
export const VIEWPORT_STACK_BOTTOM = `calc(${VIEWPORT_CUBE_SIZE} + ${VIEWPORT_ACTION_HEIGHT_PX + VIEWPORT_CORNER_INSET_PX * 2 + CHROME_INSET_PX}px)`;

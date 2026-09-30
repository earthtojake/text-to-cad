// Stable bottom-action center, independent of cube orientation and dimensions. A host whose own
// control floats over the view's bottom edge (a chat's composer) lines the bottom action and the
// playback bars up with it by setting `--cad-viewport-bottom-center`.
export const VIEWPORT_BOTTOM_CENTER = "var(--cad-viewport-bottom-center, 3.5rem)";

// The chrome's inset from the viewer's edges: the gap between the tool strip and the stack under
// it, so the strip sits as far from the corner as the panels sit from the strip.
export const VIEWPORT_INSET_PX = 8;
// One tool strip's height, shared by the toolbar and status row.
export const VIEWPORT_TOP_BAR_PX = 34;
// The cube and the action row below it share a width, so their centres line up.
export const VIEWPORT_CUBE_SIZE = "6rem";
export const VIEWPORT_CORNER_INSET_PX = 2;
export const VIEWPORT_ACTION_HEIGHT_PX = 24;

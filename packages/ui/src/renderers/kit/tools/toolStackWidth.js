// The tool stack's one width: every panel under the strip is drawn at it (`RendererShell.jsx`),
// and one handle on the stack's right edge moves it for all of them together. It is a viewing
// preference of the person's, not of a file: the host keeps it (`CadPreferences.toolStackWidth`)
// and it holds across files. Importing this module has no environmental effects.

// The default: the strip of the fullest tool set with one tool a file adds when
// it has something for it — seven tools (Select, Draw, Measure, two kept effects, a joint tool and
// Display), each a 24px button (`size-6`, `primitives/toolbar-button.jsx`), 2px apart (`gap-0.5`),
// inside 4px of padding (`p-1`) and a 1px border (`FloatingToolBar.js`): 190px.
const BASE_TOOLS = 7, BUTTON_PX = 24, GAP_PX = 2, PADDING_PX = 4, BORDER_PX = 1;
export const TOOL_STACK_DEFAULT_WIDTH = BASE_TOOLS * BUTTON_PX + (BASE_TOOLS - 1) * GAP_PX + 2 * PADDING_PX + 2 * BORDER_PX;
// The narrowest a person can make it: tree rows still show an icon and a few characters of their
// name beside their row actions, and Display's two-up controls still read (both truncate).
export const TOOL_STACK_MIN_WIDTH = 160;
export const TOOL_STACK_WIDTH_STORAGE_KEY = "cad-viewer:tool-stack-width:v1";
// A stored width is kept whatever the viewer it was chosen in; the widest any viewer draws it is
// half its own width (`clampToolStackWidth`), which leaves the model room.
const MAX_STORED_WIDTH = 1200;

/** A width the stack can be drawn at, from anything a store handed back: the default when it is no width. */
export function normalizeToolStackWidth(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.round(Math.min(MAX_STORED_WIDTH, Math.max(TOOL_STACK_MIN_WIDTH, value))) : TOOL_STACK_DEFAULT_WIDTH;
}

/** The width drawn in a viewer `viewerWidth` wide: never under the minimum, never over half the viewer. */
export function clampToolStackWidth(width, viewerWidth) {
  const widest = Math.max(TOOL_STACK_MIN_WIDTH, Math.floor(Number(viewerWidth) / 2) || TOOL_STACK_MIN_WIDTH);
  return Math.round(Math.min(widest, Math.max(TOOL_STACK_MIN_WIDTH, Number(width) || TOOL_STACK_MIN_WIDTH)));
}

export function readToolStackWidth(storage) {
  try { return normalizeToolStackWidth(JSON.parse(storage?.getItem(TOOL_STACK_WIDTH_STORAGE_KEY) || "null")); }
  catch { return TOOL_STACK_DEFAULT_WIDTH; }
}

export function writeToolStackWidth(storage, value) {
  try { storage?.setItem(TOOL_STACK_WIDTH_STORAGE_KEY, JSON.stringify(normalizeToolStackWidth(value))); }
  catch { /* A blocked preference store must not stop the stack resizing for this session. */ }
}

// The tool stack's layout, a viewing preference of the person's rather than of a file: the tab
// keeps it (`settings.toolStack` of the tab record) and it holds across files. Two things, and
// nothing else:
//
//   panels     for each panel a person can size (`ToolPanel.jsx`'s `resizable`: the tree and
//              Position), the width and the height cap they dragged it to, by panel id — only what
//              they set; a panel opens at its defaults otherwise (`TOOL_PANEL_WIDTH`, and
//              `toolPanelDefaultHeight`);
//   collapsed  which panels are folded to their first row, by panel id.
//
// Importing this module has no environmental effects.

// Every panel's width: a strip of six tools — each a 24px button (`size-6`,
// `primitives/toolbar-button.jsx`), 2px apart (`gap-0.5`), inside 4px of padding (`p-1`) and a
// 1px border (`FloatingToolBar.js`): 164px, whatever tools a file's own strip has. A fixed panel is
// exactly this wide; a resizable one opens this wide and is only ever made wider.
const STRIP_TOOLS = 6, BUTTON_PX = 24, GAP_PX = 2, PADDING_PX = 4, BORDER_PX = 1;
export const TOOL_PANEL_WIDTH = STRIP_TOOLS * BUTTON_PX + (STRIP_TOOLS - 1) * GAP_PX + 2 * PADDING_PX + 2 * BORDER_PX;
// The shortest a person can drag a panel's cap: its first row and a row of content under it.
export const TOOL_PANEL_MIN_HEIGHT = 64;
// The Reference's cap — a heading and a dozen compact rows, which a part's or a face's facts and
// its material fit without scrolling. It is not the person's: the Reference is a fixed panel.
export const TOOL_PANEL_REFERENCE_HEIGHT = 288;
// A stored size is kept whatever the viewer it was chosen in; what is drawn is bounded by the
// viewer at hand (`clampToolPanelWidth`, `clampToolPanelHeight`).
const MAX_STORED_PX = 4000;
// Panel ids are short words (`ToolPanel.jsx`'s `id`); a record full of anything else is not ours.
const PANEL_ID = /^[a-z][a-z0-9-]{0,31}$/;
const MAX_PANELS = 32;

export const DEFAULT_TOOL_STACK = Object.freeze({ panels: Object.freeze({}), collapsed: Object.freeze({}) });

const finite = value => typeof value === "number" && Number.isFinite(value);
const bounded = (value, floor) => finite(value) && value > 0 ? Math.round(Math.min(MAX_STORED_PX, Math.max(floor, value))) : undefined;
const record = value => value && typeof value === "object" && !Array.isArray(value) ? Object.entries(value).slice(0, MAX_PANELS) : [];

/**
 * The layout the stack is drawn with, from anything a store handed back: the sizes of the panels a
 * person has set (`{ width?, height? }` by id, each bounded; a panel with neither is absent), and
 * the panels whose folded state differs from nothing at all (`true` folded, `false` unfolded
 * against a panel that starts folded).
 * @returns {{ panels: Record<string, { width?: number, height?: number }>, collapsed: Record<string, boolean> }}
 */
export function normalizeToolStack(value) {
  const panels = {};
  for (const [id, size] of record(value?.panels)) {
    if (!PANEL_ID.test(id) || !size || typeof size !== "object") continue;
    const width = bounded(size.width, TOOL_PANEL_WIDTH), height = bounded(size.height, TOOL_PANEL_MIN_HEIGHT);
    if (width !== undefined || height !== undefined) panels[id] = { ...(width !== undefined ? { width } : {}), ...(height !== undefined ? { height } : {}) };
  }
  const collapsed = {};
  for (const [id, folded] of record(value?.collapsed)) if (PANEL_ID.test(id) && typeof folded === "boolean") collapsed[id] = folded;
  return { panels, collapsed };
}

/** A resizable panel's width in a viewer `viewerWidth` wide: never under `TOOL_PANEL_WIDTH`, never over half the viewer. */
export function clampToolPanelWidth(width, viewerWidth) {
  const widest = Math.max(TOOL_PANEL_WIDTH, Math.floor(Number(viewerWidth) / 2) || TOOL_PANEL_WIDTH);
  return Math.round(Math.min(widest, Math.max(TOOL_PANEL_WIDTH, Number(width) || TOOL_PANEL_WIDTH)));
}

/** A panel's cap in a stack `stackHeight` tall: never under the minimum, never over the stack. */
export function clampToolPanelHeight(height, stackHeight) {
  const tallest = Math.max(TOOL_PANEL_MIN_HEIGHT, Math.floor(Number(stackHeight)) || TOOL_PANEL_MIN_HEIGHT);
  return Math.round(Math.min(tallest, Math.max(TOOL_PANEL_MIN_HEIGHT, Number(height) || TOOL_PANEL_MIN_HEIGHT)));
}

/**
 * The cap a resizable panel opens with where a person has set none: the tree and Position, half
 * the stack's own height on desktop and all of it on a phone (where the tree starts folded, and
 * gives way to whatever joins it); anything else, the Reference's height.
 */
export function toolPanelDefaultHeight(key, stackHeight, mobile = false) {
  const height = Number(stackHeight) || 0;
  if (key === "tree" || key === "position") return Math.round(mobile ? height : height / 2) || TOOL_PANEL_REFERENCE_HEIGHT;
  return TOOL_PANEL_REFERENCE_HEIGHT;
}

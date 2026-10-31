// The tool stack's layout, a viewing preference of the person's rather than of a file: the tab
// keeps it (`settings.toolStack` of the tab record) and it holds across files. Two things, and
// nothing else (any other key a stored record carries is dropped):
//
//   panels     for each panel a person can size (`ToolPanel.jsx`'s `resizable`), the width and
//              the height cap they dragged it to, by panel id, and each file sidebar section's
//              panel (`fileSidebarSizeId`: `sidebar:<id>`) — only what they set; a panel opens at its
//              defaults otherwise (`TOOL_PANEL_WIDTH`, and `toolPanelDefaultHeight`: the stack's height);
//   collapsed  which panels and sidebar sections are folded to their first row, by id.
//
// Importing this module has no environmental effects.

// Every panel's width: a strip of six tools — each a 24px button (`size-6`,
// `primitives/toolbar-button.jsx`), 2px apart (`gap-0.5`), inside 4px of padding (`p-1`) and a
// 1px border (`FloatingToolBar.js`): 164px, whatever tools a file's own strip has. A fixed panel is
// exactly this wide; a resizable one opens this wide and is only ever made wider.
const STRIP_TOOLS = 6, BUTTON_PX = 24, GAP_PX = 2, PADDING_PX = 4, BORDER_PX = 1;
export const TOOL_PANEL_WIDTH = STRIP_TOOLS * BUTTON_PX + (STRIP_TOOLS - 1) * GAP_PX + 2 * PADDING_PX + 2 * BORDER_PX;
// The file sidebar (`FileSidebar.jsx`): its size kept under this id among the panels'; it opens a
// tool panel's width, as tall as its sections, and may be made narrower, down to room for a
// heading's name, its chevron and the bar's toggle (a tree's names truncate).
export const FILE_SIDEBAR_ID = "sidebar";
/** Where the sidebar keeps the size of one section's panel: each section is sized on its own. */
export function fileSidebarSizeId(sectionId) {
  return sectionId ? `${FILE_SIDEBAR_ID}:${sectionId}` : FILE_SIDEBAR_ID;
}
const isFileSidebarSize = id => id === FILE_SIDEBAR_ID || id.startsWith(`${FILE_SIDEBAR_ID}:`);
export const FILE_SIDEBAR_MIN_WIDTH = 120;
// The shortest a person can drag a panel's cap: its first row and a row of content under it.
export const TOOL_PANEL_MIN_HEIGHT = 64;
// A stored size is kept whatever the viewer it was chosen in; what is drawn is bounded by the
// viewer at hand (`clampToolPanelWidth`, `clampToolPanelHeight`).
const MAX_STORED_PX = 4000;
// Panel ids are short words (`ToolPanel.jsx`'s `id`), and a sidebar section's size is kept under
// `sidebar:<its id>` (`fileSidebarSizeId`); a record full of anything else is not ours.
const PANEL_ID = /^[a-z][a-z0-9-]{0,31}(?::[a-z][a-z0-9-]{0,31})?$/;
const MAX_PANELS = 32;

export const DEFAULT_TOOL_STACK = Object.freeze({ panels: Object.freeze({}), collapsed: Object.freeze({}) });

const finite = value => typeof value === "number" && Number.isFinite(value);
const bounded = (value, floor) => finite(value) && value > 0 ? Math.round(Math.min(MAX_STORED_PX, Math.max(floor, value))) : undefined;
const record = value => value && typeof value === "object" && !Array.isArray(value) ? Object.entries(value).slice(0, MAX_PANELS) : [];
const flags = value => {
  const kept = {};
  for (const [id, flag] of record(value)) if (PANEL_ID.test(id) && typeof flag === "boolean") kept[id] = flag;
  return kept;
};

/**
 * The layout the stack is drawn with, from anything a store handed back: the sizes of the panels a
 * person has set (`{ width?, height? }` by id, each bounded; a panel with neither is absent),
 * and the panels whose folded state differs from nothing at all (`true` folded, `false` unfolded
 * against a panel that starts folded).
 * @returns {{ panels: Record<string, { width?: number, height?: number }>, collapsed: Record<string, boolean> }}
 */
export function normalizeToolStack(value) {
  const panels = {};
  for (const [id, size] of record(value?.panels)) {
    if (!PANEL_ID.test(id) || !size || typeof size !== "object") continue;
    const width = bounded(size.width, isFileSidebarSize(id) ? FILE_SIDEBAR_MIN_WIDTH : TOOL_PANEL_WIDTH), height = bounded(size.height, TOOL_PANEL_MIN_HEIGHT);
    if (width !== undefined || height !== undefined) panels[id] = { ...(width !== undefined ? { width } : {}), ...(height !== undefined ? { height } : {}) };
  }
  return { panels, collapsed: flags(value?.collapsed) };
}

/**
 * A resizable panel's width in a viewer `viewerWidth` wide: never under `narrowest` (a tool panel's
 * width, unless the panel may be narrower), never over half the viewer.
 */
export function clampToolPanelWidth(width, viewerWidth, narrowest = TOOL_PANEL_WIDTH) {
  const widest = Math.max(TOOL_PANEL_WIDTH, Math.floor(Number(viewerWidth) / 2) || TOOL_PANEL_WIDTH);
  const wanted = Number(width);
  return Math.round(Math.min(widest, Math.max(narrowest, Number.isNaN(wanted) ? TOOL_PANEL_WIDTH : wanted)));
}

/** A panel's cap in a stack `stackHeight` tall: never under the minimum, never over the stack. */
export function clampToolPanelHeight(height, stackHeight) {
  const tallest = Math.max(TOOL_PANEL_MIN_HEIGHT, Math.floor(Number(stackHeight)) || TOOL_PANEL_MIN_HEIGHT);
  return Math.round(Math.min(tallest, Math.max(TOOL_PANEL_MIN_HEIGHT, Number(height) || TOOL_PANEL_MIN_HEIGHT)));
}

/**
 * The cap a resizable panel opens with where a person has set none, on a wide view and a phone alike:
 * the stack's own height. So it is as tall as its content needs, up to all the room under the
 * strip, and scrolls inside past that; with others open beside it, the panels share that room by
 * how each gives way (`ToolPanel.jsx`'s `fit`). None until the stack is measured.
 */
export function toolPanelDefaultHeight(stackHeight) {
  return Math.round(Number(stackHeight)) || null;
}

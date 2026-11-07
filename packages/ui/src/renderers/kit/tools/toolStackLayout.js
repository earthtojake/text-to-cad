// The tool stack's layout, a viewing preference of the person's rather than of a file: the tab
// keeps it (`settings.toolStack` of the tab record) and it holds across files. Two things (any
// other key a stored record carries is dropped):
//
//   panels     for each panel a person can size (`ToolPanel.jsx`'s `resizable`), the width and
//              the height cap they dragged it to, by panel id — only what they set; a panel opens
//              at its defaults otherwise (`TOOL_PANEL_WIDTH`, and `toolPanelDefaultHeight`: the
//              stack's height);
//   collapsed  which panels are folded to their first row, by id.
//
// The view's panel (`kit/shell/FlatPanel.jsx`) is the file's, not the tab's (`file-viewer/filePanel.js`).
// It was once kept here, for every file alike — `panels.flat`, `panels.flatDetail`, `collapsed.flat`
// and `tabs` (its tab by the kind of file) — and a record that still carries those keeps them, read
// as they always were, until the panel adopts them for a file and drops them; nothing writes them now.
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
// A stored size is kept whatever the viewer it was chosen in; what is drawn is bounded by the
// viewer at hand (`clampToolPanelWidth`, `clampToolPanelHeight`).
const MAX_STORED_PX = 4000;
// Panel ids are short words (`ToolPanel.jsx`'s `id`); a record full of anything else is not ours
// (the floating sidebar's `sidebar:<id>` sizes, which no view draws now, among it).
const PANEL_ID = /^[a-z][a-z0-9-]{0,31}$/;
const MAX_PANELS = 32;

export const DEFAULT_TOOL_STACK = Object.freeze({ panels: Object.freeze({}), collapsed: Object.freeze({}) });
// A tab's id, as a panel's is: a short word.
const TAB_ID = /^[a-z][a-z0-9-]{0,31}$/;

const finite = value => typeof value === "number" && Number.isFinite(value);
const bounded = (value, floor) => finite(value) && value > 0 ? Math.round(Math.min(MAX_STORED_PX, Math.max(floor, value))) : undefined;
const record = value => value && typeof value === "object" && !Array.isArray(value) ? Object.entries(value).slice(0, MAX_PANELS) : [];
const words = value => {
  const kept = {};
  for (const [id, word] of record(value)) if (TAB_ID.test(id) && typeof word === "string" && TAB_ID.test(word)) kept[id] = word;
  return kept;
};
const flags = value => {
  const kept = {};
  for (const [id, flag] of record(value)) if (PANEL_ID.test(id) && typeof flag === "boolean") kept[id] = flag;
  return kept;
};

/**
 * The layout the stack is drawn with, from anything a store handed back: the sizes of the panels a
 * person has set (`{ width?, height? }` by id, each bounded; a panel with neither is absent),
 * and the panels whose folded state differs from nothing at all (`true` folded, `false` unfolded
 * against a panel that starts folded), and the old shared form's tab of the view's panel by the kind of file.
 * @returns {{ panels: Record<string, { width?: number, height?: number }>, collapsed: Record<string, boolean>, tabs?: Record<string, string> }}
 */
export function normalizeToolStack(value) {
  const panels = {};
  for (const [id, size] of record(value?.panels)) {
    if (!PANEL_ID.test(id) || !size || typeof size !== "object") continue;
    const width = bounded(size.width, TOOL_PANEL_WIDTH), height = bounded(size.height, TOOL_PANEL_MIN_HEIGHT);
    if (width !== undefined || height !== undefined) panels[id] = { ...(width !== undefined ? { width } : {}), ...(height !== undefined ? { height } : {}) };
  }
  // The old shared form's tabs, read until the view's panel drops them (`filePanel.js`): no tab, no key.
  const tabs = words(value?.tabs);
  return { panels, collapsed: flags(value?.collapsed), ...(Object.keys(tabs).length ? { tabs } : {}) };
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

// The Selected pane's share of the view's panel's height (`flatDetailHeight`): its height whatever is picked.
export const FLAT_DETAIL_SHARE = 0.4;
export const FLAT_DETAIL_MIN_HEIGHT = 96;
export const FLAT_LISTS_MIN_HEIGHT = 160;

/**
 * The height of the views' Selected pane, and the most it may have. A person's (`kept`, or `draft` during a drag)
 * is used as it is; else a steady share of the panel (`FLAT_DETAIL_SHARE`, 40%), whatever is picked and however
 * much of it there is: the lists above it stop jumping with every pick, a tall screen gets a tall pane, and what is
 * picked scrolls inside it. Always within 96px and what leaves the lists above it 160px; 96px where the panel is not
 * measured yet.
 */
export function flatDetailHeight({ panelHeight = 0, kept = null, draft = null } = {}) {
  const panel = Number(panelHeight) || 0;
  const max = Math.max(FLAT_DETAIL_MIN_HEIGHT, panel - FLAT_LISTS_MIN_HEIGHT);
  const wanted = draft ?? kept ?? panel * FLAT_DETAIL_SHARE;
  return { height: Math.round(Math.min(max, Math.max(FLAT_DETAIL_MIN_HEIGHT, wanted))), max };
}

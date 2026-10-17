// The tool stack's layout, a viewing preference of the person's rather than of a file: the tab
// keeps it (`settings.toolStack` of the tab record) and it holds across files. Four things, and
// nothing else:
//
//   panels     for each panel a person can size (`ToolPanel.jsx`'s `resizable`: the tree, the
//              Reference and Position), the width and the height cap they dragged it to, by panel
//              id — only what they set; a panel opens at its defaults otherwise (`TOOL_PANEL_WIDTH`,
//              and `toolPanelDefaultHeight`: the stack's height);
//   collapsed  which panels are folded to their first row, by panel id;
//   closed     whether a panel a person can close (`closable`: a tree) is closed, by
//              panel id — their own choice, once they have closed or opened it, which then holds
//              in every file of the tab over how the panel starts (`toolPanelClosed`);
//   hidden     whether the whole column — the strip and every panel under it — is put away
//              (`ToolColumn.jsx`): absent until the person hides it (`true`) or shows it (`false`),
//              and then their choice, in every file of the tab, over how it starts (`toolStackHidden`).
//
// Importing this module has no environmental effects.

// Every panel's width: a strip of six tools — each a 24px button (`size-6`,
// `primitives/toolbar-button.jsx`), 2px apart (`gap-0.5`), inside 4px of padding (`p-1`) and a
// 1px border (`FloatingToolBar.js`): 164px, whatever tools a file's own strip has. A fixed panel is
// exactly this wide; a resizable one opens this wide and is only ever made wider.
const STRIP_TOOLS = 6, BUTTON_PX = 24, GAP_PX = 2, PADDING_PX = 4, BORDER_PX = 1;
export const TOOL_PANEL_WIDTH = STRIP_TOOLS * BUTTON_PX + (STRIP_TOOLS - 1) * GAP_PX + 2 * PADDING_PX + 2 * BORDER_PX;
// The strip's height, one of its buttons inside the same padding and border: 34px. A strip of one
// button is this square — the box of the column's own toggle (`ToolColumn.jsx`).
export const TOOL_STRIP_HEIGHT = BUTTON_PX + 2 * PADDING_PX + 2 * BORDER_PX;
// The shortest a person can drag a panel's cap: its first row and a row of content under it.
export const TOOL_PANEL_MIN_HEIGHT = 64;
// A stored size is kept whatever the viewer it was chosen in; what is drawn is bounded by the
// viewer at hand (`clampToolPanelWidth`, `clampToolPanelHeight`).
const MAX_STORED_PX = 4000;
// Panel ids are short words (`ToolPanel.jsx`'s `id`); a record full of anything else is not ours.
const PANEL_ID = /^[a-z][a-z0-9-]{0,31}$/;
const MAX_PANELS = 32;

export const DEFAULT_TOOL_STACK = Object.freeze({ panels: Object.freeze({}), collapsed: Object.freeze({}), closed: Object.freeze({}) });

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
 * person has set (`{ width?, height? }` by id, each bounded; a panel with neither is absent), the
 * panels whose folded state differs from nothing at all (`true` folded, `false` unfolded against a
 * panel that starts folded), the closable panels a person has closed (`true`) or opened (`false`),
 * and, once they have chosen, whether they hid the whole column (`hidden`, absent until then).
 * @returns {{ panels: Record<string, { width?: number, height?: number }>, collapsed: Record<string, boolean>, closed: Record<string, boolean>, hidden?: boolean }}
 */
export function normalizeToolStack(value) {
  const panels = {};
  for (const [id, size] of record(value?.panels)) {
    if (!PANEL_ID.test(id) || !size || typeof size !== "object") continue;
    const width = bounded(size.width, TOOL_PANEL_WIDTH), height = bounded(size.height, TOOL_PANEL_MIN_HEIGHT);
    if (width !== undefined || height !== undefined) panels[id] = { ...(width !== undefined ? { width } : {}), ...(height !== undefined ? { height } : {}) };
  }
  const layout = { panels, collapsed: flags(value?.collapsed), closed: flags(value?.closed) };
  if (typeof value?.hidden === "boolean") layout.hidden = value.hidden;
  return layout;
}

/**
 * Whether the column — the strip and the panels under it — is put away: as the person left it,
 * their choice holding in every file of the tab, and otherwise as it starts: hidden on a phone, so
 * the model has the screen, and shown elsewhere.
 * @param {{ hidden?: boolean } | null | undefined} layout
 * @param {{ mobile?: boolean }} [start]
 */
export function toolStackHidden(layout, { mobile = false } = {}) {
  const stored = layout?.hidden;
  return typeof stored === "boolean" ? stored : mobile;
}

/**
 * Whether a panel a person can close (a tree: its X puts it away, and a press on the tool it
 * belongs to while that tool is up brings it back) is closed: as the person left it — their choice,
 * once made, holds in every file of the tab — and otherwise as it starts: closed on a phone, so the
 * model has the screen, and open elsewhere.
 * @param {{ closed?: Record<string, boolean> } | null | undefined} layout
 * @param {string} id
 * @param {{ mobile?: boolean }} [start]
 */
export function toolPanelClosed(layout, id, { mobile = false } = {}) {
  const stored = layout?.closed?.[id];
  return typeof stored === "boolean" ? stored : mobile;
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
 * The cap a resizable panel opens with where a person has set none, on desktop and phone alike:
 * the stack's own height. So it is as tall as its content needs, up to all the room under the
 * strip, and scrolls inside past that; with others open beside it, the panels share that room by
 * how each gives way (`ToolPanel.jsx`'s `fit`). None until the stack is measured.
 */
export function toolPanelDefaultHeight(stackHeight) {
  return Math.round(Number(stackHeight)) || null;
}

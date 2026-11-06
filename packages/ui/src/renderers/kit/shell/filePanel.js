import { createContext } from "react";

// The view's panel (`FlatPanel.jsx`), kept per file: one more field of the file's view
// (`fileView.js`), `panel`, beside the renderer's own, and written by the panel itself rather
// than by any renderer. The file viewer (`file-viewer/FileViewer.tsx`) holds it for the file on
// screen and merges it into every record the renderer writes, so a renderer that writes its
// view wholesale never drops it; `useFlatPanelState` reads it and writes it through
// `FilePanelContext`. Four things, each absent until the person sets it:
//
//   open          the person opened (`true`) or closed (`false`) the panel; absent, it follows the
//                 view's width (open at 1024px or more);
//   width         the width they dragged it to;
//   tab           the tab it shows;
//   detailHeight  the height they dragged the Selected pane to.
//
// The tab once kept these for every file alike (`settings.toolStack`: `collapsed.flat`,
// `panels.flat.width`, `panels.flatDetail.height` and `tabs` by the kind of file): that form is
// read once, as the starting value of a file that has none (`legacyFilePanel`), then dropped
// from the tab's record (`withoutLegacyFilePanel`) and never written again.

const plainObject = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const MAX_PX = 4000;
const size = value => (typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.round(Math.min(MAX_PX, value)) : undefined);
const TAB_ID = /^[a-z][a-z0-9-]{0,31}$/;

/** A file's panel from anything a record held: the fields that are what they should be, and nothing else. */
export function readFilePanel(value) {
  if (!plainObject(value)) return {};
  const panel = {};
  if (typeof value.open === "boolean") panel.open = value.open;
  const width = size(value.width), detailHeight = size(value.detailHeight);
  if (width !== undefined) panel.width = width;
  if (typeof value.tab === "string" && TAB_ID.test(value.tab)) panel.tab = value.tab;
  if (detailHeight !== undefined) panel.detailHeight = detailHeight;
  return panel;
}

/** The panel a file's own record holds (`record.panel`). */
export const filePanelOf = record => readFilePanel(plainObject(record) ? record.panel : undefined);

/** `record` (what the renderer wrote, or nothing yet) with the file's panel in it, or without one when it has none. */
export function withFilePanel(record, panel) {
  const { panel: _stale, ...rest } = plainObject(record) ? record : {};
  const kept = readFilePanel(panel);
  if (!Object.keys(kept).length) return plainObject(record) ? rest : record;
  return { ...rest, panel: kept };
}

/** Whether the tab's settings still carry the panel's old, shared form. */
export function hasLegacyFilePanel(toolStack) {
  return Boolean(toolStack?.panels?.flat || toolStack?.panels?.flatDetail || toolStack?.collapsed?.flat !== undefined || toolStack?.tabs);
}

/**
 * The old shared form as a file's panel: its starting value where the file has none. Its tab was kept
 * by the kind of view (`tabs`), which a view may name only once its file is read, so it comes back as
 * the map (`legacyFilePanelTab` picks from it).
 * @returns {{ panel: object, tabs: Record<string, string> | null }}
 */
export function legacyFilePanel(toolStack) {
  if (!hasLegacyFilePanel(toolStack)) return { panel: {}, tabs: null };
  const panel = readFilePanel({
    ...(toolStack.collapsed?.flat === true ? { open: false } : {}),
    width: toolStack.panels?.flat?.width,
    detailHeight: toolStack.panels?.flatDetail?.height
  });
  return { panel, tabs: plainObject(toolStack.tabs) ? { ...toolStack.tabs } : null };
}

/** The old shared form's tab for a view of `kind`, if it kept one that is a tab's id. */
export const legacyFilePanelTab = (tabs, kind) => readFilePanel({ tab: kind ? tabs?.[kind] : undefined }).tab;

/** A patch over the tab's tool stack that drops the old shared form (`changeToolStack`'s). */
export function withoutLegacyFilePanel(toolStack) {
  const { flat: _flat, flatDetail: _detail, ...panels } = toolStack?.panels ?? {};
  const { flat: _collapsed, ...collapsed } = toolStack?.collapsed ?? {};
  return { panels, collapsed, tabs: undefined };
}

/**
 * The file on screen's panel, as the file viewer holds it: `panel` (as the person last left it: what its
 * record held as it opened, then each change, so a renderer that mounts again on the same file starts
 * from their choice) and `change(panel)` (kept in its record from now on). Null where no file viewer mounted
 * the view: the panel is then kept for as long as the view is open.
 * @type {import("react").Context<{ panel: object, change(panel: object): void } | null>}
 */
export const FilePanelContext = createContext(null);

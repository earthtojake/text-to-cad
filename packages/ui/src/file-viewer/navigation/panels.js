/**
 * A file surface's panels: the list, and the rule that only one is open.
 *
 * ONE panel column, one width, one border, one resize handle
 * (`FilePanelColumn.jsx`) — and a list of things that can be in it: what the
 * file's renderer declares (a viewer file's own controls) and the file tree LAST. The nav row draws one icon button per
 * panel, in declaration order, and highlights the open one; pressing a toggle
 * opens that panel and closes whatever was open. Tabs inside a panel are the
 * panel's own business (a viewer file's Settings, `FilePanelTabs.jsx`).
 *
 * The panel frame is shared across both apps: the tree is an
 * entry in this list, not a second column beside it with a design of its own.
 * The standalone viewer's file list used to be a LEFT sidebar with its own
 * trigger; it is the rightmost entry here instead, which is why the toggle a
 * person reaches for is in the same place in both apps.
 *
 * The host owns which one is open, not the renderer and not the surface: the
 * toggle is in the nav row and the panel is in the body, and two owners of one
 * flag is how a toggle and a panel come to disagree. It is a single id, so two
 * panels cannot both be open however the writes interleave.
 *
 * Pure but for its lucide glyphs, so `node --test` loads it with no bundler.
 */
import { Folders, SlidersHorizontal } from "lucide-react";

/**
 * Where a panel's content comes from — which is who draws it.
 *
 * `"tree"` and `"slot"` are both the panel column: the shared file tree, or a
 * box handed to the file's renderer to draw into (a viewer surface portals its
 * panels there, `panelSlot` in `docs/file-viewer.md`).
 * `"body"` is the one panel that is not a column at all — the desktop's
 * markdown source view is the same bytes read differently, so it replaces the
 * content instead of sitting beside it. It is still in this list, and still
 * exclusive with the others: one panel open at a time means opening the source
 * closes the tree.
 *
 * @typedef {"tree"|"slot"|"body"} FilePanelContent
 *
 * @typedef {object} FilePanel
 * @property {string} id
 * @property {string} label The accessible name and the tooltip — what pressing it does.
 * @property {import("react").ElementType} icon
 * @property {FilePanelContent} content
 * @property {boolean} [defaultOpen]
 *   The panel a surface opens with when nobody has said (`panel: null`): the
 *   FIRST declaration that claims it wins. A viewer file's own controls claim it;
 *   the file tree never does, so a file opened directly
 *   shows its controls, or nothing when it has none.
 *
 * @typedef {object} FilePanelContext
 * @property {string} open
 *   The id of the open panel, resolved — a declaration reads it to name itself
 *   by what pressing it does (`View source` / `View preview`).
 * @property {boolean} ready
 *   False while the body is not the renderer's own surface: a CAD tab whose
 *   runtime did not start shows a failure card, and a toggle over a card that
 *   cannot open a panel is a dead control.
 */

/**
 * The file tree's panel id. In the desktop it is also the value persisted in
 * a tab's `panel` field, which is why it is a plain string and not a symbol.
 */
export const FILE_PANEL_TREE = "tree";

/**
 * The file sidebar's id. Any other stored id — a retired panel's — resolves as
 * nothing open (`resolveOpenPanel`).
 */
export const CAD_PANEL = Object.freeze({
  file: "cad-file"
});

/**
 * A viewer file's sidebar, when it has file-specific controls. Display settings
 * live in the viewport toolbar's popover and never occupy this column.
 *
 * `file` asks for it: one panel, always labelled "Settings" under the sliders icon,
 * whatever the file is; false for a file whose only settings are Display's (a
 * mesh). It is the default: a file opened directly opens with its controls.
 *
 * Nothing until the surface is up: a pane whose runtime did not start shows a
 * failure card, and a toggle over a card would open nothing.
 *
 * @param {boolean} ready
 * @param {{ file?: boolean }} [options]
 * @returns {FilePanel[]}
 */
export function viewerPanels(ready, { file = false } = {}) {
  if (!ready) return [];
  return [
    ...(file ? [{ id: CAD_PANEL.file, label: "Settings", icon: SlidersHorizontal, content: "slot", defaultOpen: true }] : [])
  ];
}

/**
 * The file tree, as the last entry in every panel list: the folders glyph is
 * always the rightmost navigation action.
 *
 * It stays open while a person walks the tree from file to file, but it is not
 * what a file opens with — except where there is no file to show at all, when
 * the tree is the only thing to reach for (`empty`).
 *
 * @param {string} open
 * @param {{ empty?: boolean }} [options]
 * @returns {FilePanel}
 */
export function treePanel(open, { empty = false } = {}) {
  return {
    id: FILE_PANEL_TREE,
    label: open === FILE_PANEL_TREE ? "Hide files" : "Show files",
    icon: Folders,
    content: "tree",
    defaultOpen: empty
  };
}

/**
 * Which panel is open, given the stored field and the panels there are.
 *
 * `null` — nobody has said — is the first panel claiming `defaultOpen`. `""`
 * is nothing open, and an id no panel in this list has is nothing open too: a
 * pane that was showing markdown's source and is pointed at a `.step`, or a
 * CAD pane whose surface has not come up, names a panel that is not there, and
 * the honest answer is that nothing is.
 *
 * @param {FilePanel[]} panels
 * @param {string|null} panel
 * @returns {FilePanel|null}
 */
export function resolveOpenPanel(panels, panel) {
  if (panel === null) {
    return panels.find((entry) => entry.defaultOpen) ?? null;
  }
  return panels.find((entry) => entry.id === panel) ?? null;
}

/**
 * The stored field after pressing one panel's toggle.
 *
 * Opening one closes whatever was open, and pressing the open one closes it —
 * which is the whole rule, because the field is one id. A press while another
 * panel is up reads as "show me this instead" and never blinks the column shut
 * on the way.
 *
 * @param {string} open
 * @param {string} id
 * @returns {string}
 */
export function nextOpenPanel(open, id) {
  return open === id ? "" : id;
}

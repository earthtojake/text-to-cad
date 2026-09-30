/**
 * A file surface's panels: the list, and the rule that only one is open.
 *
 * A list of things that can be open beside a file — what the file's renderer declares, then the
 * file tree LAST — and one id saying which is. The tree is the file explorer, which floats over
 * the view's left (`FileExplorer.jsx`), its toggle at the navbar's left beside the home mark; a
 * declared panel opens in the column at the view's right (`FilePanelColumn.jsx`), its toggle at
 * the navbar's right. Pressing a toggle opens that panel and closes whatever was open. A CAD file
 * declares none: its controls are panels in the viewer's own tool stack, shown by the tool they
 * belong to (`docs/settings-ui.md`), so nothing a renderer does opens or turns the explorer.
 *
 * The host owns which one is open, not the renderer and not the surface: the toggle is in the
 * navbar and the panel is in the body, and two owners of one flag is how a toggle and a panel
 * come to disagree. It is a single id, so two panels cannot both be open however the writes
 * interleave.
 *
 * Pure but for its lucide glyphs, so `node --test` loads it with no bundler.
 */
import { Folders } from "lucide-react";

/**
 * Where a panel's content comes from — which is who draws it.
 *
 * `"tree"` is the shared file tree, in the explorer over the view's left; `"slot"` is a box
 * handed to the file's renderer to draw into (`panelSlot` in `docs/file-viewer.md`), in the
 * column at the view's right.
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
 *   FIRST declaration that claims it wins. The file tree claims it only when
 *   there is no file to show, so a file opened directly opens with nothing
 *   beside it unless its own declaration says otherwise.
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
 * The file tree, as the last entry in every panel list: the explorer, whose toggle is the
 * navbar's second control, after the home mark.
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
 * stored id of a retired panel (a CAD file's old Settings, `cad-file`), names a
 * panel that is not there, and the honest answer is that nothing is.
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

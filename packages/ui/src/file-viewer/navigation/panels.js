/**
 * A file surface's panels: the list a file's renderer declares, and the rule that only one is open.
 *
 * A declared panel opens in the column at the view's right (`FilePanelColumn.jsx`), its toggle at
 * the navbar's right; pressing a toggle opens that panel and closes whatever was open. A CAD file
 * declares none: its controls are panels in the viewer's own tool stack, shown by the tool they
 * belong to (`docs/settings-ui.md`). The file explorer is not a panel: it is the popover the
 * navbar's file name opens (`FolderExplorer.jsx`).
 *
 * The host owns which one is open, not the renderer and not the surface: the toggle is in the
 * navbar and the panel is in the body, and two owners of one flag is how a toggle and a panel
 * come to disagree. It is a single id, so two panels cannot both be open however the writes
 * interleave.
 *
 * Pure, so `node --test` loads it with no bundler.
 *
 * @typedef {"slot"|"body"} FilePanelContent
 *   `"slot"` is a box handed to the file's renderer to draw into (`panelSlot` in
 *   `docs/file-viewer.md`), in the column; `"body"` replaces the content instead of sitting beside it.
 *
 * @typedef {object} FilePanel
 * @property {string} id
 * @property {string} label The accessible name and the tooltip — what pressing it does.
 * @property {import("react").ElementType} icon
 * @property {FilePanelContent} content
 * @property {boolean} [defaultOpen]
 *   The panel a surface opens with when nobody has said (`panel: null`): the FIRST declaration
 *   that claims it wins.
 *
 * @typedef {object} FilePanelContext
 * @property {string} open
 *   The id of the open panel, resolved — a declaration reads it to name itself by what pressing it does.
 * @property {boolean} ready
 *   False while the body is not the renderer's own surface: a toggle over a card that cannot open
 *   a panel is a dead control.
 */

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

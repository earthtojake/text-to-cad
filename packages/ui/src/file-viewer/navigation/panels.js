/**
 * A file surface's panels: the list, and the rule that only one is open.
 *
 * ONE panel column, one width, one border, one resize handle
 * (`FilePanelColumn.jsx`) — and a list of things that can be in it: the CAD
 * Inspector, whatever else the host's renderer declares,
 * and the file tree LAST. The nav row draws one icon button per panel, in
 * declaration order, and highlights the open one; pressing a toggle opens that
 * panel and closes whatever was open.
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
import { Code2, Eye, Folders, PanelLeft, SlidersHorizontal } from "lucide-react";

/**
 * Where a panel's content comes from — which is who draws it.
 *
 * `"tree"` and `"slot"` are both the panel column: the shared file tree, or a
 * box handed to the file's renderer to draw into (the CAD surface portals its
 * Inspector there, `panelSlot` in `docs/file-view.md`).
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
 *   The panel a surface opens with when the person has not said (`panel:
 *   null`). The FIRST declaration that claims it wins, and the tree is last,
 *   so a CAD file opens with its Inspector and everything else with the tree.
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

/** The Inspector's panel id, shared by both hosts and every viewer renderer. */
export const CAD_PANEL = Object.freeze({
  fileSheet: "cad-file-sheet"
});

/** The desktop's markdown source view — its own id, since the field holds ids. */
export const SOURCE_PANEL = "source";

/**
 * The Inspector: the panel a viewer renderer declares for its file's tabs.
 *
 * Declared here rather than in either app, because both draw it: each portals
 * it into its panel column through `panelSlot`. Every viewer renderer declares
 * this SAME panel, so a person who opened the Inspector keeps it open from one
 * model to the next, whichever renderer shows it.
 *
 * "Inspector" is the name a person sees. The id stays `cad-file-sheet` because
 * the desktop's stored `panel` field holds it and the viewer's host contract
 * calls the same panel `fileSheetOpen`.
 *
 * Nothing until the surface is up: a pane whose runtime did not start shows a
 * failure card, and a toggle over a card would open nothing.
 *
 * Whether it starts open is the renderer's to say (`defaultOpen`): a file whose
 * Inspector is only its Display settings opens with the column shut, so the model
 * gets the room. It is a default, so a person who opens the Inspector keeps it open.
 *
 * @param {boolean} ready
 * @param {{ defaultOpen?: boolean }} [options]
 * @returns {FilePanel[]}
 */
export function inspectorPanels(ready, { defaultOpen = true } = {}) {
  return ready
    ? [
      {
        id: CAD_PANEL.fileSheet,
        label: "Inspector",
        icon: SlidersHorizontal,
        content: "slot",
        defaultOpen
      }
    ]
    : [];
}

/**
 * The desktop's markdown panel: the same bytes read as a document or as
 * source. Here because it is one of the list and obeys the same rule; the
 * label is what pressing it does.
 *
 * @param {string} open
 * @returns {FilePanel[]}
 */
export function markdownPanels(open) {
  return [
    {
      id: SOURCE_PANEL,
      label: open === SOURCE_PANEL ? "View preview" : "View source",
      icon: open === SOURCE_PANEL ? Eye : Code2,
      content: "body"
    }
  ];
}

/**
 * The file tree, as the last entry in every panel list.
 *
 * The folders glyph is always the rightmost navigation action. Inspector
 * uses PanelLeft; document actions precede the pair.
 *
 * @param {string} open
 * @returns {FilePanel}
 */
export function treePanel(open) {
  return {
    id: FILE_PANEL_TREE,
    label: open === FILE_PANEL_TREE ? "Hide files" : "Show files",
    icon: Folders,
    content: "tree",
    defaultOpen: true
  };
}

/**
 * Every panel a surface has, in the order the nav row draws them: the
 * renderer's, then the tree.
 *
 * @param {FilePanel[]} declared
 * @param {string} open
 * @returns {FilePanel[]}
 */
export function panelsFor(declared, open) {
  return [...declared, treePanel(open)];
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

/**
 * What the open panel becomes when the CAD surface reports one of ITS OWN
 * panels open or shut.
 *
 * `true` opens it, over whatever was up. `false` is only ever about the panel
 * it names: the surface reports its state on every change, so a "the
 * Inspector is shut" arriving while the file TREE is the open panel must leave
 * the tree alone rather than close the column.
 *
 * @param {boolean} open
 * @param {string} current
 * @param {string} id
 * @returns {string}
 */
export function panelClosedBy(open, current, id) {
  if (open) {
    return id;
  }
  return current === id ? "" : current;
}

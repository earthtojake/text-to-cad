// The view's one panel (`ViewFrame.jsx`), the sidebar at its left (`FlatPanel.jsx`): the file's structure (its Model
// tree, a board's Parts, Nets and Layers…) and, as tabs after it, the file's own settings (Parameters, Joints,
// Animation). How it shares the view, as design and CAD tools do (Figma, Sketch, VS Code, KiCad):
//
// - Its toggle is the navbar's, and its key ⌘\ (Ctrl+\ elsewhere).
// - Pinned open, it always pushes: it takes its width beside the model, the model's area the narrower for it (the
//   model centred in what is left). The one thing that overlays the model is a peek of the collapsed panel, a mouse
//   resting on its toggle (`usePanelPeek.js`), which this module never sees: it pushes nothing and is kept nowhere.
// - Until the person opens or closes it on a file, it follows the view: open where the model keeps `MIN_MODEL_WIDTH`
//   beside the default-width panel (the view at least that and 232px: 872px, whatever width the grip has set, so a
//   drag never collapses the panel under the grip), collapsed below, and again
//   as the window is resized across that line. Once they have opened or closed it on that file (its toggle, its key,
//   a peek pinned), their choice holds there at any width: no window opens or collapses it again. A peek is no choice.
//   Another file follows the view until it has a choice of its own.
// - What is kept is what the person chose (opened or closed it) and the width they dragged it to, for the file, for
//   this browser session (the file's entry in the tab's settings: `file-viewer/filePanel.js`).
// - Its width is the person's, between fixed bounds, the same at any window width: 232px at first
//   (`DEFAULT_PANEL_WIDTH`), from 200px (`FlatPanel.jsx`'s `FLAT_PANEL_MIN_WIDTH`) to `MAX_PANEL_WIDTH`. A panel the
//   person pins open in a narrow window may leave the model little room: that is their choice.
//
// Importing this module has no environmental effects.

/** The least width the model's area keeps with the panel open beside it; narrower, the panel starts collapsed. */
export const MIN_MODEL_WIDTH = 640;
/**
 * The panel's width where none is given (`FlatPanel.jsx`'s `FLAT_PANEL_DEFAULT_WIDTH`): one fixed number, never the
 * view's or the tabs', budgeted for three tabs: the least width on the 8px grid where every three tabs a file can have
 * (a model's Model and two of Params, Joints and Motion; a board's Parts, Nets and Layers; a schematic's Parts, Nets and
 * Hierarchy) stand in English beside the search's icon with no ⋯ (the widest, Model, Params and Motion, needs 225px). A
 * fourth tab is ⋯'s.
 */
export const DEFAULT_PANEL_WIDTH = 232;
/** The widest the grip takes the panel, at any window width: on the 8px grid, about twice the default. */
export const MAX_PANEL_WIDTH = 480;

/**
 * Whether the view's width collapses the panel on its own: open, it would leave the model under `MIN_MODEL_WIDTH`
 * (a `frameWidth` of 0, not measured yet, does not).
 */
export function sidebarCollapsed(frameWidth, panelWidth = DEFAULT_PANEL_WIDTH) {
  return frameWidth > 0 && frameWidth - panelWidth < MIN_MODEL_WIDTH;
}

/**
 * Where the panel is: `"push"` (beside the model, the model narrower for it) or `"closed"`; and whether that is the
 * view's doing (`auto`: the person has made no choice on this file, so the view's width decides).
 *
 * @param {{ frameWidth: number, choice?: boolean, has: boolean }} state
 *   `choice`: the person's, on this file (`filePanel.js`'s `open`): open (true), closed (false), or none (absent): then
 *   the view's width decides, against the default width (`sidebarCollapsed`).
 * @returns {{ mode: "push" | "closed", auto: boolean }}
 */
export function sidebarLayout({ frameWidth, choice, has }) {
  const auto = typeof choice !== "boolean";
  const open = Boolean(has) && (auto ? !sidebarCollapsed(frameWidth) : choice);
  return { mode: open ? "push" : "closed", auto };
}

/**
 * A press on the panel's toggle (its button, its key, a peek's pin): the person's choice, kept for the file from now
 * on whatever the view's width — open where the panel is shut, shut where it is open.
 * @param {Parameters<typeof sidebarLayout>[0]} state
 * @returns {{ open: boolean }}
 */
export function toggleSidebar(state) {
  return { open: sidebarLayout(state).mode !== "push" };
}

/** A width as the panel draws it: the person's (or the default), within the fixed bounds, whatever was stored. */
export const clampPanelWidth = (width, minWidth) => Math.round(Math.min(MAX_PANEL_WIDTH, Math.max(minWidth, Number(width) || DEFAULT_PANEL_WIDTH)));

// The view's one panel (`ViewFrame.jsx`), the sidebar at its left (`FlatPanel.jsx`): the file's structure (its Model
// tree, a board's Parts, Nets and Layers…) and, as tabs after it, the file's own settings (Parameters, Joints,
// Animation). How it shares the view, as design and CAD tools do (Figma, Sketch, VS Code, KiCad):
//
// - Its toggle is the navbar's, and its key ⌘\ (Ctrl+\ elsewhere).
// - It always pushes: open, it takes its width beside the model, the model's area the narrower for it (the model
//   centred in what is left); nothing overlays the model at any width.
// - It starts open only where the model keeps `MIN_MODEL_WIDTH` beside it (the view at least that and the panel's width:
//   896px with the 256px panel), and collapsed below. That collapse is the width's, never
//   written, so widening the view brings back the person's choice. Opened over it by the person, it pushes (kept for
//   now, nowhere else: `opened`).
// - What is kept is what the person chose (opened or closed it), for the file, for this browser session
//   (the file's entry in the tab's settings: `file-viewer/filePanel.js`).
//
// Importing this module has no environmental effects.

/** The least width the model's area keeps with the panel open beside it; narrower, the panel starts collapsed. */
export const MIN_MODEL_WIDTH = 640;
/**
 * The panel's width where none is given (`FlatPanel.jsx`'s `FLAT_PANEL_DEFAULT_WIDTH`): one fixed number, never the
 * view's or the tabs', room for the usual tabs (Model, Params, Joints, Motion) and the search's icon without the ⋯.
 */
export const DEFAULT_PANEL_WIDTH = 256;

/**
 * Whether the view's width collapses the panel on its own: open, it would leave the model under `MIN_MODEL_WIDTH`
 * (a `frameWidth` of 0, not measured yet, does not).
 */
export function sidebarCollapsed(frameWidth, panelWidth = DEFAULT_PANEL_WIDTH) {
  return frameWidth > 0 && frameWidth - panelWidth < MIN_MODEL_WIDTH;
}

/**
 * Where the panel is: `"push"` (beside the model, the model narrower for it) or `"closed"`; and whether it is
 * collapsed only because the view is narrow (`auto`).
 *
 * @param {{ frameWidth: number, panelWidth?: number, want: boolean, has: boolean, opened?: boolean }} state
 *   `want`: what the person chose (or the default, open). `opened`: the person opened it over the width's collapse,
 *   kept for now and nowhere else.
 * @returns {{ mode: "push" | "closed", auto: boolean }}
 */
export function sidebarLayout({ frameWidth, panelWidth, want, has, opened = false }) {
  const wanted = Boolean(has && want);
  const open = wanted && (!sidebarCollapsed(frameWidth, panelWidth) || opened === true);
  return { mode: open ? "push" : "closed", auto: wanted && !open };
}

/**
 * What a press on the panel's toggle (its button, or its key) changes: `want` (kept, the person's choice) and `opened`
 * (opened over the width's collapse, kept nowhere). An open panel closes, and the close is kept; a closed one opens and
 * pushes, the choice to have it open kept, and where the width had collapsed it, it is opened over that.
 * @param {Parameters<typeof sidebarLayout>[0]} state
 * @returns {{ want: boolean, opened: boolean, kept: boolean }}  `kept`: whether `want` changed (and is to be written).
 */
export function toggleSidebar(state) {
  if (sidebarLayout(state).mode === "push") return { want: false, opened: false, kept: true };
  return { want: true, opened: sidebarCollapsed(state.frameWidth, state.panelWidth), kept: !state.want };
}

/** The person's choice as the file's entry keeps it (`filePanel.js`'s `open`): open (true) or closed (false), absent for the default, open. */
export const sidebarWant = kept => kept !== false;

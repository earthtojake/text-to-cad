// The view's one panel (`ViewFrame.jsx`), the sidebar at its left (`FlatPanel.jsx`): the file's structure (its Model
// tree, a board's Parts, Nets and Layers…) and, as tabs after it, the file's own settings (Parameters, Joints,
// Animation). How it shares the view, as design and CAD tools do (Figma, Sketch, VS Code, KiCad):
//
// - Its toggle is the navbar's, and its key ⌘\ (Ctrl+\ elsewhere).
// - Pinned open, it always pushes: it takes its width beside the model, the model's area the narrower for it (the
//   model centred in what is left). The one thing that overlays the model is a peek of the collapsed panel, a mouse
//   resting on its toggle (`usePanelPeek.js`), which this module never sees: it pushes nothing and is kept nowhere.
// - It starts open only where the model keeps `MIN_MODEL_WIDTH` beside it (the view at least that and the panel's width:
//   872px with the 232px panel), and collapsed below. That collapse is the width's, never
//   written, so widening the view brings back the person's choice. Opened over it by the person, it pushes (kept for
//   now, nowhere else: `opened`).
// - What is kept is what the person chose (opened or closed it), for the file, for this browser session
//   (the file's entry in the tab's settings: `file-viewer/filePanel.js`).
//
// Importing this module has no environmental effects.

// Where the panel starts open, the one rule the file viewer's toggle before the view is up shares (`file-viewer/panelToggles.js`).
import { DEFAULT_PANEL_WIDTH, MIN_MODEL_WIDTH, sidebarCollapsed, sidebarWant } from "../../../file-viewer/panelToggles.js";

export { DEFAULT_PANEL_WIDTH, MIN_MODEL_WIDTH, sidebarCollapsed, sidebarWant };

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

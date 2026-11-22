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

// The rule itself (`MIN_MODEL_WIDTH`, `DEFAULT_PANEL_WIDTH`, `MAX_PANEL_WIDTH`, `sidebarCollapsed`, `sidebarLayout`,
// `clampPanelWidth`) is the file viewer's (`file-viewer/panelToggles.js`), re-exported here: its toggle and the panel's
// empty frame before the view is up follow the one rule the view's frame then follows.
import { DEFAULT_PANEL_WIDTH, MAX_PANEL_WIDTH, MIN_MODEL_WIDTH, MIN_PANEL_WIDTH, clampPanelWidth, sidebarCollapsed, sidebarLayout }
  from "../../../file-viewer/panelToggles.js";

export { DEFAULT_PANEL_WIDTH, MAX_PANEL_WIDTH, MIN_MODEL_WIDTH, MIN_PANEL_WIDTH, clampPanelWidth, sidebarCollapsed, sidebarLayout };

/**
 * A press on the panel's toggle (its button, its key, a peek's pin): the person's choice, kept for the file from now
 * on whatever the view's width — open where the panel is shut, shut where it is open.
 * @param {Parameters<typeof sidebarLayout>[0]} state
 * @returns {{ open: boolean }}
 */
export function toggleSidebar(state) {
  return { open: sidebarLayout(state).mode !== "push" };
}

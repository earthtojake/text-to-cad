import { createContext, useContext, useEffect } from "react";

// The view's panel toggle lives in the navbar (`navigation/ViewerNavbar.jsx`), its first control, before the logo. The
// panel is the renderer's (`renderers/kit/shell/ViewFrame.jsx`), the navbar the file viewer's, so the frame says what
// its toggle is through this context and `FileViewer` hands it to the navbar. A frame drawn outside a file viewer (no
// context) has no toggle but its key.
//
// Importing this module has no environmental effects.

/**
 * @typedef {object} PanelToggle  The panel's toggle, as the navbar draws it.
 * @property {boolean} open  The panel is open (said by `aria-expanded`; the button looks the same either way).
 * @property {string} label  Its name now ("Hide panel", "Show panel").
 * @property {string} [shortcut]  Its key, for the tooltip ("⌘\\").
 * @property {() => void} toggle
 * @property {boolean} [disabled]  Drawn, in the state the view will open its panel in, but not pressable yet: the file
 *   viewer's own, while the view is not up (`FileViewer.tsx`). It looks the same; a press does nothing.
 * @property {object | null} [hover]  Its pointer handlers (`onPointerEnter`, `onPointerLeave`, `onPointerDown`): a mouse
 *   resting on it peeks the collapsed panel (`renderers/kit/shell/usePanelPeek.js`).
 * @property {boolean} [peeking]  The panel peeks: the toggle's tooltip is closed while it does.
 *
 * @typedef {{ left?: PanelToggle | null }} PanelToggles  The panel's toggle (`left`: the panel is the left sidebar).
 */

/** Where a view's frame says its toggle: `(toggles: PanelToggles | null) => void`, null for none. */
/** @type {import("react").Context<((toggles: PanelToggles | null) => void) | null>} */
export const PanelTogglesContext = createContext(/** @type {((toggles: PanelToggles | null) => void) | null} */ (null));

/**
 * Where a view's frame says, as it renders, that it is one (and so says its toggle, or none, in its first effects):
 * the file viewer draws the toggle the view will have until then, and drops it at once for a view with no frame.
 * @type {import("react").Context<(() => void) | null>}
 */
export const PanelFrameContext = createContext(/** @type {(() => void) | null} */ (null));

/**
 * Says the view's toggle to the navbar while the frame is mounted, again whenever it changes, and none once it goes.
 * `toggles` should be memoised by its caller: a new object says them again.
 * @param {PanelToggles | null} toggles
 */
export function usePanelToggles(toggles) {
  const publish = useContext(PanelTogglesContext);
  useContext(PanelFrameContext)?.();
  useEffect(() => {
    if (!publish) return undefined;
    publish(toggles);
    return () => publish(null);
  }, [publish, toggles]);
}

// Where the view's panel starts open (`renderers/kit/shell/sidebars.js`, which re-exports these): here, so the file
// viewer draws the toggle the view will have before any renderer is loaded.

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

/**
 * Whether the view's width collapses the panel on its own: open, it would leave the model under `MIN_MODEL_WIDTH`
 * (a `frameWidth` of 0, not measured yet, does not).
 */
export function sidebarCollapsed(frameWidth, panelWidth = DEFAULT_PANEL_WIDTH) {
  return frameWidth > 0 && frameWidth - panelWidth < MIN_MODEL_WIDTH;
}

// The panel surface's metrics the file viewer's stand-in for it needs too (`renderers/kit/shell/PanelSurface.jsx`, which
// uses these): drawn before any view is up, it stands exactly where the view's loading panel will.

/** The panel's vertical step: 8px over the head's row (and under it, to its rule, where it has one). */
export const PANEL_SURFACE_PX = 8;
/** The head's row where it is one title (the view's single tab, or a tab not known yet): a list row's height, 28px. */
export const PANEL_TITLE_HEAD_PX = 28;
/** The body under a one-title head starts this far under it (`FlatPanel.jsx`'s `pt-1`), so the list follows the title. */
export const PANEL_TITLE_BODY_GAP_PX = 4;
/**
 * The rows' horizontal geometry the panel sets (`primitives/tree-row.jsx` reads it): a row's fill hangs half the inset
 * out past the line and its glyph stands half the inset into it; its last action's glyph ends the inset from the
 * panel's right (half the inset, less that button's own 2px).
 */
export const PANEL_ROW_VARIABLES = Object.freeze({ "--tree-row-pad": "calc(var(--panel-inset) / 2)", "--tree-row-hang": "calc(var(--panel-inset) / 2)",
  "--tree-row-actions-pad": "calc(var(--panel-inset) / 2 - 2px)" });

/** The person's choice as the file's entry keeps it (`filePanel.js`'s `open`): open (true) or closed (false), absent for the default, open. */
export const sidebarWant = kept => kept !== false;

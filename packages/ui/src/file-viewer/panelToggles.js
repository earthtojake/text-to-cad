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
 * @property {boolean} [disabled]  Drawn but not pressable (`aria-disabled`): it looks the same; a press does nothing.
 * @property {object | null} [hover]  Its pointer handlers (`onPointerEnter`, `onPointerLeave`, `onPointerDown`): a mouse
 *   resting on it peeks the collapsed panel (`panelPeek.js`).
 * @property {boolean} [peeking]  The panel peeks: the toggle's tooltip is closed while it does.
 * @property {boolean} [peekable]  The panel is collapsed where it can peek (a desktop's, not in Preview): the page's one peek
 *   (`panelPeek.js`) is enabled while the toggle drawn says so; not said (undefined) while the frame has not measured
 *   its width, the peek staying as it was.
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

// Where the view's panel is open, and how wide (`renderers/kit/shell/sidebars.js`, which re-exports these and says the
// rule in full): here, so the file viewer draws the toggle, and the panel's frame, the view will have before any
// renderer is loaded.

/** The least width the model's area keeps beside the default-width panel; narrower, a file with no choice of the person's has it collapsed. */
export const MIN_MODEL_WIDTH = 640;
/**
 * The panel's width where none is given (`FlatPanel.jsx`'s `FLAT_PANEL_DEFAULT_WIDTH`): one fixed number, never the
 * view's or the tabs', budgeted for three tabs: the least width on the 8px grid where every three tabs a file can have
 * (a model's Model and two of Params, Joints and Motion; a board's Parts, Nets and Layers; a schematic's Parts, Nets and
 * Hierarchy) stand in English beside the search's icon with no ⋯ (the widest, Model, Params and Motion, needs 213px with
 * the pills' 6px padding, so 19px to spare, kept for longer translations). A fourth tab is ⋯'s.
 */
export const DEFAULT_PANEL_WIDTH = 232;
/** The narrowest the grip takes the panel (`FlatPanel.jsx`'s `FLAT_PANEL_MIN_WIDTH`). */
export const MIN_PANEL_WIDTH = 200;
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

/** A width as the panel draws it: the person's (or the default), within the fixed bounds, whatever was stored. */
export const clampPanelWidth = (width, minWidth = MIN_PANEL_WIDTH) =>
  Math.round(Math.min(MAX_PANEL_WIDTH, Math.max(minWidth, Number(width) || DEFAULT_PANEL_WIDTH)));

// The panel surface's metrics the file viewer's stand-in for it needs too (`renderers/kit/shell/PanelSurface.jsx` and
// `FlatPanel.jsx` use these): drawn before any view is up, it stands exactly where the view's loading panel will.

/** The panel's vertical step: 8px over the head's row, 8px under it to its rule, and 8px from the rule to the body's first row. */
export const PANEL_SURFACE_PX = 8;
/**
 * The head's row: ONE block whatever it holds (a lone title, the tabs, the search box): 32px (the 28px pills and
 * buttons and 4px), between its two 8px steps, over its 1px rule.
 */
export const PANEL_HEAD_ROW_PX = 32;
/** The head's row as drawn, at THE scale (`globals.css`): the control and 4px (32px on a desktop, 40 on a phone). */
export const PANEL_HEAD_ROW = "calc(var(--cad-control) + 4px)";
/**
 * The rows' horizontal geometry the panel sets (`primitives/tree-row.jsx` reads it): a row's fill hangs half the inset
 * out past the line and its glyph stands half the inset into it; its last action's glyph ends the inset from the
 * panel's right (half the inset, less that button's own 2px).
 */
export const PANEL_ROW_VARIABLES = Object.freeze({ "--tree-row-pad": "calc(var(--panel-inset) / 2)", "--tree-row-hang": "calc(var(--panel-inset) / 2)",
  "--tree-row-actions-pad": "calc(var(--panel-inset) / 2 - 2px)" });

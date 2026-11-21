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
 *
 * @typedef {{ left?: PanelToggle | null }} PanelToggles  The panel's toggle (`left`: the panel is the left sidebar).
 */

/** Where a view's frame says its toggle: `(toggles: PanelToggles | null) => void`, null for none. */
/** @type {import("react").Context<((toggles: PanelToggles | null) => void) | null>} */
export const PanelTogglesContext = createContext(/** @type {((toggles: PanelToggles | null) => void) | null} */ (null));

/**
 * Says the view's toggle to the navbar while the frame is mounted, again whenever it changes, and none once it goes.
 * `toggles` should be memoised by its caller: a new object says them again.
 * @param {PanelToggles | null} toggles
 */
export function usePanelToggles(toggles) {
  const publish = useContext(PanelTogglesContext);
  useEffect(() => {
    if (!publish) return undefined;
    publish(toggles);
    return () => publish(null);
  }, [publish, toggles]);
}

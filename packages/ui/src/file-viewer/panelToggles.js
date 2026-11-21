import { createContext, useContext, useEffect } from "react";

// The view's two panel toggles live in the navbar (`navigation/ViewerNavbar.jsx`): the left one after the file's name
// and its ⋯, the right one at the row's far right. The panels are the renderer's (`renderers/kit/shell/ViewFrame.jsx`),
// the navbar the file viewer's, so the frame says what its toggles are through this context and `FileViewer` hands
// them to the navbar. A frame drawn outside a file viewer (no context) has no toggles but its keys.
//
// Importing this module has no environmental effects.

/**
 * @typedef {object} PanelToggle  One panel's toggle, as the navbar draws it.
 * @property {boolean} open  The panel is open (the button pressed, its icon the brand's).
 * @property {string} label  Its name now ("Hide panel", "Show properties").
 * @property {string} [shortcut]  Its key, for the tooltip ("⌘\\").
 * @property {string} [hint]  A second key that reaches it ("\\ hides all").
 * @property {() => void} toggle
 *
 * @typedef {{ left?: PanelToggle | null, right?: PanelToggle | null }} PanelToggles
 */

/** Where a view's frame says its toggles: `(toggles: PanelToggles | null) => void`, null for none. */
/** @type {import("react").Context<((toggles: PanelToggles | null) => void) | null>} */
export const PanelTogglesContext = createContext(/** @type {((toggles: PanelToggles | null) => void) | null} */ (null));

/**
 * Says the view's toggles to the navbar while the frame is mounted, again whenever they change, and none once it goes.
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

import { createContext, useContext } from "react";

// Home's navbar (`navigation/ViewerNavbar.jsx`) holds Home's own controls — "Home" at its left, the
// search and Import at its right — in two slots the navbar draws on the grid's column; the home (`library/ModelLibrary.tsx`)
// portals its controls into them. The slots are elements, null until the navbar has drawn them; outside a file viewer
// there are none, and the home draws its controls in its own row.
//
// Importing this module has no environmental effects.

/** @typedef {{ left: HTMLElement | null, right: HTMLElement | null }} NavbarSlots */

/** @type {import("react").Context<NavbarSlots | null>} */
export const NavbarSlotsContext = createContext(/** @type {NavbarSlots | null} */ (null));

/** Home's navbar slots, or null where there is no navbar to hold its controls. */
export const useNavbarSlots = () => useContext(NavbarSlotsContext);

/**
 * A file's navbar's view slot: the element at the row's right end where the view on screen portals its view settings
 * (Display, then Preview where the view has it: `renderers/kit/shell/NavbarViewControls.jsx`), null until the navbar
 * has drawn it, and outside a file viewer's navbar, where a view ends its tool strip with them.
 */
/** @type {import("react").Context<HTMLElement | null>} */
export const NavbarViewSlotContext = createContext(/** @type {HTMLElement | null} */ (null));

/** The navbar's view slot, or null where there is none. */
export const useNavbarViewSlot = () => useContext(NavbarViewSlotContext);

/**
 * The app's menu where the panel's foot holds it (`PanelFoot.jsx`: the bottom of the sidebar, on the home and over a
 * document): its content (the host's links, the person's settings: `AppMenu`'s props), which the file viewer hands
 * down where the host has a home. Null where the host has no home (its logo opens the menu), where there is nothing
 * to put in it, and outside a file viewer: no foot.
 * @type {import("react").Context<{ links?: object, appSettings?: readonly object[], colorScheme?: object, language?: object, platform?: string } | null>}
 */
export const AppMenuContext = createContext(/** @type {any} */ (null));

/** The app's menu's content, for the panel's foot; null where there is none. */
export const useAppMenu = () => useContext(AppMenuContext);

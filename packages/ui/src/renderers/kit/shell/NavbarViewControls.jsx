import { createPortal } from "react-dom";
import { useI18n } from "@cad/ui/i18n";
import { useNavbarViewSlot } from "../../../file-viewer/navbarSlots.js";

/**
 * The view's settings in the file's navbar, at its right end (`file-viewer/navbarSlots.js`): how the picture is
 * looked at — **View ▾** (`ViewSettingsMenu.jsx`'s `ViewMenu`: Display, Projection, Background and Grid, or a board's
 * Side, Mode, Display and Background, one menu of submenus, the same on a desktop and a phone), then a 3D view's
 * **Preview**, last — as the navbar's own 28px buttons, their tooltips and menus under them. The picture keeps only
 * the camera's controls in its top-right corner (the cube and its Home, or a flat view's zoom; a phone's none:
 * gestures and the menu's Reset view). Outside a file viewer's navbar (a host's inline card)
 * there is no slot, and a view keeps its settings over its picture as before (`ViewCornerStack.jsx`, Preview at the
 * strip's end, a phone's in its More): `useNavbarViewControls` says which.
 */

/** A navbar view button: the navbar's 28px, its 16px glyph, muted until under the pointer or open. */
export const NAVBAR_VIEW_BUTTON_CLASS = "size-7 shrink-0 rounded-md text-muted-foreground hover:text-foreground aria-expanded:bg-accent aria-expanded:text-foreground [&>svg]:size-4!";

/** What each control needs to stand in the navbar: its class, and its tooltip and menu under it, a menu's end on its button's. */
export const NAVBAR_VIEW_PLACE = Object.freeze({ className: NAVBAR_VIEW_BUTTON_CLASS, tooltipSide: "bottom", side: "bottom", align: "end" });

/** Whether the view's settings stand in the navbar: a navbar slot to hold them, on a desktop and on a phone alike. */
export function useNavbarViewControls() {
  return Boolean(useNavbarViewSlot());
}

/** `children` drawn in the navbar's view slot, as one group; nothing where there is no slot. */
export default function NavbarViewControls({ children }) {
  const { t } = useI18n();
  const slot = useNavbarViewSlot();
  if (!slot) return null;
  return createPortal(<div role="group" aria-label={t("toolbar.view")} className="flex items-center gap-0.5" data-navbar-view-controls="">{children}</div>, slot);
}

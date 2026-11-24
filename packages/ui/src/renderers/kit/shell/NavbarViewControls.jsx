import { createPortal } from "react-dom";
import { useI18n } from "@cad/ui/i18n";
import { useNavbarViewSlot } from "../../../file-viewer/navbarSlots.js";

/**
 * The view's settings in the file's navbar, at its right end (`file-viewer/navbarSlots.js`), for every kind of file:
 * **Display** (`DisplaySettings.jsx`: the plain cube, a toggle whose card — a 3D view's Projection, Style, Background
 * and Show grid; a board's Side, Mode, in 3D Projection, Style and Background; a drawing's Background — docks under the
 * navbar at the view's right edge, the same on a desktop and a phone), then a 3D view's **Preview**, last — as the
 * navbar's own 28px buttons, their tooltips under them. The picture keeps only the camera's own control in its top-right
 * corner (the cube, or a flat view's zoom; a phone's none: gestures). Where there is no navbar (Preview, which draws its
 * own bar, and a compact view) there is no slot, and nothing is drawn.
 */

/** A navbar view button: the navbar's 28px, its 16px glyph, muted until under the pointer or open (`aria-expanded`). */
export const NAVBAR_VIEW_BUTTON_CLASS = "size-control shrink-0 rounded-md text-muted-foreground hover:text-foreground aria-expanded:bg-accent aria-expanded:text-foreground [&>svg]:size-4!";

/** What each control needs to stand in the navbar: its class, and its tooltip and menu under it, a menu's end on its button's. */
export const NAVBAR_VIEW_PLACE = Object.freeze({ className: NAVBAR_VIEW_BUTTON_CLASS, tooltipSide: "bottom", side: "bottom", align: "end" });

/** `children` drawn in the navbar's view slot, as one group; nothing where there is no slot. */
export default function NavbarViewControls({ children }) {
  const { t } = useI18n();
  const slot = useNavbarViewSlot();
  if (!slot) return null;
  return createPortal(<div role="group" aria-label={t("toolbar.view")} className="flex items-center gap-0.5" data-navbar-view-controls="">{children}</div>, slot);
}

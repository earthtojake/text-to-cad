import { createContext, useContext } from "react";
import { House } from "lucide-react";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { STRIP_BUTTON_CLASS } from "../tools/stripTouch.js";
import { viewCornerLayout } from "./viewportLayout.js";

/**
 * The view's corner, at the bottom-right, where the picture is looked at from: a 3D view's cube
 * (`camera/ViewPlaneControl.js`, the viewport's) with Home at its upper-left (`ViewHome`), as a ViewCube's
 * house is; a flat view's zoom pill (`ZoomControl.jsx`), the one thing there. How the view is looked at —
 * Projection, Display, a board's 2D/3D and Flip — ends the tool strip (`FloatingToolBar.js`'s `views`).
 *
 * A host may anchor the cube at the bottom-left (`--cad-viewport-corner-left`, `viewer-host.md`): then
 * the corner stands there, mirrored as one group (`viewCornerLayout`): Home at the cube's upper-right, the pill
 * at the left, tooltips and menus to the right. The frame reads the side (`viewCornerSide`) and says it to
 * everything in the corner (`ViewCornerSideProvider`, `useViewCornerSide`).
 */

const ViewCornerSideContext = createContext("right");
/** The side the frame's corner stands at, for everything drawn in it: "right" or "left". */
export const ViewCornerSideProvider = ViewCornerSideContext.Provider;
/** @returns {"right" | "left"} */
export const useViewCornerSide = () => useContext(ViewCornerSideContext);
/**
 * The side the host anchors the corner at, read off the frame's root: "left" where it sets
 * `--cad-viewport-corner-left` (a host that anchors the corner at the left), else "right".
 * @param {Element | null} element
 */
export function viewCornerSide(element) {
  if (!element || typeof getComputedStyle !== "function") return "right";
  const left = getComputedStyle(element).getPropertyValue("--cad-viewport-corner-left").trim();
  return left && left !== "auto" ? "left" : "right";
}
/** Which way a corner control's tooltip and menu open, away from the corner's edge, and how a menu aligns on it. */
export function viewCornerAway(side) {
  return side === "left" ? { side: "right", align: "start" } : { side: "left", align: "end" };
}

// Home is the strip's 24px tile with no surface of its own: no fill, border, blur or shadow until the pointer or the
// keyboard is on it, when it takes the strip's hover fill. Its house is ringed in the background's colour (the glow
// Preview's bar gives its name, `PreviewChrome.jsx`), which keeps the glyph legible over the model as on either canvas.
const HOME_CLASS = cn(STRIP_BUTTON_CLASS, "pointer-events-auto absolute z-20",
  "focus-visible:bg-sidebar-accent focus-visible:text-sidebar-accent-foreground",
  "[&>svg]:[filter:drop-shadow(0_0_1px_var(--background))_drop-shadow(0_0_1px_var(--background))]");

/**
 * Home, a 3D view's: the view it opened with (the opening direction, what is shown framed whole: the viewport's
 * `goHome`), as Fusion's and Maya's cubes' Home is. A ghost button snug at the cube's upper-left, the ViewCube's
 * house (Autodesk's, Onshape's), its tooltip beside it, away from the corner; at the upper-right where the host
 * anchors the cube at the left (`viewCornerLayout`'s `home`).
 * @param {{ onHome(): void, disabled?: boolean }} props
 */
export function ViewHome({ onHome, disabled = false }) {
  const { t } = useI18n();
  const side = useViewCornerSide();
  return <ToolbarButton label={t("view.home")} tooltipSide={viewCornerAway(side).side} disabled={disabled} className={HOME_CLASS}
    style={viewCornerLayout(side).home} onClick={onHome} data-view-home="">
    <House aria-hidden="true" />
  </ToolbarButton>;
}

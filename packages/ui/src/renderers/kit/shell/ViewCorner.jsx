import { createContext, useContext } from "react";

/**
 * The view's corner, at the TOP-right (the bottom row is Quick Edit's), where the picture is looked at from: a 3D
 * view's cube (`camera/ViewPlaneControl.js`, the viewport's), a flat view's zoom pill (`ZoomControl.jsx`), and under
 * either the corner's stack (`ViewCornerStack.jsx`): how the view is looked at — Display, Projection and Home, a
 * board's Display, side and 2D/3D.
 *
 * A host may anchor the cube at the top-left (`--cad-viewport-corner-left`, `viewer-host.md`): then
 * the corner stands there, mirrored as one group (`viewCornerLayout`): the pill at the left, tooltips and menus
 * to the right. The frame reads the side (`viewCornerSide`) and says it to everything in the corner
 * (`ViewCornerSideProvider`, `useViewCornerSide`).
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
/** Which way a corner control's tooltip and menu open, away from the corner's edge, and how a menu aligns on it: its
 * top on its button's, as the corner is at the view's top. */
export function viewCornerAway(side) {
  return side === "left" ? { side: "right", align: "start" } : { side: "left", align: "start" };
}

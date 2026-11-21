import { createContext, useContext } from "react";

/**
 * The view's corner, at the TOP-right (the bottom row is Quick Edit's), where the picture is looked at from, its one
 * control the camera's own: a 3D view's cube (`camera/ViewPlaneControl.js`, the viewport's), a flat view's zoom
 * (`ZoomControl.jsx`). How the view is looked at is Display's, its card opened from the navbar (`DisplaySettings.jsx`).
 *
 * A host may anchor the cube at the top-left (`--cad-viewport-corner-left`, `viewer-host.md`): then
 * the corner stands there, mirrored (`viewCornerLayout`): the zoom at the left, its menu opening to the right. The frame reads the side (`viewCornerSide`) and says it to everything in the corner
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

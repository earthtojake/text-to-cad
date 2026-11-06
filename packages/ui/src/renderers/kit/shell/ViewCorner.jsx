import { createContext, useContext } from "react";
import { House } from "lucide-react";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { FLOATING_CHROME_FILL_CLASS } from "../../../lib/floatingSurface.js";
import { STRIP_BUTTON_CLASS } from "../tools/stripTouch.js";
import ProjectionToggle from "./ProjectionToggle.jsx";
import StateButton from "./StateButton.jsx";
import { VIEWPORT_CORNER_GAP_PX, viewCornerLayout } from "./viewportLayout.js";

/**
 * The view's corner: how you look at the model, at the bottom-right, where the cube is (Blender's
 * navigation gizmo and the buttons beside it). A 3D view's is a column of buttons over the
 * cube — Display, Projection, Home — flush with the cube's right face (`ViewCubeColumn`); a flat view,
 * which has no orientation to turn, has its zoom pill there (`ZoomControl.jsx`), and its own controls
 * for how it is looked at (a view that is seen from two sides, or drawn flat or in 3D) in a column over
 * the pill, flush with its right edge (`ViewPillColumn`). A flat view that draws its picture in 3D keeps
 * its pill and its column: the pill zooms the 3D camera, and not one control moves. The top strip
 * is what you do to the model; this corner is how you look at it.
 *
 * Every control here is the tool strip's own button (`FloatingToolBar.js`'s tile, 24px, its icon 14px)
 * carrying the strip's surface itself, without the strip's border and shadow (`VIEW_CORNER_SURFACE_CLASS`:
 * the popover's colour at 90% under a small blur): one 24px square each, with no box round it (Display's
 * menu button, Home; a state the view is looked at in, Projection or a view's own, its state button,
 * `StateButton.jsx`, whose icon is the state on screen), its hover, open, pressed and lit fills states of
 * that one surface, and its tooltip; the zoom pill is one 24px row of them on the same surface. Over an
 * empty canvas they stand a step off it, as the strip does; over the picture or the model the fill,
 * nearly opaque and blurred, keeps their glyphs at full contrast. They stand 4px apart; a column's
 * tooltips and menus open beside it, away from the corner; the pill's above it.
 *
 * A host may anchor the cube at the bottom-left (`--cad-viewport-corner-left`, `viewer-host.md`): then
 * the whole corner stands there, mirrored as one group (`viewCornerLayout`): a column flush with the
 * cube's left face or the pill's left edge, the pill where the cube's drawing ends, tooltips and menus
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
/** Which way a corner control's tooltip and menu open, away from the corner's edge, and how a menu aligns on it. */
export function viewCornerAway(side) {
  return side === "left" ? { side: "right", align: "start" } : { side: "left", align: "end" };
}
/** A corner control that needs the side to draw: `children(side)`. */
export function ViewCornerSided({ children }) {
  return children(useViewCornerSide());
}

/** The corner's one surface: the strip's fill (`FLOATING_CHROME_FILL_CLASS`), without its border and shadow, under each control. */
export const VIEW_CORNER_SURFACE_CLASS = FLOATING_CHROME_FILL_CLASS;

// A corner button as the strip has it: its 24px tile (`STRIP_BUTTON_CLASS`, `ToolbarButton`'s size), lit while its menu is open.
const CORNER_TILE_CLASS = cn(STRIP_BUTTON_CLASS, "aria-expanded:bg-sidebar-accent aria-expanded:text-sidebar-accent-foreground");

/**
 * A corner button's classes, for a `ToolbarButton` (or a trigger built on one): the strip's tile carrying the
 * corner's surface, one 24px square with nothing round it; hovered, open, pressed or lit, the strip's fill takes
 * that surface's place.
 */
export const VIEW_CORNER_BUTTON_CLASS = cn(CORNER_TILE_CLASS, VIEW_CORNER_SURFACE_CLASS);

/** A corner control of several buttons (the zoom pill): one row of them, its height theirs, on the corner's surface, rounded as they are. */
export const VIEW_CORNER_TOOLBAR_CLASS = cn("pointer-events-auto inline-flex shrink-0 items-center rounded-sm", VIEW_CORNER_SURFACE_CLASS);

/** A button of a corner toolbar: the corner button's tile, the toolbar's surface under it. */
export const VIEW_CORNER_TOOLBAR_BUTTON_CLASS = CORNER_TILE_CLASS;

/** The corner's column: its controls stacked, aligned on the corner's edge, a gap between them. */
export function ViewCornerColumn({ children, style, className, ...data }) {
  const side = useViewCornerSide();
  return <div className={cn("pointer-events-auto absolute z-20 flex flex-col", side === "left" ? "items-start" : "items-end", className)}
    style={{ gap: VIEWPORT_CORNER_GAP_PX, ...style }} data-view-corner="" {...data}>{children}</div>;
}

/**
 * A flat view's column over its zoom pill: the view's own controls for how it is looked at (`children`,
 * from the top down), flush with the pill's outer edge, the lowest a gap above it, as a 3D view's column
 * stands over its cube (`viewCornerLayout`'s `pillColumn`). Mirrored with the corner, at the bottom-left
 * flush with the pill's left edge; the order from the top down is the same either side.
 */
export function ViewPillColumn({ children }) {
  return <ViewCornerColumn style={viewCornerLayout(useViewCornerSide()).pillColumn} data-view-pill-column="">{children}</ViewCornerColumn>;
}

/**
 * A state of the view's own as a corner button (`StateButton.jsx`, the one control a state is drawn
 * with): a button of the column, its tooltip beside it, away from the corner, as Display's and
 * Projection's are. Its props are the state button's but the side its tooltip opens on.
 * @param {Omit<import("react").ComponentProps<typeof StateButton>, "tooltipSide" | "className">} props
 */
export function ViewCornerState(props) {
  const away = viewCornerAway(useViewCornerSide());
  return <StateButton {...props} tooltipSide={away.side} className={VIEW_CORNER_BUTTON_CLASS} />;
}

/**
 * A 3D view's column over the cube: what it is displayed as (`display`, the view's own Display button,
 * where it has one: a node, or `display(away)` given which way its tooltip and menu open,
 * `viewCornerAway`), Projection, then Home nearest the cube, the view it opened with. Every 3D view's
 * (`RendererShell.jsx`), so they never differ. It stands over the cube wherever the host anchors it
 * (`viewCornerLayout`'s `cubeColumn`).
 *
 * @param {{ projection: { value: string, onChange(value: string): void }, onHome(): void,
 *   display?: import("react").ReactNode | ((away: { side: string, align: string }) => import("react").ReactNode),
 *   disabled?: boolean }} props
 */
export function ViewCubeColumn({ projection, onHome, display = null, disabled = false }) {
  const { t } = useI18n();
  const side = useViewCornerSide();
  const away = viewCornerAway(side);
  const shown = typeof display === "function" ? display(away) : display;
  return <ViewCornerColumn style={viewCornerLayout(side).cubeColumn}>
    {shown}
    <ProjectionToggle disabled={disabled} projection={projection} tooltipSide={away.side} className={VIEW_CORNER_BUTTON_CLASS} />
    <ToolbarButton label={t("view.home")} tooltipSide={away.side} disabled={disabled} className={VIEW_CORNER_BUTTON_CLASS} onClick={onHome} data-view-home="">
      <House aria-hidden="true" />
    </ToolbarButton>
  </ViewCornerColumn>;
}

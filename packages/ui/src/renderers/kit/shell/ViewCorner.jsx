import { createContext, useContext } from "react";
import { House } from "lucide-react";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { FLOATING_CHROME_FILL_CLASS } from "../../../lib/floatingSurface.js";
import { STRIP_BUTTON_CLASS, STRIP_SHAPE_CLASS } from "../tools/stripTouch.js";
import ProjectionToggle from "./ProjectionToggle.jsx";
import { VIEWPORT_CORNER_GAP_PX, viewCornerLayout } from "./viewportLayout.js";

/**
 * The view's corner: how you look at the model, at the bottom-right, where the cube is (Blender's
 * navigation gizmo and the buttons beside it). A 3D view's is a column of buttons over the
 * cube — Display, Projection, Home — flush with the cube's right face (`ViewCubeColumn`); a flat view,
 * which has no orientation to turn, has its zoom pill there (`ZoomControl.jsx`). A view with controls
 * of its own for how it is looked at (a view that is seen from two sides, or drawn flat or in 3D) puts
 * them on the corner's bottom row, LEFT of the pill or the cube (`ViewCornerRow`): a fixed place, so
 * when the pill becomes the cube (a flat view turning into a 3D one) not one of them moves. The top strip
 * is what you do to the model; this corner is how you look at it.
 *
 * Every control here is the tool strip's tiles (`FloatingToolBar.js`) on the strip's own surface
 * without its border and its shadow (`VIEW_CORNER_SURFACE_CLASS`: the popover's colour at 90% under a
 * small blur): a single button is a one-button toolbar (`ViewCornerTile`), a choice between a few
 * (`ViewCornerSwitch`) and the zoom pill a small toolbar of them, its segments the strip's buttons, with
 * their hover, pressed, open and on states and their tooltips. Over an empty canvas they stand a step
 * off it, as the strip does; over the picture or the model the fill, nearly opaque and blurred, keeps
 * their glyphs at full contrast. Their menus open to the left and up.
 *
 * A host may anchor the cube at the bottom-left (`--cad-viewport-corner-left`, `viewer-host.md`): then
 * the whole corner stands there, mirrored as one group (`viewCornerLayout`): the column flush with the
 * cube's left face, the pill 8px from the left, the row right of it in the order it reads from the
 * corner outwards, tooltips and menus to the right. The frame reads the side (`viewCornerSide`) and says
 * it to everything in the corner (`ViewCornerSideProvider`, `useViewCornerSide`).
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

/** The corner's one surface: the strip's (`FLOATING_CHROME_SURFACE_CLASS`) without its border and shadow. */
export const VIEW_CORNER_SURFACE_CLASS = FLOATING_CHROME_FILL_CLASS;

/** A corner control's box: the strip's shape (4px in, 4px between its tiles) on the corner's surface. */
export const VIEW_CORNER_TOOLBAR_CLASS = cn("pointer-events-auto inline-flex shrink-0", STRIP_SHAPE_CLASS, VIEW_CORNER_SURFACE_CLASS);

/** A corner button's classes, for a `ToolbarButton` (or a trigger built on one): the strip's own tile, lit while its menu is open. */
export const VIEW_CORNER_BUTTON_CLASS = cn(STRIP_BUTTON_CLASS, "aria-expanded:bg-sidebar-accent aria-expanded:text-sidebar-accent-foreground");

/** A single corner button as a one-button toolbar: the button (`VIEW_CORNER_BUTTON_CLASS`) in the corner's box. */
export function ViewCornerTile({ children }) {
  return <div className={VIEW_CORNER_TOOLBAR_CLASS} data-view-corner-tile="">{children}</div>;
}

/** The corner's column: its buttons stacked, aligned on the corner's edge, a gap between them. */
export function ViewCornerColumn({ children, style, className }) {
  const side = useViewCornerSide();
  return <div className={cn("pointer-events-auto absolute z-20 flex flex-col", side === "left" ? "items-start" : "items-end", className)}
    style={{ gap: VIEWPORT_CORNER_GAP_PX, ...style }} data-view-corner="">{children}</div>;
}

/**
 * The corner's bottom row, beside the pill or the cube: its controls side by side, from a fixed place
 * by the pill (`viewCornerLayout`'s `row`), each of a fixed width, so none moves when the pill becomes
 * the cube. Its controls are given in the order they read from the corner's far side inwards (at the
 * bottom-right, left to right); at the bottom-left the row runs the other way, so it reads from the
 * corner outwards there too.
 */
export function ViewCornerRow({ children, style = null }) {
  const side = useViewCornerSide();
  return <div className="pointer-events-auto absolute z-20 flex items-center" style={{ gap: VIEWPORT_CORNER_GAP_PX, ...viewCornerLayout(side).row, ...style }}
    data-view-corner="" data-view-corner-row="" data-side={side}>{children}</div>;
}

// A switch's segments: the strip's buttons drawn out to share its width, words in place of a glyph.
const SWITCH_SEGMENT_CLASS = "w-auto min-w-0 flex-1 px-1 text-tiny font-medium";

/**
 * A choice between a few ways of looking, as a small toolbar in the corner: its options side by side,
 * each a strip button, the one chosen on (the strip's pressed fill); a press on another chooses it. The
 * words say it all, so no tooltip.
 *
 * @param {{ label: string, options: { value: string, label: string }[], value: string, onChange(value: string): void,
 *   disabled?: boolean, className?: string, data?: object }} props
 *   `className`: its width (`w-[6.5rem]`); `data`: its own data attributes, and each option's
 *   (`option(value)`), so a host or a test can name it.
 */
export function ViewCornerSwitch({ label, options, value, onChange, disabled = false, className = "w-[6.5rem]", data = null, option = null }) {
  return <div role="radiogroup" aria-label={label} className={cn(VIEW_CORNER_TOOLBAR_CLASS, className)} {...data}>
    {options.map(choice => <ToolbarButton key={choice.value} label={choice.label} tooltip={false} active={choice.value === value} role="radio"
      aria-checked={choice.value === value} disabled={disabled} className={SWITCH_SEGMENT_CLASS} {...option?.(choice.value)}
      onClick={() => { if (choice.value !== value) onChange(choice.value); }}>{choice.label}</ToolbarButton>)}
  </div>;
}

/**
 * A 3D view's column over the cube: what it is displayed as (`display`, the view's own Display button,
 * where it has one: a node, or `display(away)` given which way its tooltip and menu open,
 * `viewCornerAway`), Projection, then Home nearest the cube, the view it opened with. Every 3D view's,
 * a renderer's own frame or a flat view's frame showing a 3D view alike, so they never differ. It stands
 * over the cube wherever the host anchors it (`viewCornerLayout`'s `cubeColumn`).
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
    {shown ? <ViewCornerTile>{shown}</ViewCornerTile> : null}
    <ViewCornerTile><ProjectionToggle disabled={disabled} projection={projection} tooltipSide={away.side} className={VIEW_CORNER_BUTTON_CLASS} /></ViewCornerTile>
    <ViewCornerTile>
      <ToolbarButton label={t("view.home")} tooltipSide={away.side} disabled={disabled} className={VIEW_CORNER_BUTTON_CLASS} onClick={onHome} data-view-home="">
        <House aria-hidden="true" />
      </ToolbarButton>
    </ViewCornerTile>
  </ViewCornerColumn>;
}

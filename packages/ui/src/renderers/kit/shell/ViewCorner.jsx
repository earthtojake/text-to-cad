import { cn } from "@cad/ui/utils";
import { VIEWPORT_CORNER_GAP_PX } from "./viewportLayout.js";

/**
 * The view's corner: how you look at the model, at the bottom-right, where the cube is (Blender's
 * navigation gizmo and the round buttons under it). A 3D view's is a column of round buttons over the
 * cube — Display, Zoom to fit, Projection — flush with the cube's right face; a flat view, which has no
 * orientation to turn, has its zoom pill there (`ZoomControl.jsx`), and over it its own view buttons (a
 * board's Display). The top strip is what you do to the model; this corner is how you look at it.
 *
 * Every control here sits on one surface (`VIEW_CORNER_SURFACE_CLASS`): the canvas itself, nearly
 * opaque and lightly blurred, under the corner's faint wash, no border and no shadow. Over an empty
 * canvas it is the canvas and the wash, so the corner reads as part of the view rather than a
 * toolbar; over the picture or the model it keeps its glyphs at full contrast, what passes under it
 * a faint hint. Their menus open to the left and up.
 */

/**
 * The corner's surface: the canvas at 85% under a light blur (the background colour), the wash over
 * it (a background image in `--view-corner-wash`, the foreground at 9%). A state that strengthens the
 * wash sets the variable to `VIEW_CORNER_WASH_STRONG`'s 16%, so the backing stays under it.
 */
export const VIEW_CORNER_SURFACE_CLASS = "bg-canvas/85 backdrop-blur-[4px] "
  + "bg-[image:linear-gradient(var(--view-corner-wash),var(--view-corner-wash))] "
  + "[--view-corner-wash:color-mix(in_oklab,var(--foreground)_9%,transparent)]";

/** A round corner button's classes, for a `ToolbarButton` (or a trigger built on one). Hovered, open or
 * on, its wash is the stronger one; the button's own state fills give way to the surface's backing. */
export const VIEW_CORNER_BUTTON_CLASS = `relative size-7 rounded-full border-0 ${VIEW_CORNER_SURFACE_CLASS} text-muted-foreground shadow-none `
  + "hover:bg-canvas/85 dark:hover:bg-canvas/85 hover:text-foreground aria-expanded:text-foreground data-[variant=secondary]:bg-canvas/85 "
  + "data-[variant=secondary]:hover:bg-canvas/85 data-[variant=secondary]:text-foreground "
  + "hover:[--view-corner-wash:color-mix(in_oklab,var(--foreground)_16%,transparent)] "
  + "aria-expanded:[--view-corner-wash:color-mix(in_oklab,var(--foreground)_16%,transparent)] "
  + "data-[variant=secondary]:[--view-corner-wash:color-mix(in_oklab,var(--foreground)_16%,transparent)] [&>svg]:size-3.5!";

/** The corner's column: its buttons stacked, right-aligned, a gap between them. */
export function ViewCornerColumn({ children, style, className }) {
  return <div className={cn("pointer-events-auto absolute z-20 flex flex-col items-end", className)}
    style={{ gap: VIEWPORT_CORNER_GAP_PX, ...style }} data-view-corner="">{children}</div>;
}

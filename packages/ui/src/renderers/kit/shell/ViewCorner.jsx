import { cn } from "@cad/ui/utils";
import { VIEWPORT_CORNER_GAP_PX } from "./viewportLayout.js";

/**
 * The view's corner: how you look at the model, at the bottom-right, where the cube is (Blender's
 * navigation gizmo and the round buttons under it). A 3D view's is a column of round buttons over the
 * cube — Display, Zoom to fit, Projection — flush with the cube's right face; a flat view, which has no
 * orientation to turn, has its zoom pill there (`ZoomControl.jsx`), and over it its own view buttons (a
 * board's Display). The top strip is what you do to the model; this corner is how you look at it.
 *
 * The buttons are see-through discs on the canvas, no border and no surface of their own, so the
 * corner reads as part of the view rather than a toolbar. Their menus open to the left and up.
 */

/** A round corner button's classes, for a `ToolbarButton` (or a trigger built on one). */
export const VIEW_CORNER_BUTTON_CLASS = "relative size-7 rounded-full border-0 bg-foreground/[0.09] text-muted-foreground shadow-none "
  + "hover:bg-foreground/[0.16] hover:text-foreground aria-expanded:bg-foreground/[0.16] aria-expanded:text-foreground "
  + "data-[variant=secondary]:bg-foreground/[0.16] data-[variant=secondary]:text-foreground [&>svg]:size-3.5!";

/** The corner's column: its buttons stacked, right-aligned, a gap between them. */
export function ViewCornerColumn({ children, style, className }) {
  return <div className={cn("pointer-events-auto absolute z-20 flex flex-col items-end", className)}
    style={{ gap: VIEWPORT_CORNER_GAP_PX, ...style }} data-view-corner="">{children}</div>;
}

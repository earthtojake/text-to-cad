import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { useViewCornerSide, viewCornerAway } from "./ViewCorner.jsx";
import { viewCornerLayout } from "./viewportLayout.js";

/**
 * A corner stack button: 24px, its icon 14px at the muted foreground (62%), on no tile, border or shadow at
 * rest; under the pointer a faint fill (the foreground at 9%); on (its menu open) the foreground at 14% and the
 * icon at full strength. Over the model, a halo of the theme's background round the glyph (three soft drop
 * shadows, 1, 2 and 3px) keeps it readable on a dark part in the light theme and on a light part in the dark,
 * where a bare icon vanished.
 */
export const CORNER_BUTTON_CLASS = [
  "size-6 rounded-md text-foreground/62 shadow-none hover:bg-foreground/9 dark:hover:bg-foreground/9 hover:text-foreground",
  "aria-expanded:bg-foreground/14 aria-expanded:text-foreground data-[state=open]:bg-foreground/14 data-[state=open]:text-foreground",
  "[&>svg]:size-3.5! [&>svg]:[filter:drop-shadow(0_0_1px_var(--background))_drop-shadow(0_0_2px_var(--background))_drop-shadow(0_0_3px_var(--background))]"
].join(" ");

/**
 * The view's controls in its corner (a 3D view's Display, then Projection, then Home), as Figma keeps its view
 * settings out of its toolbar: a column of single buttons, 4px apart, with no group surface, under the cube at the
 * view's top-right, its right edge at the corner's inset (12px, the zoom pill's: `viewCornerLayout`'s `stack`), 4px
 * under the cube's box. Their menus and tooltips open to the side away from the corner (`viewCornerAway`: the left),
 * a menu's top on its button's. Where the host anchors the corner at the left, the stack stands there, mirrored. A
 * flat view that has view controls for its corner (a board's Display, side and 2D/3D) stands them under its zoom pill
 * instead (`under: "pill"`), at the same inset. A phone has none: its view's controls are rows of the strip's More.
 *
 * Where the view's settings are the navbar's (`NavbarViewControls.jsx`), the cube keeps Home alone, against the cube's
 * drawing at its top-left, 4px from it and top-aligned with its top face (`under: "home"`, `viewCornerLayout`'s `home`),
 * never over the cube, so the two read as one.
 *
 * `children` are drawn from a render prop with what each button needs: `({ className, tooltipSide, side, align })`.
 * @param {{ children(placement: { className: string, tooltipSide: "left" | "right", side: "left" | "right", align: "start" | "end" }): import("react").ReactNode }} props
 */
export default function ViewCornerStack({ children, under = "cube" }) {
  const { t } = useI18n();
  const corner = useViewCornerSide();
  const away = viewCornerAway(corner);
  return <div role="group" aria-label={t("toolbar.view")} data-view-corner-stack=""
    // Home stands a little over the cube's box, against its drawing: over the box, so the box never takes its press.
    className={cn("pointer-events-auto absolute flex flex-col items-center gap-1", under === "home" ? "z-40" : "z-20")} style={viewCornerLayout(corner)[{ pill: "stackUnderPill", home: "home", pillHome: "pillHome" }[under] ?? "stack"]}
    data-view-corner-home={under === "home" || under === "pillHome" ? "" : undefined}>
    {children({ className: CORNER_BUTTON_CLASS, tooltipSide: away.side, side: away.side, align: away.align })}
  </div>;
}

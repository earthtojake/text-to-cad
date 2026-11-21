import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { useViewCornerSide, viewCornerAway } from "./ViewCorner.jsx";
import { CORNER_TILE_PX, CUBE_ROW_FROM_BOX_PX, CUBE_ROW_WIDTH_PX, viewCornerLayout } from "./viewportLayout.js";

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
 * A flat view's controls in its corner, as Figma keeps its view settings out of its toolbar: a column of single
 * buttons, 4px apart, with no group surface, at the corner's inset (12px, the zoom pill's: `viewCornerLayout`), under
 * its zoom pill (`under: "pill"`: a board's Display, side and 2D/3D where its host has no navbar), or beside it
 * (`under: "pillHome"`: a board's 3D Home), or where a cube would stand (`under: "cube"`). Their menus and tooltips open
 * to the side away from the corner (`viewCornerAway`: the left), a menu's top on its button's. Where the host anchors
 * the corner at the left, the stack stands there, mirrored. A phone has none: its view's controls are rows of the
 * strip's More. A 3D view's corner is the cube and its row under it (`CubeRow`, below).
 *
 * `children` are drawn from a render prop with what each button needs: `({ className, tooltipSide, side, align })`.
 * @param {{ children(placement: { className: string, tooltipSide: "left" | "right", side: "left" | "right", align: "start" | "end" }): import("react").ReactNode }} props
 */
export default function ViewCornerStack({ children, under = "cube" }) {
  const { t } = useI18n();
  const corner = useViewCornerSide();
  const away = viewCornerAway(corner);
  return <div role="group" aria-label={t("toolbar.view")} data-view-corner-stack=""
    className="pointer-events-auto absolute z-20 flex flex-col items-center gap-1" style={viewCornerLayout(corner)[{ pill: "stackUnderPill", pillHome: "pillHome" }[under] ?? "stack"]}
    data-view-corner-home={under === "pillHome" ? "" : undefined}>
    {children({ className: CORNER_BUTTON_CLASS, tooltipSide: away.side, side: away.side, align: away.align })}
  </div>;
}

/**
 * A 3D view's row under its cube (`viewCornerLayout`'s `cubeRow`): Home, then View, 24px tiles 4px apart with no
 * group surface, centred under the cube as drawn, so the camera's controls and how the file is looked at stand in one
 * place. `children` are drawn from a render prop with what each needs: `({ className, tooltipSide, menu })`, `menu` the
 * View menu's placement (`ViewMenu`'s `placement`): under the row, its outer edge on the cube box's
 * (`CUBE_ROW_FROM_BOX_PX` past the row's), so the open menu never covers the cube.
 * @param {{ children(placement: { className: string, tooltipSide: "bottom", menu: { align: "start" | "end", alignOffset: number } }): import("react").ReactNode }} props
 */
export function CubeRow({ children }) {
  const { t } = useI18n();
  const corner = useViewCornerSide();
  const away = viewCornerAway(corner);
  // View is the row's second tile: at the right its outer edge is the row's; mirrored at the left, a tile and a gap in.
  const menu = corner === "left" ? { align: "start", alignOffset: -(CUBE_ROW_FROM_BOX_PX + CUBE_ROW_WIDTH_PX - CORNER_TILE_PX) }
    : { align: "end", alignOffset: -CUBE_ROW_FROM_BOX_PX };
  return <div role="group" aria-label={t("toolbar.view")} data-view-corner-stack="" data-view-cube-row=""
    className="pointer-events-auto absolute z-20 flex items-center gap-1" style={viewCornerLayout(corner).cubeRow}>
    {children({ className: CORNER_BUTTON_CLASS, tooltipSide: "bottom", menu, away })}
  </div>;
}

/**
 * A phone's corner (no cube, no zoom pill): one tile at the corner's inset (`viewCornerLayout`'s `pill`), the phone's
 * 36px, as a 3D view's View stands there (`RendererShell.jsx`). `children(className)` draws it.
 */
export function CornerTile({ children }) {
  const { t } = useI18n();
  const corner = useViewCornerSide();
  return <div role="group" aria-label={t("toolbar.view")} data-view-corner-stack="" data-view-corner-tile=""
    className="pointer-events-auto absolute z-20 flex" style={viewCornerLayout(corner).pill}>
    {children(CORNER_BUTTON_CLASS)}
  </div>;
}

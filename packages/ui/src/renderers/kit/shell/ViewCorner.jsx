import { House } from "lucide-react";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import ProjectionToggle from "./ProjectionToggle.jsx";
import { VIEWPORT_CORNER_GAP_PX, VIEWPORT_CORNER_ROW_POSITION } from "./viewportLayout.js";

/**
 * The view's corner: how you look at the model, at the bottom-right, where the cube is (Blender's
 * navigation gizmo and the round buttons under it). A 3D view's is a column of round buttons over the
 * cube — Display, Projection, Home — flush with the cube's right face (`ViewCubeColumn`); a flat view,
 * which has no orientation to turn, has its zoom pill there (`ZoomControl.jsx`). A view with controls
 * of its own for how it is looked at (a view that is seen from two sides, or drawn flat or in 3D) puts
 * them on the corner's bottom row, LEFT of the pill or the cube (`ViewCornerRow`): a fixed place, so
 * when the pill becomes the cube (a flat view turning into a 3D one) not one of them moves. The top strip
 * is what you do to the model; this corner is how you look at it.
 *
 * Every control here sits on one surface (`VIEW_CORNER_SURFACE_CLASS`): the canvas itself, nearly
 * opaque and lightly blurred, under the corner's faint wash, no border and no shadow. Over an empty
 * canvas it is the canvas and the wash, so the corner reads as part of the view rather than a
 * toolbar; over the picture or the model it keeps its glyphs at full contrast, what passes under it
 * a faint hint; a choice between two is a capsule on the same surface (`ViewCornerSwitch`). Their menus
 * open to the left and up.
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

/**
 * The corner's bottom row, left of the pill or the cube: its controls side by side, right-aligned at a
 * fixed place (`VIEWPORT_CORNER_ROW_POSITION`), each of a fixed width, so none moves when the pill
 * becomes the cube.
 */
export function ViewCornerRow({ children, style = null }) {
  return <div className="pointer-events-auto absolute z-20 flex flex-row items-center" style={{ gap: VIEWPORT_CORNER_GAP_PX, ...VIEWPORT_CORNER_ROW_POSITION, ...style }}
    data-view-corner="" data-view-corner-row="">{children}</div>;
}

// A switch's halves: the one chosen raised on the corner's stronger fill.
const SWITCH_HALF_CLASS = "h-7 flex-1 rounded-full text-tiny font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/45 disabled:opacity-50 "
  + "aria-checked:bg-foreground/[0.16] aria-checked:text-foreground text-muted-foreground hover:text-foreground";

/**
 * A choice between a few ways of looking, as a capsule of the corner's fill: its options side by side,
 * the one chosen raised; a press on another chooses it. The words say it all, so no tooltip.
 *
 * @param {{ label: string, options: { value: string, label: string }[], value: string, onChange(value: string): void,
 *   disabled?: boolean, className?: string, data?: object }} props
 *   `className`: its width (`w-[6.5rem]`, the pill's); `data`: its own data attributes, and each option's
 *   (`option(value)`), so a host or a test can name it.
 */
export function ViewCornerSwitch({ label, options, value, onChange, disabled = false, className = "w-[6.5rem]", data = null, option = null }) {
  return <div role="radiogroup" aria-label={label} className={cn("pointer-events-auto inline-flex h-7 shrink-0 items-center rounded-full", VIEW_CORNER_SURFACE_CLASS, className)}
    {...data}>
    {options.map(choice => <button key={choice.value} type="button" role="radio" aria-checked={choice.value === value} disabled={disabled}
      className={SWITCH_HALF_CLASS} {...option?.(choice.value)} onClick={() => { if (choice.value !== value) onChange(choice.value); }}>{choice.label}</button>)}
  </div>;
}

/**
 * A 3D view's column over the cube: what it is displayed as (`display`, the view's own Display button,
 * where it has one), Projection, then Home nearest the cube, the view it opened with. Every 3D view's,
 * a renderer's own frame or a flat view's frame showing a 3D view alike, so they never differ.
 *
 * @param {{ projection: { value: string, onChange(value: string): void }, onHome(): void, display?: import("react").ReactNode,
 *   disabled?: boolean, style: object }} props
 */
export function ViewCubeColumn({ projection, onHome, display = null, disabled = false, style }) {
  const { t } = useI18n();
  return <ViewCornerColumn style={style}>
    {display}
    <ProjectionToggle disabled={disabled} projection={projection} tooltipSide="left" className={VIEW_CORNER_BUTTON_CLASS} />
    <ToolbarButton label={t("view.home")} tooltipSide="left" disabled={disabled} className={VIEW_CORNER_BUTTON_CLASS} onClick={onHome} data-view-home="">
      <House aria-hidden="true" />
    </ToolbarButton>
  </ViewCornerColumn>;
}

import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useI18n } from "@cad/ui/i18n";
import { OrthographicProjectionIcon, PerspectiveProjectionIcon } from "../camera/ProjectionModeIcons.js";
import { useStripButtonClass } from "../tools/FloatingToolBar.js";

const ICONS = Object.freeze({ orthographic: OrthographicProjectionIcon, perspective: PerspectiveProjectionIcon });

/** The projection a click on Projection's tile switches to: the other one. */
export const otherProjection = value => (value === "perspective" ? "orthographic" : "perspective");

/**
 * The camera's projection, a tile of its own beside Display's (every 3D view has one, while not every
 * view has display modes to choose): it shows the projection on screen, and a click switches to the
 * other, Orthographic to Perspective and back, as Blender's and Onshape's projection toggles do; its
 * tooltip says which it switches to. On a phone's strip with no room for the tile, More's row does the
 * same (`RendererShell.jsx`).
 *
 * @param {{ projection: { value: string, onChange(value: string): void }, disabled?: boolean, tooltipSide?: "top" | "bottom" }} props
 */
export default function ProjectionToggle({ projection, disabled = false, tooltipSide = "top", className = null }) {
  const { t } = useI18n();
  const stripClass = useStripButtonClass();
  const current = ICONS[projection.value] ? projection.value : "orthographic";
  const Icon = ICONS[current];
  const next = otherProjection(current);
  return <ToolbarButton label={t("projection.current", { mode: t(`projection.${current}`) })} tooltip={t("projection.switchTo", { mode: t(`projection.${next}`) })}
    tooltipSide={tooltipSide} disabled={disabled} className={className || stripClass} data-projection={current} onClick={() => projection.onChange(next)}>
    <Icon />
  </ToolbarButton>;
}

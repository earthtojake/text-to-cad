import { useI18n } from "@cad/ui/i18n";
import { OrthographicProjectionIcon, PerspectiveProjectionIcon } from "../camera/ProjectionModeIcons.js";
import StateButton from "./StateButton.jsx";

const ICONS = Object.freeze({ orthographic: OrthographicProjectionIcon, perspective: PerspectiveProjectionIcon });

/** The projection a click on Projection's tile switches to: the other one. */
export const otherProjection = value => (value === "perspective" ? "orthographic" : "perspective");

/**
 * The camera's projection, a tile of its own on the strip, before Display's (every 3D view has one, while not
 * every view has display modes to choose): the view's one state button (`StateButton.jsx`). It shows the
 * projection on screen, and a click switches to the other, Orthographic to Perspective and back, as
 * Blender's viewport gizmo and Flux's camera options do; its name says the projection on screen
 * ("Projection: Orthographic"), its tooltip the one it switches to. On a phone's strip with no room for
 * the tile, More's row does the same (`RendererShell.jsx`).
 *
 * @param {{ projection: { value: string, onChange(value: string): void }, disabled?: boolean, tooltipSide?: "top" | "bottom" | "left" | "right" }} props
 */
export default function ProjectionToggle({ projection, disabled = false, tooltipSide = "top" }) {
  const { t } = useI18n();
  const current = ICONS[projection.value] ? projection.value : "orthographic";
  const next = otherProjection(current);
  return <StateButton icon={ICONS[current]} label={t("projection.current", { mode: t(`projection.${current}`) })}
    tooltip={t("projection.switchTo", { mode: t(`projection.${next}`) })} tooltipSide={tooltipSide} disabled={disabled}
    data-projection={current} onPress={() => projection.onChange(next)} />;
}

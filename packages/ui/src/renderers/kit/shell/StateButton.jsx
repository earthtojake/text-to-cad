import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { useStripButtonClass } from "../tools/FloatingToolBar.js";

/**
 * A state of how the view is looked at, as one icon button a press switches: the one control every
 * such state is drawn with — the camera's Projection (`ProjectionToggle.jsx`), and a view's own (a
 * picture drawn flat or in 3D, the side it is seen from) — as Blender's viewport gizmo shows its
 * projection and Flux's camera options theirs. Its icon is the state on screen. Its name says that
 * state ("Projection: Orthographic"), so the name changes with it, which makes it a plain button with no
 * `aria-pressed` (the W3C APG button pattern: a toggle keeps one name). Its tooltip says what a press
 * does ("Switch to Perspective"), with the key that does the same (`shortcut`, muted after it, as the
 * strip's tooltips show theirs). `lit`: a state a person may lose track of (a view seen from its other
 * side), drawn in the strip's pressed fill for as long as it holds, its tooltip kept.
 *
 * It is a tile of the strip in hand (`useStripButtonClass`), or of the view's corner (`className`,
 * `ViewCorner.jsx`'s `VIEW_CORNER_BUTTON_CLASS`, in a `ViewCornerTile`), the same size whatever its
 * state, so nothing round it moves when the state does.
 *
 * @param {{ icon: import("react").ComponentType<{ "aria-hidden"?: boolean | "true" }>, label: string, tooltip: string,
 *   onPress(): void, shortcut?: string, lit?: boolean, disabled?: boolean, tooltipSide?: "top" | "right" | "bottom" | "left",
 *   className?: string | null } & Record<`data-${string}`, string>} props
 *   `data-*`: its own data attributes, which say the state to a host or a test (`data-projection="orthographic"`).
 */
export default function StateButton({ icon: Icon, label, tooltip, onPress, shortcut = "", lit = false, disabled = false, tooltipSide = "top",
  className = null, ...data }) {
  const stripClass = useStripButtonClass();
  return <ToolbarButton label={label} tooltip={tooltip} shortcut={shortcut} lit={lit} tooltipSide={tooltipSide} disabled={disabled}
    className={className || stripClass} onClick={() => onPress()} data-state-button="" {...data}>
    <Icon aria-hidden="true" />
  </ToolbarButton>;
}

import { Scan } from "lucide-react";
import { useI18n } from "@cad/ui/i18n";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { cn } from "@cad/ui/utils";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { STRIP_BUTTON_CLASS, TOUCH_STRIP_BUTTON_CLASS } from "../tools/stripTouch.js";
import { TOOL_SHORTCUTS } from "../tools/toolShortcuts.js";
import { VIEWPORT_CUBE_BOTTOM_PX, VIEWPORT_INSET_PX } from "./viewportLayout.js";

/**
 * Zoom to fit, the one button every view has for its framing, in one place: the view's bottom-right
 * corner, where its navigation is. A 3D view's stands at the view cube's left, its foot on the cube's
 * (`beside`: the room the cube takes from the right edge); a flat view, which has no orientation to
 * turn, has the button alone in the corner. Its tooltip names its key (F); a double-click on empty
 * space and the view's menu fit too. A single icon on the floating chrome's surface, as the panel's
 * pill is, and no zoom readout.
 *
 * @param {{ onFit(): void, beside?: string | null, touch?: boolean, disabled?: boolean }} props
 */
export default function ZoomFitButton({ onFit, beside = null, touch = false, disabled = false }) {
  const { t } = useI18n();
  return <div className={cn("pointer-events-auto absolute z-20 inline-flex rounded-md p-1", FLOATING_CHROME_SURFACE_CLASS)}
    style={{ right: beside ?? `${VIEWPORT_INSET_PX}px`, bottom: beside ? `calc(${VIEWPORT_CUBE_BOTTOM_PX}px + var(--cad-viewport-corner-bottom, 0px))` : `${VIEWPORT_INSET_PX}px` }}
    data-zoom-fit="">
    <ToolbarButton label={t("menu.zoomToFit")} shortcut={touch ? "" : TOOL_SHORTCUTS.fit} tooltipSide="top" disabled={disabled}
      className={touch ? TOUCH_STRIP_BUTTON_CLASS : STRIP_BUTTON_CLASS} onClick={onFit}>
      <Scan aria-hidden="true" />
    </ToolbarButton>
  </div>;
}

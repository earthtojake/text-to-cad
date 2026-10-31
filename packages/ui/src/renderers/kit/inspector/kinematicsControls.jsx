import { ChevronDown, RotateCcw } from "lucide-react";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger
} from "@text-to-cad/ui/primitives/dropdown-menu";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { TOOL_PANEL_BUTTON_CLASS, ToolPanelHeadAction } from "../tools/ToolPanel.jsx";
import { useControlUsage } from "../../../usage/controls.js";
import { useI18n } from "@text-to-cad/ui/i18n";

export const NO_PRESET_VALUE = "__none__";
export const DEFAULT_POSE_VALUE = "__default__";

export function positionValuesAreDefault(values, defaults) {
  return Object.entries(defaults || {}).every(([key, value]) => {
    const current = values?.[key] ?? value;
    return typeof value === "number" && typeof current === "number"
      ? Math.abs(current - value) <= 1e-6 : current === value;
  });
}

/**
 * Position's Pose, the first row of its body, full width over the joints: the pose in hand as a
 * dropdown ("Custom" while the joints are set by hand) — Default first where the section
 * can reset, then the named poses. Reset, the way back to the default pose, is in the section's
 * heading before its X (`ToolPanelHeadAction`), idle while the model is there. Nothing where there
 * is neither to choose. `disabled`: shown, not chosen from (while a motion owns the pose).
 */
export function KinematicsPoseRow({ poses = [], activeValue, onSelect, onReset, disabled = false }) {
  const usage = useControlUsage();
  const { t } = useI18n();
  if (!poses.length && !onReset) return null;
  const reset = () => { usage.used("position_reset"); onReset?.(); };
  const options = [...(onReset ? [{ value: DEFAULT_POSE_VALUE, label: t("pose.default") }] : []), ...poses];
  const active = options.find(pose => pose.value === activeValue);
  const label = active?.label || t("pose.custom");
  // A full-width row over the joints, on their edges, as the Animation section's routine is.
  return <div className="flex h-8 items-center px-2" data-pose-row="">
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label={t("pose.current", { pose: label })} data-pose-menu="" disabled={disabled}
          className="flex h-6 w-full min-w-0 items-center justify-between gap-1 rounded-md border border-input bg-transparent px-2 text-left text-tiny shadow-xs outline-none focus-visible:ring-2 focus-visible:ring-ring/45 aria-expanded:bg-accent disabled:opacity-50 dark:bg-input/30 dark:hover:bg-input/50">
          <span className="min-w-0 truncate">{label}</span>
          <ChevronDown className="size-3 shrink-0 opacity-60" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={4} collisionPadding={8} aria-label={t("pose.label")}
        className={cn(FLOATING_SURFACE_CLASS, "min-w-(--radix-dropdown-menu-trigger-width) data-[state=closed]:animate-none!")}>
        <DropdownMenuRadioGroup value={active?.value || NO_PRESET_VALUE}
          onValueChange={value => { if (value === DEFAULT_POSE_VALUE) { reset(); return; } usage.used("position_preset"); onSelect?.(value); }}>
          {options.map(option => <DropdownMenuRadioItem key={option.value} value={option.value}>
            <span className="min-w-0 truncate">{option.label}</span>
          </DropdownMenuRadioItem>)}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
    {onReset ? <ToolPanelHeadAction>
      <TooltipHint content={t("pose.reset")} side="bottom">
        <button type="button" aria-label={t("pose.reset")} data-pose-reset="" disabled={disabled || activeValue === DEFAULT_POSE_VALUE} onClick={reset}
          className={cn(TOOL_PANEL_BUTTON_CLASS, "disabled:pointer-events-none disabled:opacity-40")}><RotateCcw className="size-3" aria-hidden="true" /></button>
      </TooltipHint>
    </ToolPanelHeadAction> : null}
  </div>;
}

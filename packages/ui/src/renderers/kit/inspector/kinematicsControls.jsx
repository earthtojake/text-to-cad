import { TooltipHint } from "@hardcore/ui/primitives/tooltip";
import { RotateCcw } from "lucide-react";
import { Button } from "@hardcore/ui/primitives/button";
import { FileSheetSelectRow, FileSheetControlRow } from "./FileSheet.js";

export const NO_PRESET_VALUE = "__none__";
export const DEFAULT_POSE_VALUE = "__default__";

export function positionValuesAreDefault(values, defaults) {
  return Object.entries(defaults || {}).every(([key, value]) => {
    const current = values?.[key] ?? value;
    return typeof value === "number" && typeof current === "number"
      ? Math.abs(current - value) <= 1e-6 : current === value;
  });
}

/** One compact header shared by STEP and robot position controls. */
export function KinematicsPoseRow({ poses = [], activeValue, onSelect, onReset, disabled = false, label = "Pose", ariaLabel = "Pose" }) {
  const hasPoses = poses.length > 0;
  if (!hasPoses && !onReset) return null;
  const options = [...(onReset ? [{ value: DEFAULT_POSE_VALUE, label: "Default" }] : []), ...poses];
  const active = options.find(pose => pose.value === activeValue);
  return <div data-position-header="">
    <FileSheetControlRow className={hasPoses ? "space-y-0 pb-1" : undefined} label={hasPoses ? label : "Position"}
      trailing={<MotionResetButton onReset={onReset} disabled={disabled} />}>
      {hasPoses ? <FileSheetSelectRow hideLabel className="px-0" value={active?.value || NO_PRESET_VALUE}
        onValueChange={value => value === DEFAULT_POSE_VALUE ? onReset?.() : onSelect?.(value)}
        ariaLabel={ariaLabel} disabled={disabled} triggerContent={<span className="truncate">{active?.label || "Custom"}</span>}
        options={options} /> : null}
    </FileSheetControlRow>
  </div>;
}

/** Reset stays beside the pose selector, above the joint list. */
export function MotionResetButton({ onReset, disabled = false }) {
  if (!onReset) return null;
  return <TooltipHint content="Reset motion"><Button variant="ghost" size="icon-xs" className="size-5 shrink-0 text-muted-foreground"
    disabled={disabled} onClick={onReset} aria-label="Reset" >
    <RotateCcw className="size-3" aria-hidden="true" />
  </Button></TooltipHint>;
}

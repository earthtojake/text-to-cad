import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { RotateCcw, Spline } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { cn } from "@text-to-cad/ui/utils";
import { FILE_SHEET_FIELD_LABEL_CLASSES, FileSheetSelectRow } from "./FileSheet.js";

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
 * The Pose row of a Position panel: a "Pose" label beside its dropdown, drawn only when there is a
 * named pose to choose; Default leads the options when the panel can reset. Without a named pose
 * there is no row: Reset is the panel heading's (`MotionResetButton`).
 */
export function KinematicsPoseRow({ poses = [], activeValue, onSelect, onReset }) {
  if (!poses.length) return null;
  const options = [...(onReset ? [{ value: DEFAULT_POSE_VALUE, label: "Default" }] : []), ...poses];
  const active = options.find(pose => pose.value === activeValue);
  return <div data-position-header="" className="flex min-w-0 items-center gap-2 px-2">
    <span className={cn(FILE_SHEET_FIELD_LABEL_CLASSES, "shrink-0")}>Pose</span>
    {/* Compact and at the row's right end, the size of the joint value boxes under it. */}
    <FileSheetSelectRow hideLabel className="ml-auto min-w-0 px-0" triggerClassName="!h-6 w-auto max-w-full gap-1 !px-1.5 text-tiny" value={active?.value || NO_PRESET_VALUE}
      onValueChange={value => value === DEFAULT_POSE_VALUE ? onReset?.() : onSelect?.(value)}
      ariaLabel="Pose" triggerContent={<span className="truncate">{active?.label || "Custom"}</span>}
      options={options} />
  </div>;
}

/**
 * The Position tool's icon: the spline, with a small dot at its top-left while the pose is not the
 * default one (a joint moved, or a named pose applied), so a person can see that from the strip.
 */
export function PositionToolIcon({ custom = false }) {
  return <span className="relative inline-flex" data-position-custom={custom ? "" : undefined}>
    <Spline className="size-3" strokeWidth={2} aria-hidden="true" />
    {/* The size of the spline's own end dots and in its colour: a note, not a badge. */}
    {custom ? <span aria-hidden="true" className="absolute -left-px -top-px size-1 rounded-full bg-current" /> : null}
  </span>;
}

/** A Position panel's Reset: in its heading, before the fold chevron. */
export function MotionResetButton({ onReset }) {
  if (!onReset) return null;
  return <TooltipHint content="Reset motion"><Button variant="ghost" size="icon-xs" className="size-5 shrink-0 text-muted-foreground"
    onClick={onReset} aria-label="Reset">
    <RotateCcw className="size-3" aria-hidden="true" />
  </Button></TooltipHint>;
}

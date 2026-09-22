import { RotateCcw } from "lucide-react";
import { Button } from "@hardcore/ui/primitives/button";
import { FILE_SHEET_COMPACT_BUTTON_CLASSES, FileSheetSelectRow } from "./FileSheet.js";

// The Position section's two controls every posable file shares: the named-pose
// dropdown and the Reset button. None describes custom/default values without adding
// a selectable reset option.
export const NO_PRESET_VALUE = "__none__";

export function KinematicsPoseRow({
  poses,
  activeValue,
  onSelect,
  disabled = false,
  label = "Pose",
  ariaLabel = "Pose"
}) {
  if (!Array.isArray(poses) || !poses.length) {
    return null;
  }
  const active = poses.some((pose) => pose.value === activeValue) ? activeValue : NO_PRESET_VALUE;
  const activeLabel = active === NO_PRESET_VALUE
    ? "None"
    : String(poses.find((pose) => pose.value === active)?.label || active);
  return (
    // A labelled row: the name on the left, the dropdown right-aligned beside it.
    <FileSheetSelectRow
      label={label}
      value={active}
      onValueChange={(value) => {
        if (value === NO_PRESET_VALUE) {
          return;
        }
        onSelect?.(value);
      }}
      ariaLabel={ariaLabel}
      disabled={disabled}
      triggerContent={<span className="truncate">{activeLabel}</span>}
      options={poses.map((pose) => ({ value: pose.value, label: pose.label }))}
    />
  );
}

/** The section's last row: every driven value back to where the file puts it. */
export function MotionResetButton({ onReset }) {
  if (!onReset) return null;
  return <div className="px-2 py-2">
    <Button variant="outline" size="sm" className={`${FILE_SHEET_COMPACT_BUTTON_CLASSES} w-full justify-center`}
      onClick={onReset} title="Reset animation and position">
      <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />Reset
    </Button>
  </div>;
}

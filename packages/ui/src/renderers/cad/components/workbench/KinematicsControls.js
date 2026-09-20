import { FileSheetSelectRow } from "../../../kit/inspector/FileSheet.js";

// Shared named-position dropdown for STEP presets and robot group states.
// None describes custom/default values without adding a selectable reset option.
export const NO_PRESET_VALUE = "__none__";

export function KinematicsPoseRow({
  poses,
  activeValue,
  onSelect,
  disabled = false,
  compact = false,
  label = "Preset",
  ariaLabel = "Preset position"
}) {
  if (!Array.isArray(poses) || !poses.length) {
    return null;
  }
  const active = poses.some((pose) => pose.value === activeValue) ? activeValue : NO_PRESET_VALUE;
  const activeLabel = active === NO_PRESET_VALUE
    ? "None"
    : String(poses.find((pose) => pose.value === active)?.label || active);
  return (
    <FileSheetSelectRow
      stacked={!compact}
      hideLabel={compact}
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

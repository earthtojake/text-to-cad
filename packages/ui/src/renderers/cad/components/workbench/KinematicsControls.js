import { Copy, RotateCcw } from "lucide-react";
import { cn } from "@hardcore/ui/utils";
import { POSE_TRANSITION_SPEEDS } from "../../workbench/poseTransition.js";
import { Button } from "@hardcore/ui/primitives/button";
import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FileSheetButtonRow,
  FileSheetSelectRow,
  FileSheetSubsection,
  FileSheetToggleRow
} from "./FileSheet.js";

// The parts of the Kinematics tab that are the SAME for every kind of model that has
// poses: which pose is on, what the person does to the values, and how the model
// travels between poses.
//
// A STEP model's mates and a robot's joints are one control to the person using them —
// pick a pose, watch it move, nudge a DOF, copy the result — and they were two panels
// that had drifted into two vocabularies ("Presets" and buttons here, "Group state" and
// a dropdown there). These are the shared halves; each sheet still renders its own DOF
// rows, because a typed parameter and a joint limit are genuinely different things.

// The model is in no preset. The sentinel is a value rather than an empty string
// because a Select with no value shows its placeholder, and "None" is a state worth
// reading: the person moved a DOF and left every named position behind.
export const NO_PRESET_VALUE = "__none__";

// The named positions, as the FIRST row of Position: a preset is a way of setting the
// position, so it belongs among the DOFs rather than in a section of its own with one
// control in it.
//
// "Preset", not "Pose" or "Group state": the tab already says Kinematics and the section
// already says Position, so the row names what these ARE to the person using them -- a
// named position to jump to -- in the same word for a STEP model's poses and a robot's
// SRDF group states.
export function KinematicsPoseRow({
  poses,
  activeValue,
  onSelect,
  disabled = false,
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
      stacked
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

// How the model TRAVELS between poses, at the FOOT of the tab: a setting about the
// controls above it rather than one of them.
//
// Speed is hidden when animation is off, not greyed. A disabled control still asks to
// be read and still says "this applies to you"; one that cannot apply is better gone.
export function KinematicsTransitionSubsection({ transition }) {
  if (!transition) {
    return null;
  }
  const animate = transition.animate !== false;
  return (
    <FileSheetSubsection title="Transition">
      <FileSheetToggleRow
        label="Animate"
        checked={animate}
        onCheckedChange={(checked) => transition.setAnimate?.(checked)}
        ariaLabel="Animate pose changes"
      />
      {animate ? (
        <FileSheetSelectRow
          label="Speed"
          value={String(transition.speed ?? 1)}
          onValueChange={(value) => transition.setSpeed?.(Number(value))}
          ariaLabel="Pose transition speed"
          options={POSE_TRANSITION_SPEEDS}
        />
      ) : null}
    </FileSheetSubsection>
  );
}

// The foot of Values: what the person does to the numbers above, in both sheets. The
// labels are the verbs alone -- "Reset pose" and "Copy angles" said which noun the file
// happened to use, under a heading that already says it.
export function KinematicsValueActions({
  onReset,
  onCopy,
  resetTitle = "Reset every value to the model as authored",
  copyTitle = "Copy the current values"
}) {
  if (!onReset && !onCopy) {
    return null;
  }
  return (
    <FileSheetButtonRow columns={onReset && onCopy ? 2 : 1}>
      {onReset ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn(FILE_SHEET_COMPACT_BUTTON_CLASSES, "justify-center")}
          onClick={() => onReset()}
          title={resetTitle}
        >
          <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
          <span>Reset</span>
        </Button>
      ) : null}
      {onCopy ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className={cn(FILE_SHEET_COMPACT_BUTTON_CLASSES, "justify-center")}
          onClick={() => { void onCopy(); }}
          title={copyTitle}
        >
          <Copy className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
          <span>Copy</span>
        </Button>
      ) : null}
    </FileSheetButtonRow>
  );
}

import { memo, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { cn } from "@text-to-cad/ui/utils";
import { Slider } from "@text-to-cad/ui/primitives/slider";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import {
  FILE_SHEET_PRECISION_SLIDER_CLASSES, FileSheetSliderField, FileSheetStatusText, parseFileSheetNumberInput
} from "../kit/inspector/FileSheet.js";
import { KinematicsPoseRow, NO_PRESET_VALUE, DEFAULT_POSE_VALUE, positionValuesAreDefault } from "../kit/inspector/kinematicsControls.jsx";

const CONTROL_SYNC_EPSILON = 0.001;
const CONTROL_LOCAL_OVERRIDE_MS = 3500;
// A control with no limits (a continuous joint) spans one turn on its slider; a free slide spans a metre.
const UNBOUNDED_SPAN = { deg: [-180, 180], m: [-1, 1] };

function controlValuesClose(left, right) {
  return Math.abs(Number(left) - Number(right)) <= CONTROL_SYNC_EPSILON;
}

function isAngular(control) {
  return String(control?.unit || "").trim().toLowerCase() === "deg";
}

function formatControlValue(value, control) {
  const scale = isAngular(control) ? 10 : 10000;
  const rounded = Math.round(Number(value) * scale) / scale;
  const safeValue = Number.isFinite(rounded) ? rounded : 0;
  return isAngular(control) ? `${safeValue}°` : `${safeValue} ${control?.unit || "m"}`;
}

/** The slider's span: the control's declared limits, else one turn or one metre about zero
 * (a null limit is no limit, and `Number(null)` is 0, so it is asked first). */
function sliderSpan(control) {
  const limit = value => (value == null ? Number.NaN : Number(value));
  const min = limit(control?.min), max = limit(control?.max);
  if (Number.isFinite(min) && Number.isFinite(max)) return [min, max];
  return UNBOUNDED_SPAN[isAngular(control) ? "deg" : "m"];
}

function clampInputValue(value, min, max, fallback) {
  const numericValue = Number.isFinite(Number(value)) ? Number(value) : fallback;
  return Math.min(Math.max(numericValue, min), Math.max(min, max));
}

// A row keeps its own live value while it is being driven: it writes at most once per
// animation frame, and after a local change it ignores the pose's value until the two
// agree (or a few seconds pass), so a slider never fights the hand moving it.
const ControlRow = memo(function ControlRow({ control, value, onValueChange }) {
  const label = String(control?.label || control?.id || "").trim();
  const [min, max] = sliderSpan(control);
  const safeValue = clampInputValue(value, min, max, 0);
  const unitLabel = isAngular(control) ? "deg" : String(control?.unit || "m");
  const sliderStep = isAngular(control) ? 1 : 0.001;
  const pendingFrameRef = useRef(0);
  const pendingValueRef = useRef(safeValue);
  const latestSafeValueRef = useRef(safeValue);
  const localOverrideRef = useRef(false);
  const localOverrideTimeoutRef = useRef(0);
  const [liveValue, setLiveValue] = useState(safeValue);

  const clearLocalOverrideTimeout = () => {
    if (localOverrideTimeoutRef.current && typeof window !== "undefined") {
      window.clearTimeout(localOverrideTimeoutRef.current);
    }
    localOverrideTimeoutRef.current = 0;
  };

  const releaseLocalOverride = (nextValue = latestSafeValueRef.current) => {
    clearLocalOverrideTimeout();
    localOverrideRef.current = false;
    const normalized = clampInputValue(nextValue, min, max, latestSafeValueRef.current);
    pendingValueRef.current = normalized;
    setLiveValue(normalized);
  };

  const holdLocalValueUntilParentSettles = (nextValue) => {
    pendingValueRef.current = nextValue;
    localOverrideRef.current = true;
    clearLocalOverrideTimeout();
    if (typeof window !== "undefined") {
      localOverrideTimeoutRef.current = window.setTimeout(() => { releaseLocalOverride(); }, CONTROL_LOCAL_OVERRIDE_MS);
    }
  };

  useEffect(() => {
    latestSafeValueRef.current = safeValue;
    if (localOverrideRef.current) {
      if (controlValuesClose(safeValue, pendingValueRef.current)) {
        releaseLocalOverride(safeValue);
      }
      return;
    }
    pendingValueRef.current = safeValue;
    setLiveValue(safeValue);
  }, [safeValue]);

  useEffect(() => () => {
    if (pendingFrameRef.current && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(pendingFrameRef.current);
    }
    clearLocalOverrideTimeout();
  }, []);

  const scheduleValueChange = (nextValue) => {
    pendingValueRef.current = nextValue;
    if (typeof requestAnimationFrame !== "function") {
      onValueChange(control.id, nextValue);
      return;
    }
    if (pendingFrameRef.current) {
      return;
    }
    pendingFrameRef.current = requestAnimationFrame(() => {
      pendingFrameRef.current = 0;
      onValueChange(control.id, pendingValueRef.current);
    });
  };

  const commitValue = (nextValue) => {
    const normalized = clampInputValue(nextValue, min, max, liveValue);
    pendingValueRef.current = normalized;
    if (pendingFrameRef.current && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(pendingFrameRef.current);
      pendingFrameRef.current = 0;
    }
    setLiveValue(normalized);
    holdLocalValueUntilParentSettles(normalized);
    onValueChange(control.id, normalized);
  };

  return (
    <FileSheetSliderField
      label={label || "Joint"}
      value={formatControlValue(liveValue, control)}
      onValueCommit={(nextValue) => {
        commitValue(parseFileSheetNumberInput(nextValue, { fallback: liveValue, min, max }));
      }}
      valueInputProps={{ ariaLabel: `${label || "Joint"} value in ${unitLabel}` }}
    >
        <TooltipHint content={`${formatControlValue(min, control)} to ${formatControlValue(max, control)}`}>
          <Slider
            className={cn(FILE_SHEET_PRECISION_SLIDER_CLASSES, "min-w-0")}
            min={min}
            max={max}
            step={sliderStep}
            value={[liveValue]}
            onValueChange={(nextValue) => {
              const next = clampInputValue(nextValue?.[0], min, max, liveValue);
              if (controlValuesClose(next, pendingValueRef.current)) {
                return;
              }
              setLiveValue(next);
              holdLocalValueUntilParentSettles(next);
              scheduleValueChange(next);
            }}
            onValueCommit={(nextValue) => { commitValue(nextValue?.[0]); }}
            thumbProps={{ "aria-label": label || "Joint value" }}
          />
        </TooltipHint>
    </FileSheetSliderField>
  );
});

// Each control subscribes to the ONE thing it draws (a control's value, the named pose's
// id), so a pose step renders the row that moved and nothing else: not the section, not
// its 26 other rows.
function PoseControlRow({ pose, control }) {
  const read = () => pose.getSnapshot().values[control.id] ?? pose.defaults[control.id] ?? 0;
  const value = useSyncExternalStore(pose.subscribe, read, read);
  return <ControlRow control={control} value={value} onValueChange={pose.write} />;
}

function PoseGroupStateRow({ pose }) {
  const read = () => pose.getSnapshot();
  const { groupStateId, values } = useSyncExternalStore(pose.subscribe, read, read);
  return <KinematicsPoseRow
    poses={pose.groupStates.map(state => ({ value: state.id, label: String(state.label || state.name || "").trim() || "State" }))}
    onReset={pose.reset}
    activeValue={positionValuesAreDefault(values, pose.defaults) ? DEFAULT_POSE_VALUE : pose.groupStates.some(state => state.id === groupStateId) ? groupStateId : NO_PRESET_VALUE}
    onSelect={(value) => {
      const state = pose.groupStates.find(candidate => candidate.id === value);
      if (state) pose.selectGroupState(state);
    }}
  />;
}

/**
 * A robot's Position panel (the tool stack's, while the Position tool is up): its named pose (an
 * SRDF's group states) when it has one, then a compact slider row per control of the articulation —
 * one panel's rows, with no sections of their own. Reset is the panel heading's.
 *
 * @param {{ pose: ReturnType<typeof import("./poseStore.js").createPoseStore> }} props
 */
export default function PositionControls({ pose }) {
  if (!pose.controls.length) return <FileSheetStatusText className="py-2">No movable joints.</FileSheetStatusText>;
  return (
    <div className="space-y-1.5 pb-1.5 pt-0.5">
      {/* A named state is a way of SETTING the controls, so it leads them. A plain URDF
          declares none and opens straight onto its values. */}
      <PoseGroupStateRow pose={pose} />
      {pose.controls.map(control => <PoseControlRow key={control.id} pose={pose} control={control} />)}
    </div>
  );
}

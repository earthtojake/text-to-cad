import { memo, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { cn } from "@hardcore/ui/utils";
import { Slider } from "@hardcore/ui/primitives/slider";
import {
  FILE_SHEET_PRECISION_SLIDER_CLASSES, FileSheetSliderField, FileSheetStatusText, parseFileSheetNumberInput
} from "../kit/inspector/FileSheet.js";
import { KinematicsPoseRow, NO_PRESET_VALUE, DEFAULT_POSE_VALUE, positionValuesAreDefault } from "../kit/inspector/kinematicsControls.jsx";

const JOINT_CONTROL_SYNC_EPSILON = 0.001;
const JOINT_CONTROL_LOCAL_OVERRIDE_MS = 3500;

function jointControlValuesClose(left, right) {
  return Math.abs(Number(left) - Number(right)) <= JOINT_CONTROL_SYNC_EPSILON;
}

function isAngularJoint(joint) {
  const jointType = String(joint?.type || "").trim().toLowerCase();
  return jointType === "continuous" || jointType === "revolute";
}

function jointUnitLabel(joint) {
  return isAngularJoint(joint) ? "deg" : "m";
}

function formatJointValue(value, joint) {
  const scale = isAngularJoint(joint) ? 10 : 10000;
  const rounded = Math.round(Number(value) * scale) / scale;
  const safeValue = Number.isFinite(rounded) ? rounded : 0;
  return isAngularJoint(joint) ? `${safeValue}\u00b0` : `${safeValue} m`;
}

function clampJointInputValue(valueDeg, minValueDeg, maxValueDeg, fallbackValueDeg) {
  const numericValue = Number.isFinite(Number(valueDeg)) ? Number(valueDeg) : fallbackValueDeg;
  return Math.min(Math.max(numericValue, minValueDeg), Math.max(minValueDeg, maxValueDeg));
}

// A row keeps its own live value while it is being driven: it writes at most once per
// animation frame, and after a local change it ignores the pose's value until the two
// agree (or a few seconds pass), so a slider never fights the hand moving it.
const JointRow = memo(function JointRow({
  joint,
  valueDeg,
  onValueChange
}) {
  const jointName = String(joint?.name || "").trim();
  const minValueDeg = Number.isFinite(Number(joint?.minValueDeg)) ? Number(joint.minValueDeg) : -180;
  const maxValueDeg = Number.isFinite(Number(joint?.maxValueDeg)) ? Number(joint.maxValueDeg) : 180;
  const safeValueDeg = clampJointInputValue(valueDeg, minValueDeg, maxValueDeg, 0);
  const unitLabel = jointUnitLabel(joint);
  const sliderStep = isAngularJoint(joint) ? 1 : 0.001;
  const pendingFrameRef = useRef(0);
  const pendingValueRef = useRef(safeValueDeg);
  const latestSafeValueRef = useRef(safeValueDeg);
  const localOverrideRef = useRef(false);
  const localOverrideTimeoutRef = useRef(0);
  const [liveValueDeg, setLiveValueDeg] = useState(safeValueDeg);

  const clearLocalOverrideTimeout = () => {
    if (localOverrideTimeoutRef.current && typeof window !== "undefined") {
      window.clearTimeout(localOverrideTimeoutRef.current);
    }
    localOverrideTimeoutRef.current = 0;
  };

  const releaseLocalOverride = (nextValueDeg = latestSafeValueRef.current) => {
    clearLocalOverrideTimeout();
    localOverrideRef.current = false;
    const normalizedValueDeg = clampJointInputValue(nextValueDeg, minValueDeg, maxValueDeg, latestSafeValueRef.current);
    pendingValueRef.current = normalizedValueDeg;
    setLiveValueDeg(normalizedValueDeg);
  };

  const holdLocalValueUntilParentSettles = (nextValueDeg) => {
    pendingValueRef.current = nextValueDeg;
    localOverrideRef.current = true;
    clearLocalOverrideTimeout();
    if (typeof window !== "undefined") {
      localOverrideTimeoutRef.current = window.setTimeout(() => {
        releaseLocalOverride();
      }, JOINT_CONTROL_LOCAL_OVERRIDE_MS);
    }
  };

  useEffect(() => {
    latestSafeValueRef.current = safeValueDeg;
    if (localOverrideRef.current) {
      if (jointControlValuesClose(safeValueDeg, pendingValueRef.current)) {
        releaseLocalOverride(safeValueDeg);
      }
      return;
    }
    pendingValueRef.current = safeValueDeg;
    setLiveValueDeg(safeValueDeg);
  }, [safeValueDeg]);

  useEffect(() => () => {
    if (pendingFrameRef.current && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(pendingFrameRef.current);
    }
    clearLocalOverrideTimeout();
  }, []);

  const scheduleValueChange = (nextValueDeg) => {
    pendingValueRef.current = nextValueDeg;
    if (typeof requestAnimationFrame !== "function") {
      onValueChange(joint, nextValueDeg);
      return;
    }
    if (pendingFrameRef.current) {
      return;
    }
    pendingFrameRef.current = requestAnimationFrame(() => {
      pendingFrameRef.current = 0;
      onValueChange(joint, pendingValueRef.current);
    });
  };

  const commitValue = (nextValueDeg) => {
    const normalizedValueDeg = clampJointInputValue(nextValueDeg, minValueDeg, maxValueDeg, liveValueDeg);
    pendingValueRef.current = normalizedValueDeg;
    if (pendingFrameRef.current && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(pendingFrameRef.current);
      pendingFrameRef.current = 0;
    }
    setLiveValueDeg(normalizedValueDeg);
    holdLocalValueUntilParentSettles(normalizedValueDeg);
    onValueChange(joint, normalizedValueDeg);
  };

  return (
    <FileSheetSliderField stacked
      label={jointName || "Joint"}
      value={formatJointValue(liveValueDeg, joint)}
      onValueCommit={(nextValue) => {
        commitValue(parseFileSheetNumberInput(nextValue, {
          fallback: liveValueDeg,
          min: minValueDeg,
          max: maxValueDeg
        }));
      }}
      valueInputProps={{
        ariaLabel: `${jointName || "Joint"} value in ${unitLabel}`
      }}
    >
        <Slider
          className={cn(FILE_SHEET_PRECISION_SLIDER_CLASSES, "min-w-0")}
          min={minValueDeg}
          max={maxValueDeg}
          step={sliderStep}
          value={[liveValueDeg]}
          onValueChange={(nextValue) => {
            const nextValueDeg = clampJointInputValue(nextValue?.[0], minValueDeg, maxValueDeg, liveValueDeg);
            if (jointControlValuesClose(nextValueDeg, pendingValueRef.current)) {
              return;
            }
            setLiveValueDeg(nextValueDeg);
            holdLocalValueUntilParentSettles(nextValueDeg);
            scheduleValueChange(nextValueDeg);
          }}
          onValueCommit={(nextValue) => {
            commitValue(nextValue?.[0]);
          }}
          aria-label={jointName || "Joint value"}
          title={`${formatJointValue(minValueDeg, joint)} to ${formatJointValue(maxValueDeg, joint)}`}
        />
    </FileSheetSliderField>
  );
});

// Each control subscribes to the ONE thing it draws (a joint's value, the named pose's
// id), so a pose step renders the row that moved and nothing else: not the section, not
// its 26 other rows.
function PoseJointRow({ pose, joint }) {
  const read = () => pose.getSnapshot().values[joint.name] ?? joint.defaultValueDeg ?? 0;
  const valueDeg = useSyncExternalStore(pose.subscribe, read, read);
  return <JointRow joint={joint} valueDeg={valueDeg} onValueChange={pose.write} />;
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
 * A robot's Position sidebar section: its named pose (an SRDF's group states), then a slider per
 * joint a person can drive, with Reset beside the pose selector — one section's rows, with no sections of their own.
 *
 * @param {{ pose: ReturnType<typeof import("./poseStore.js").createPoseStore> }} props
 */
export default function PositionControls({ pose }) {
  if (!pose.joints.length) return <FileSheetStatusText className="py-2">No movable joints.</FileSheetStatusText>;
  return (
    <div className="space-y-2 px-1 py-2">
      {/* A named state is a way of SETTING the joints, so it leads them. A plain URDF
          declares none and opens straight onto its values. */}
      <PoseGroupStateRow pose={pose} />
      {pose.joints.map(joint => <PoseJointRow key={joint.name} pose={pose} joint={joint} />)}
    </div>
  );
}

import { memo, useEffect, useRef, useState } from "react";
import { Copy, RotateCcw } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger
} from "../ui/accordion";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "../ui/select";
import { Slider } from "../ui/slider";
import { Switch } from "../ui/switch";
import FileSheet from "./FileSheet";

const fieldLabelClasses = "block text-xs font-medium text-muted-foreground";
const compactInputClasses = "h-8 px-2 !text-xs font-medium leading-none tabular-nums";
const compactJointInputClasses = "h-7 px-2 !text-[11px] font-medium leading-none tabular-nums";

function formatJointValue(valueDeg) {
  const rounded = Math.round(Number(valueDeg) * 10) / 10;
  return `${Number.isFinite(rounded) ? rounded : 0}\u00b0`;
}

function formatJointInput(valueDeg) {
  const rounded = Math.round(Number(valueDeg) * 10) / 10;
  return Number.isFinite(rounded) ? String(rounded) : "";
}

function formatAnimationSpeed(speed) {
  const rounded = Math.round(Number(speed) * 100) / 100;
  return `${Number.isFinite(rounded) ? rounded.toFixed(2).replace(/\.?0+$/, "") : "1"}x`;
}

function formatMotionCoordinate(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return "";
  }
  const rounded = Math.round(numericValue * 10000) / 10000;
  return String(Object.is(rounded, -0) ? 0 : rounded);
}

function motionPositionsClose(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b) || a.length < 3 || b.length < 3) {
    return false;
  }
  return [0, 1, 2].every((index) => Math.abs(Number(a[index]) - Number(b[index])) <= 0.0005);
}

function clampJointInputValue(valueDeg, minValueDeg, maxValueDeg, fallbackValueDeg) {
  const numericValue = Number.isFinite(Number(valueDeg)) ? Number(valueDeg) : fallbackValueDeg;
  return Math.min(Math.max(numericValue, minValueDeg), Math.max(minValueDeg, maxValueDeg));
}

const UrdfJointRow = memo(function UrdfJointRow({
  joint,
  valueDeg,
  onValueChange
}) {
  const jointName = String(joint?.name || "").trim();
  const minValueDeg = Number.isFinite(Number(joint?.minValueDeg)) ? Number(joint.minValueDeg) : -180;
  const maxValueDeg = Number.isFinite(Number(joint?.maxValueDeg)) ? Number(joint.maxValueDeg) : 180;
  const safeValueDeg = clampJointInputValue(valueDeg, minValueDeg, maxValueDeg, 0);
  const pendingFrameRef = useRef(0);
  const pendingValueRef = useRef(safeValueDeg);
  const [liveValueDeg, setLiveValueDeg] = useState(safeValueDeg);
  const [draftValue, setDraftValue] = useState(() => formatJointInput(safeValueDeg));

  useEffect(() => {
    pendingValueRef.current = safeValueDeg;
    setLiveValueDeg(safeValueDeg);
    setDraftValue(formatJointInput(safeValueDeg));
  }, [safeValueDeg]);

  useEffect(() => () => {
    if (pendingFrameRef.current && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(pendingFrameRef.current);
    }
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
    setDraftValue(formatJointInput(normalizedValueDeg));
    onValueChange(joint, normalizedValueDeg);
  };

  return (
    <div className="px-3 py-1.5">
      <label className="block">
        <div className="flex items-center justify-between gap-2">
          <span className={`${fieldLabelClasses} min-w-0 truncate`}>{jointName || "Joint"}</span>
          <div className="relative w-16 shrink-0">
            <Input
              type="number"
              min={String(minValueDeg)}
              max={String(maxValueDeg)}
              step="0.1"
              inputMode="decimal"
              value={draftValue}
              onChange={(event) => {
                setDraftValue(event.target.value);
              }}
              onFocus={(event) => {
                event.currentTarget.select();
              }}
              onMouseUp={(event) => {
                event.preventDefault();
              }}
              onBlur={() => {
                commitValue(draftValue);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.currentTarget.blur();
                }
              }}
              className={`${compactJointInputClasses} pr-6 text-right`}
              aria-label={`${jointName || "Joint"} angle in degrees`}
            />
            <span className="pointer-events-none absolute inset-y-0 right-1.5 flex items-center text-[9px] leading-none text-muted-foreground">deg</span>
          </div>
        </div>
        <Slider
          className="mt-1 h-5 min-w-0"
          min={minValueDeg}
          max={maxValueDeg}
          step={1}
          value={[liveValueDeg]}
          onValueChange={(nextValue) => {
            const nextValueDeg = clampJointInputValue(nextValue?.[0], minValueDeg, maxValueDeg, liveValueDeg);
            setLiveValueDeg(nextValueDeg);
            setDraftValue(formatJointInput(nextValueDeg));
            scheduleValueChange(nextValueDeg);
          }}
          onValueCommit={(nextValue) => {
            commitValue(nextValue?.[0]);
          }}
          aria-label={jointName || "Joint angle"}
          title={`${formatJointValue(minValueDeg)} to ${formatJointValue(maxValueDeg)}`}
        />
      </label>
    </div>
  );
});

const MotionCoordinateInput = memo(function MotionCoordinateInput({
  axis,
  value,
  disabled,
  onValueChange
}) {
  const safeValue = Number.isFinite(Number(value)) ? Number(value) : 0;
  const [draftValue, setDraftValue] = useState(() => formatMotionCoordinate(safeValue));

  useEffect(() => {
    setDraftValue(formatMotionCoordinate(safeValue));
  }, [safeValue]);

  const commitValue = (nextValue) => {
    const numericValue = Number(nextValue);
    const committedValue = Number.isFinite(numericValue) ? numericValue : safeValue;
    setDraftValue(formatMotionCoordinate(committedValue));
    onValueChange?.(committedValue);
  };

  return (
    <label className="block min-w-0">
      <span className={fieldLabelClasses}>{axis}</span>
      <Input
        type="number"
        step="0.001"
        inputMode="decimal"
        disabled={disabled}
        value={draftValue}
        onChange={(event) => {
          setDraftValue(event.target.value);
        }}
        onFocus={(event) => {
          event.currentTarget.select();
        }}
        onMouseUp={(event) => {
          event.preventDefault();
        }}
        onBlur={() => {
          commitValue(draftValue);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.currentTarget.blur();
          }
        }}
        className={`${compactInputClasses} mt-1.5 text-right`}
        aria-label={`Target ${axis} coordinate`}
      />
    </label>
  );
});

export default function UrdfFileSheet({
  open,
  isDesktop,
  width,
  onStartResize,
  joints,
  poses,
  activePoseName,
  jointValues,
  onJointValueChange,
  onPoseSelect,
  onCopyJointAngles,
  introAnimationEnabled = false,
  animationSpeed = 1,
  onIntroAnimationEnabledChange,
  onReplayIntroAnimation,
  onAnimationSpeedChange,
  onResetPose,
  motion = null
}) {
  const movableJoints = Array.isArray(joints) ? joints : [];
  const posePresets = Array.isArray(poses) ? poses : [];
  const motionEndEffectors = Array.isArray(motion?.endEffectors) ? motion.endEffectors : [];
  const motionEnabled = motionEndEffectors.length > 0;
  const defaultSections = [
    ...(motionEnabled ? ["motion"] : []),
    "joints"
  ];
  const activeMotionEndEffectorName = String(motion?.activeEndEffectorName || motionEndEffectors[0]?.name || "").trim();
  const motionTargetPosition = Array.isArray(motion?.targetPosition) ? motion.targetPosition : [0, 0, 0];
  const motionCurrentPosition = Array.isArray(motion?.currentPosition) ? motion.currentPosition : null;
  const motionBusy = Boolean(motion?.solving);
  const motionSelectPoseActive = Boolean(motion?.selectPoseActive);
  const motionTargetMatchesCurrentPosition = motionCurrentPosition ? motionPositionsClose(motionTargetPosition, motionCurrentPosition) : true;
  const activePoseValue = posePresets.some((pose) => String(pose?.name || "").trim() === activePoseName)
    ? activePoseName
    : "__custom__";
  const activePoseLabel = activePoseValue === "__custom__" ? "custom" : activePoseValue;
  const [openSections, setOpenSections] = useState(defaultSections);

  useEffect(() => {
    setOpenSections((current) => {
      const allowedSections = new Set(["joints", "animation", ...(motionEnabled ? ["motion"] : [])]);
      const nextSections = (Array.isArray(current) ? current : []).filter((section) => allowedSections.has(section));
      if (motionEnabled && !nextSections.includes("motion")) {
        nextSections.unshift("motion");
      }
      if (!nextSections.includes("joints")) {
        nextSections.push("joints");
      }
      if (nextSections.length === current.length && nextSections.every((section, index) => section === current[index])) {
        return current;
      }
      return nextSections;
    });
  }, [motionEnabled]);

  return (
    <FileSheet
      open={open}
      title="URDF"
      isDesktop={isDesktop}
      width={width}
      onStartResize={onStartResize}
    >
      <Accordion type="multiple" value={openSections} onValueChange={setOpenSections}>
        {motionEnabled ? (
          <AccordionItem value="motion">
            <AccordionTrigger>Motion</AccordionTrigger>
            <AccordionContent className="py-1">
              <div className="space-y-3 px-3 py-2">
                <div>
                  <span className={fieldLabelClasses}>End effector</span>
                  <Select
                    value={activeMotionEndEffectorName}
                    disabled={motionBusy || motionEndEffectors.length <= 1}
                    onValueChange={(value) => {
                      motion?.onEndEffectorChange?.(value);
                    }}
                  >
                    <SelectTrigger size="sm" className="mt-1.5 h-8 !text-xs">
                      <SelectValue placeholder="Select end effector" />
                    </SelectTrigger>
                    <SelectContent>
                      {motionEndEffectors.map((endEffector) => {
                        const name = String(endEffector?.name || "").trim();
                        return name ? (
                          <SelectItem key={name} value={name}>
                            {name}
                          </SelectItem>
                        ) : null;
                      })}
                    </SelectContent>
                  </Select>
                </div>

                <div className="grid grid-cols-3 gap-2">
                  {["X", "Y", "Z"].map((axis, index) => (
                    <MotionCoordinateInput
                      key={axis}
                      axis={axis}
                      value={motionTargetPosition[index]}
                      disabled={motionBusy}
                      onValueChange={(nextValue) => {
                        motion?.onTargetPositionChange?.(index, nextValue);
                      }}
                    />
                  ))}
                </div>

                <div className="flex flex-wrap gap-1.5">
                  <Button
                    type="button"
                    variant={motionSelectPoseActive ? "secondary" : "outline"}
                    size="sm"
                    className="h-8 px-2 text-xs"
                    disabled={motionBusy}
                    onClick={() => {
                      if (motionSelectPoseActive) {
                        motion?.onCancelSelectPose?.();
                        return;
                      }
                      motion?.onSelectPose?.();
                    }}
                    aria-pressed={motionSelectPoseActive}
                  >
                    <span>Select Pose</span>
                  </Button>
                  {!motionTargetMatchesCurrentPosition ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-8 px-2 text-xs"
                      disabled={motionBusy}
                      onClick={() => {
                        motion?.onUseCurrentPosition?.();
                      }}
                    >
                      <span>Reset</span>
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    variant="default"
                    size="sm"
                    className="h-8 px-2 text-xs"
                    disabled={motionBusy || motionTargetMatchesCurrentPosition}
                    onClick={() => {
                      void motion?.onApply?.();
                    }}
                  >
                    <span>{motionBusy ? "Applying..." : "Apply"}</span>
                  </Button>
                </div>
              </div>
            </AccordionContent>
          </AccordionItem>
        ) : null}
        <AccordionItem value="joints">
          <AccordionTrigger>Joints</AccordionTrigger>
          <AccordionContent className="py-1">
            {movableJoints.length ? (
              <>
                <div className="space-y-2 px-3 py-2">
                  {posePresets.length ? (
                    <div>
                      <span className={fieldLabelClasses}>Pose</span>
                      <Select
                        value={activePoseValue === "__custom__" ? undefined : activePoseValue}
                        onValueChange={(value) => {
                          if (value === "__custom__") {
                            return;
                          }
                          const pose = posePresets.find((candidate) => String(candidate?.name || "").trim() === value);
                          if (pose) {
                            onPoseSelect?.(pose);
                          }
                        }}
                      >
                        <SelectTrigger size="sm" className="mt-1.5 h-8 !text-xs">
                          <span className="truncate">{activePoseLabel}</span>
                        </SelectTrigger>
                        <SelectContent>
                          {posePresets.map((pose) => {
                            const poseName = String(pose?.name || "").trim() || "Pose";
                            return (
                              <SelectItem key={poseName} value={poseName}>
                                {poseName}
                              </SelectItem>
                            );
                          })}
                        </SelectContent>
                      </Select>
                    </div>
                  ) : null}
                  <div className="flex flex-wrap gap-1.5">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-8 px-2 text-xs"
                      onClick={onResetPose}
                    >
                      <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                      <span>Reset pose</span>
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-8 px-2 text-xs"
                      onClick={() => {
                        void onCopyJointAngles?.();
                      }}
                    >
                      <Copy className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                      <span>Copy angles</span>
                    </Button>
                  </div>
                </div>
                {movableJoints.map((joint) => (
                  <UrdfJointRow
                    key={joint.name}
                    joint={joint}
                    valueDeg={jointValues?.[joint.name] ?? joint?.defaultValueDeg ?? 0}
                    onValueChange={onJointValueChange}
                  />
                ))}
              </>
            ) : (
              <p className="px-3 py-2 text-xs text-muted-foreground">No movable joints are available.</p>
            )}
          </AccordionContent>
        </AccordionItem>
        <AccordionItem value="animation">
          <AccordionTrigger>Animation</AccordionTrigger>
          <AccordionContent className="py-1">
            <div className="space-y-3 px-3 py-2">
              <div className="flex items-start justify-between gap-3">
                <span className={fieldLabelClasses}>Entry animation</span>
                <Switch
                  checked={introAnimationEnabled}
                  onCheckedChange={onIntroAnimationEnabledChange}
                  aria-label="Enable URDF entry animation"
                />
              </div>
              {introAnimationEnabled ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 w-full justify-center px-2 text-xs"
                  onClick={() => {
                    onReplayIntroAnimation?.();
                  }}
                >
                  <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                  <span>Replay intro</span>
                </Button>
              ) : null}
              <div>
                <div className="flex items-center justify-between gap-3">
                  <span className={fieldLabelClasses}>Joint motion speed</span>
                  <span className="text-xs font-medium text-foreground">{formatAnimationSpeed(animationSpeed)}</span>
                </div>
                <Slider
                  className="mt-2 h-8"
                  min={0.25}
                  max={2.5}
                  step={0.25}
                  value={[animationSpeed]}
                  onValueChange={(nextValue) => {
                    onAnimationSpeedChange?.(nextValue?.[0] ?? animationSpeed);
                  }}
                  aria-label="URDF joint motion speed"
                />
                <div className="mt-1 flex items-center justify-between text-[10px] font-medium text-muted-foreground">
                  <span>Slower</span>
                  <span>Faster</span>
                </div>
              </div>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </FileSheet>
  );
}

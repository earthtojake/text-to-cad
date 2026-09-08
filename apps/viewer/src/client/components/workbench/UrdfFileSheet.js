import { memo, useEffect, useRef, useState } from "react";
import { Copy, RotateCcw } from "lucide-react";
import { cn } from "@/ui/utils";
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
import FileSheet, {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_COMPACT_NUMERIC_INPUT_CLASSES,
  FILE_SHEET_FIELD_LABEL_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FILE_SHEET_SELECT_TRIGGER_CLASSES,
  FileSheetButtonRow,
  FileSheetField,
  FileSheetFieldGrid,
  FileSheetSelectRow,
  FileSheetSliderField,
  FileSheetStatusText,
  FileSheetSubsection,
  FileSheetValueField,
  parseFileSheetNumberInput
} from "./FileSheet";
import FileSheetTabbedSurface from "./FileSheetTabbedSurface";
import { buildFileStatusTab } from "./FileStatusSection";
import RobotComponentsSection from "./RobotComponentsSection";
import RobotComponentReferenceSection from "./RobotComponentReferenceSection";

const compactNumericInputClasses = FILE_SHEET_COMPACT_NUMERIC_INPUT_CLASSES;
const compactButtonClasses = FILE_SHEET_COMPACT_BUTTON_CLASSES;
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

function formatSdfNumber(value, fallback = "0") {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return fallback;
  }
  const rounded = Math.round(numericValue * 1000) / 1000;
  return String(Object.is(rounded, -0) ? 0 : rounded);
}

function formatMotionCoordinate(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return "";
  }
  const rounded = Math.round(numericValue * 10000) / 10000;
  return String(Object.is(rounded, -0) ? 0 : rounded);
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

  const scheduleValueChange = (nextValueDeg, options = {}) => {
    pendingValueRef.current = nextValueDeg;
    if (typeof requestAnimationFrame !== "function") {
      onValueChange(joint, nextValueDeg, options);
      return;
    }
    if (pendingFrameRef.current) {
      return;
    }
    pendingFrameRef.current = requestAnimationFrame(() => {
      pendingFrameRef.current = 0;
      onValueChange(joint, pendingValueRef.current, options);
    });
  };

  const commitValue = (nextValueDeg, options = {}) => {
    const normalizedValueDeg = clampJointInputValue(nextValueDeg, minValueDeg, maxValueDeg, liveValueDeg);
    pendingValueRef.current = normalizedValueDeg;
    if (pendingFrameRef.current && typeof cancelAnimationFrame === "function") {
      cancelAnimationFrame(pendingFrameRef.current);
      pendingFrameRef.current = 0;
    }
    setLiveValueDeg(normalizedValueDeg);
    holdLocalValueUntilParentSettles(normalizedValueDeg);
    onValueChange(joint, normalizedValueDeg, options);
  };

  return (
    <FileSheetSliderField
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
            scheduleValueChange(nextValueDeg, { scrub: true });
          }}
          onValueCommit={(nextValue) => {
            commitValue(nextValue?.[0], { scrub: true });
          }}
          aria-label={jointName || "Joint value"}
          title={`${formatJointValue(minValueDeg, joint)} to ${formatJointValue(maxValueDeg, joint)}`}
        />
    </FileSheetSliderField>
  );
});

const SdfValueField = FileSheetValueField;

function formatSdfMetadataItem(item, fields) {
  if (!item || typeof item !== "object") {
    return "";
  }
  return fields
    .map((field) => String(item?.[field] || "").trim())
    .filter(Boolean)
    .join(" / ");
}

function SdfMetadataList({ title, items, fields }) {
  const records = Array.isArray(items)
    ? items.map((item) => formatSdfMetadataItem(item, fields)).filter(Boolean)
    : [];
  if (!records.length) {
    return null;
  }
  return (
    <div className="space-y-1.5 rounded-md border border-border/80 bg-background/40 p-2">
      <span className={FILE_SHEET_FIELD_LABEL_CLASSES}>{title}</span>
      <div className="space-y-1">
        {records.slice(0, 5).map((record, index) => (
          <div
            key={`${title}:${index}`}
            className="truncate text-[11px] font-medium leading-4 text-foreground"
            title={record}
          >
            {record}
          </div>
        ))}
        {records.length > 5 ? (
          <div className="text-[11px] leading-4 text-muted-foreground">{records.length - 5} more</div>
        ) : null}
      </div>
    </div>
  );
}

export default function UrdfFileSheet({
  open,
  title = "URDF",
  sourceFormat = "urdf",
  showJoints = true,
  isDesktop,
  width,
  selectedEntry = null,
  onOpenChange,
  onStartResize,
  joints,
  components = [],
  componentSelection,
  groupStates,
  activeGroupStateId,
  jointValues,
  onJointValueChange,
  onGroupStateSelect,
  onCopyJointAngles,
  onResetPose,
  sdf = null,
  viewerServerInfo = null,
  suppressDynamicMetadataStatus = false,
  statusItems = [],
  themeTabs = [],
  openSectionIds = [],
  onOpenSectionIdsChange
}) {
  const isSdf = String(sourceFormat || "").trim().toLowerCase() === "sdf";
  const movableJoints = Array.isArray(joints) ? joints : [];
  const groupStatePresets = Array.isArray(groupStates) ? groupStates : [];
  const sdfInfo = sdf?.info && typeof sdf.info === "object" ? sdf.info : {};
  const sdfStaticMetadata = sdfInfo.staticMetadata && typeof sdfInfo.staticMetadata === "object"
    ? sdfInfo.staticMetadata
    : {};
  const sdfIncludes = Array.isArray(sdfStaticMetadata.includes) ? sdfStaticMetadata.includes : [];
  const sdfPlugins = Array.isArray(sdfStaticMetadata.plugins) ? sdfStaticMetadata.plugins : [];
  const sdfSensors = Array.isArray(sdfStaticMetadata.sensors) ? sdfStaticMetadata.sensors : [];
  const sdfLights = Array.isArray(sdfStaticMetadata.lights) ? sdfStaticMetadata.lights : [];
  const sdfPhysics = Array.isArray(sdfStaticMetadata.physics) ? sdfStaticMetadata.physics : [];
  const sdfNestedModelCount = Number.isFinite(Number(sdfStaticMetadata.nestedModelCount))
    ? Number(sdfStaticMetadata.nestedModelCount)
    : 0;
  const hasSdfMetadata = Boolean(
    sdfIncludes.length ||
    sdfPlugins.length ||
    sdfSensors.length ||
    sdfLights.length ||
    sdfPhysics.length
  );
  const activeGroupStateValue = groupStatePresets.some((state) => String(state?.id || "").trim() === activeGroupStateId)
    ? activeGroupStateId
    : "__custom__";
  const activeGroupState = groupStatePresets.find((state) => String(state?.id || "").trim() === activeGroupStateValue);
  const activeGroupStateLabel = activeGroupStateValue === "__custom__" ? "custom" : String(activeGroupState?.label || activeGroupState?.name || activeGroupStateValue);

  const sections = [
    buildFileStatusTab(statusItems),
    isSdf ? {
      id: "sdf",
      title: "SDF",
      content: (
              <div>
                <FileSheetSubsection title="Document">
                <FileSheetFieldGrid columns={2}>
                  <SdfValueField label="Version" value={String(sdfInfo.version || "unknown")} />
                  <SdfValueField label="Document" value={String(sdfInfo.documentKind || "model")} />
                  {sdfInfo.worldName ? (
                    <SdfValueField label="World" value={String(sdfInfo.worldName)} />
                  ) : null}
                  <SdfValueField label="Frame mode" value={sdfInfo.nativeFrameSemantics ? "native" : "compat"} />
                  <SdfValueField label="Root link" value={String(sdfInfo.rootLink || "")} />
                  <SdfValueField label="Model" value={String(sdfInfo.modelName || title || "model")} />
                </FileSheetFieldGrid>
                </FileSheetSubsection>

                <FileSheetSubsection title="Counts">
                <FileSheetFieldGrid columns={3}>
                  <SdfValueField label="Links" value={String(sdfInfo.linkCount ?? movableJoints.length)} />
                  <SdfValueField label="Joints" value={String(sdfInfo.jointCount ?? joints?.length ?? 0)} />
                  <SdfValueField label="Frames" value={String(sdfInfo.frameCount ?? 0)} />
                  <SdfValueField label="Includes" value={String(sdfIncludes.length)} />
                  <SdfValueField label="Plugins" value={String(sdfPlugins.length)} />
                  <SdfValueField label="Sensors" value={String(sdfSensors.length)} />
                  <SdfValueField label="Lights" value={String(sdfLights.length)} />
                  <SdfValueField label="Physics" value={String(sdfPhysics.length)} />
                  <SdfValueField label="Nested models" value={formatSdfNumber(sdfNestedModelCount)} />
                  <SdfValueField label="Unsupported geom." value={`${formatSdfNumber(sdfInfo.unsupportedVisualCount)} / ${formatSdfNumber(sdfInfo.unsupportedCollisionCount)}`} />
                </FileSheetFieldGrid>
                </FileSheetSubsection>

                {hasSdfMetadata ? (
                  <FileSheetSubsection title="Metadata" contentClassName="px-2">
                    <SdfMetadataList title="Includes" items={sdfIncludes} fields={["name", "uri"]} />
                    <SdfMetadataList title="Plugins" items={sdfPlugins} fields={["name", "filename"]} />
                    <SdfMetadataList title="Sensors" items={sdfSensors} fields={["name", "type"]} />
                    <SdfMetadataList title="Lights" items={sdfLights} fields={["name", "type"]} />
                    <SdfMetadataList title="Physics" items={sdfPhysics} fields={["name", "type", "default"]} />
                  </FileSheetSubsection>
                ) : null}
              </div>
      )
    } : null,
    components.length ? {
      id: "components",
      title: "Components",
      titleAttr: "Named exported mesh components",
      content: (
        <RobotComponentsSection
          components={components}
          selectedIds={componentSelection.selectedIds}
          onSelect={componentSelection.select}
          onHover={componentSelection.hover}
        />
      )
    } : null,
    components.length ? {
      id: "reference",
      title: "Reference",
      content: <RobotComponentReferenceSection components={components} selectedIds={componentSelection.selectedIds} />
    } : null,
    showJoints ? {
      id: "joints",
      title: "Joints",
      content: (
            movableJoints.length ? (
              <>
                <FileSheetSubsection title="Pose">
                  {groupStatePresets.length ? (
                    // The tab's primary control: a named state rewrites every
                    // joint value below it.
                    <FileSheetSelectRow
                      stacked
                      label="Group state"
                      value={activeGroupStateValue}
                      onValueChange={(value) => {
                        if (value === "__custom__") {
                          return;
                        }
                        const groupState = groupStatePresets.find((candidate) => String(candidate?.id || "").trim() === value);
                        if (groupState) {
                          onGroupStateSelect?.(groupState);
                        }
                      }}
                      ariaLabel="Group state"
                      triggerContent={<span className="truncate">{activeGroupStateLabel}</span>}
                      options={groupStatePresets.map((groupState) => {
                        const groupStateId = String(groupState?.id || "").trim();
                        return {
                          value: groupStateId,
                          label: String(groupState?.label || groupState?.name || "").trim() || "State"
                        };
                      })}
                    />
                  ) : null}
                  <FileSheetButtonRow>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className={cn(compactButtonClasses, "justify-center")}
                      onClick={onResetPose}
                    >
                      <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                      <span>Reset pose</span>
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className={cn(compactButtonClasses, "justify-center")}
                      onClick={() => {
                        void onCopyJointAngles?.();
                      }}
                    >
                      <Copy className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                      <span>{isSdf ? "Copy values" : "Copy angles"}</span>
                    </Button>
                  </FileSheetButtonRow>
                </FileSheetSubsection>
                <FileSheetSubsection title="Values">
                {movableJoints.map((joint) => (
                  <UrdfJointRow
                    key={joint.name}
                    joint={joint}
                    valueDeg={jointValues?.[joint.name] ?? joint?.defaultValueDeg ?? 0}
                    onValueChange={onJointValueChange}
                  />
                ))}
                </FileSheetSubsection>
              </>
            ) : (
              <FileSheetStatusText className="py-2">No movable joints.</FileSheetStatusText>
            )
      )
    } : null,
    ...themeTabs
  ];

  return (
    <FileSheet
      open={open}
      title={title}
      isDesktop={isDesktop}
      width={width}
      onOpenChange={onOpenChange}
      onStartResize={onStartResize}
      scrollBody={false}
    >
      <FileSheetTabbedSurface
        kind={isSdf ? "sdf" : (sourceFormat || "urdf")}
        sections={sections}
        openSectionIds={openSectionIds}
        onOpenSectionIdsChange={onOpenSectionIdsChange}
      />
    </FileSheet>
  );
}

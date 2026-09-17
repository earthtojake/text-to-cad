import { cn } from "@/ui/utils";
import { resolveParameterNumberControlStep } from "@/workbench/parameterControls";
import {
  poseControlDisplayValue,
  poseControlWrite,
  poseDisplayValues,
  poseDrivenDofs
} from "@/workbench/poseDrivenControls";
import { Button } from "../ui/button";
import { Slider } from "../ui/slider";
import {
  NO_PRESET_VALUE,
  KinematicsPoseRow,
  KinematicsTransitionSubsection,
  KinematicsValueActions
} from "./KinematicsControls";
import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetButtonRow,
  FileSheetColorPicker,
  FileSheetControlRow,
  FileSheetSelectRow,
  FileSheetSliderField,
  FileSheetStatusText,
  FileSheetSubsection,
  FileSheetToggleRow,
  FileSheetValueInput,
  parseFileSheetNumberInput
} from "./FileSheet";

// The POSE tab: one control per kinematic DOF, plus the model's named presets.
//
// Half of the pose/animation split — this section knows nothing about clips or
// playback. Choreography is AnimationControlsSection, driven by its own state;
// the two compose in the viewport and nowhere else.

const compactButtonClasses = FILE_SHEET_COMPACT_BUTTON_CLASSES;

function formatControlNumber(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return "0";
  }
  if (Math.abs(numericValue) >= 100) {
    return numericValue.toFixed(0);
  }
  if (Math.abs(numericValue) >= 10) {
    return numericValue.toFixed(1);
  }
  return numericValue.toFixed(2);
}

// The model's named configurations, straight off the sidecar's kinematics
// block. A preset is a full configuration, not a patch: applying one puts every
// DOF it does not name back at 0 (the artifact as written), so clicking two
// presets in a row can never leave a joint from the first one behind.
function poseNamesFromDefinition(definition) {
  const poses = definition?.manifest?.poses;
  if (!poses || typeof poses !== "object" || Array.isArray(poses)) {
    return [];
  }
  return Object.keys(poses).filter((name) => String(name || "").trim());
}

// Which named pose the model is IN, or "" when a DOF has been moved since. Same
// question the robot sheet asks of its group states, so the dropdown reads the same
// way in both: the preset that is on, or "None".
export function activePoseName(definition, values) {
  for (const poseName of poseNamesFromDefinition(definition)) {
    const preset = poseValuesForPreset(definition, poseName);
    const matches = Object.entries(preset).every(([dof, value]) => {
      const current = values?.[dof];
      if (typeof value === "number" && typeof current === "number") {
        return Math.abs(current - value) <= 1e-6;
      }
      return current === value || (current == null && value == null);
    });
    if (matches) {
      return poseName;
    }
  }
  return "";
}

export function poseValuesForPreset(definition, poseName) {
  const preset = definition?.manifest?.poses?.[poseName];
  const values = { ...(definition?.defaultParameterValues || {}) };
  if (preset && typeof preset === "object") {
    for (const [dof, value] of Object.entries(preset)) {
      if (Object.hasOwn(values, dof)) {
        values[dof] = Number(value) || 0;
      }
    }
  }
  return values;
}

export default function PoseControlsSection({
  runtime = null,
  loadingLabel = "Loading pose...",
  noParametersLabel = "No pose controls.",
  hideWhenEmpty = false,
  resetTitle = "Reset every value to the model as authored"
}) {
  const definition = runtime?.definition || null;
  const parameters = Array.isArray(definition?.parameters) ? definition.parameters : [];
  const status = String(runtime?.status || "").trim();
  const error = String(runtime?.error || "").trim();
  const values = runtime?.parameterValues || {};
  // The pose-transition preference rides the runtime like every other pose concern.
  const transition = runtime?.transition || null;
  const poseNames = poseNamesFromDefinition(definition);
  // Which pose is on: the one the person picked, until they move a DOF by hand; then
  // whichever preset the values match, or "None". The robot's group state reads the
  // same way, so the two dropdowns cannot disagree about what "the current pose" means.
  const pickedPose = String(runtime?.activePose || "");
  const activePose = pickedPose && poseNames.includes(pickedPose)
    ? pickedPose
    : (activePoseName(definition, values) || NO_PRESET_VALUE);
  // Back-drive routing: which members a coupling drives, and what every DOF's
  // effective value is. Both are pure functions of the definition and the
  // current values, so a driven slider needs no state of its own.
  const drivenDofs = poseDrivenDofs(definition);
  const displayValues = poseDisplayValues(definition, values);
  const changeParameter = (parameterId, value) => {
    const write = poseControlWrite({ driven: drivenDofs, values, parameterId, value });
    runtime?.onParameterChange?.(write.id, write.value);
  };
  if (!poseControlsHaveContent(runtime, { hideWhenEmpty })) {
    return null;
  }

  return (
    <div className="py-2">
      {status === "loading" ? (
        <FileSheetStatusText className="py-2">{loadingLabel}</FileSheetStatusText>
      ) : null}
      {error ? (
        <FileSheetStatusText tone="error" className="py-2">{error}</FileSheetStatusText>
      ) : null}

      {definition ? (
        <FileSheetSubsection title="Position">
          {/* A pose is a way of SETTING the values, so it leads them. */}
          {poseNames.length ? (
            <KinematicsPoseRow
              poses={poseNames.map((poseName) => ({ value: poseName, label: poseName }))}
              activeValue={activePose}
              onSelect={(poseName) => runtime?.onApplyPose?.(poseName)}
            />
          ) : null}
          {!parameters.length ? (
            <FileSheetStatusText>{noParametersLabel}</FileSheetStatusText>
          ) : null}
          {parameters.map((parameter) => {
            const driver = drivenDofs[parameter.id] || null;
            const currentValue = poseControlDisplayValue({
              driven: drivenDofs,
              displayValues,
              values,
              parameter
            });
            const controlStep = resolveParameterNumberControlStep(parameter);
            if (parameter.type === "boolean") {
              return (
                <FileSheetToggleRow
                  key={parameter.id}
                  label={parameter.label}
                  checked={currentValue === true}
                  onCheckedChange={(checked) => runtime?.onParameterChange?.(parameter.id, checked)}
                          ariaLabel={parameter.label}
                />
              );
            }
            if (parameter.type === "enum") {
              return (
                <FileSheetSelectRow
                  key={parameter.id}
                  label={parameter.label}
                  value={String(currentValue ?? "")}
                  onValueChange={(nextValue) => runtime?.onParameterChange?.(parameter.id, nextValue)}
                          ariaLabel={parameter.label}
                  options={parameter.options}
                />
              );
            }
            if (parameter.type === "color") {
              return (
                <FileSheetControlRow
                  key={parameter.id}
                  label={parameter.label}
                  trailing={(
                    <FileSheetColorPicker
                      value={String(currentValue || "#ffffff")}
                      onChange={(nextValue) => runtime?.onParameterChange?.(parameter.id, nextValue)}
                                  aria-label={parameter.label}
                    />
                  )}
                />
              );
            }
            if (parameter.type === "button") {
              return (
                <FileSheetButtonRow key={parameter.id}>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className={cn(compactButtonClasses, "justify-center")}
                    onClick={() => runtime?.onParameterChange?.(parameter.id, Number(currentValue || 0) + 1)}
                            >
                    {parameter.label}
                  </Button>
                </FileSheetButtonRow>
              );
            }
            if (parameter.type === "string") {
              return (
                <FileSheetControlRow
                  key={parameter.id}
                  label={parameter.label}
                  trailing={(
                    <FileSheetValueInput
                      value={String(currentValue ?? "")}
                      onValueCommit={(nextValue) => runtime?.onParameterChange?.(parameter.id, nextValue)}
                                  inputMode="text"
                      ariaLabel={`${parameter.label} value`}
                      className="w-40 max-w-[min(12rem,55vw)] text-left font-medium tabular-nums"
                    />
                  )}
                />
              );
            }
            return (
              <FileSheetSliderField
                key={parameter.id}
                // A driven member says so: its slider reads the effective value
                // and writes through the coupling named here, never into itself.
                label={driver ? (
                  <>
                    {parameter.label}
                    <span className="ml-1 font-normal opacity-70">{`· driven by ${driver.coupling}`}</span>
                  </>
                ) : parameter.label}
                value={`${formatControlNumber(currentValue)}${parameter.unit ? ` ${parameter.unit}` : ""}`}
                onValueCommit={(nextValue) => {
                  changeParameter(parameter.id, parseFileSheetNumberInput(nextValue, {
                    fallback: currentValue,
                    min: parameter.min,
                    max: parameter.max
                  }));
                }}
                valueInputProps={{
                  ariaLabel: `${parameter.label} slider value`
                }}
              >
                <Slider
                  className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
                  value={[Number(currentValue) || 0]}
                  min={parameter.min}
                  max={parameter.max}
                  step={controlStep}
                  onValueChange={(nextValue) => changeParameter(parameter.id, nextValue?.[0] ?? currentValue)}
                          aria-label={parameter.label}
                />
              </FileSheetSliderField>
            );
          })}
          <KinematicsValueActions
            onReset={runtime?.onResetParameters ? () => runtime.onResetParameters() : null}
            onCopy={runtime?.onCopyParams ? () => runtime.onCopyParams() : null}
            resetTitle={resetTitle}
            copyTitle="Copy the current parameter values"
          />
        </FileSheetSubsection>
      ) : null}

      {definition && poseNames.length ? (
        <KinematicsTransitionSubsection transition={transition} />
      ) : null}
    </div>
  );
}

// Whether the pose controls would render any content for this runtime.
export function poseControlsHaveContent(runtime, { hideWhenEmpty = false } = {}) {
  const definition = runtime?.definition || null;
  const parameters = Array.isArray(definition?.parameters) ? definition.parameters : [];
  const status = String(runtime?.status || "").trim();
  const error = String(runtime?.error || "").trim();
  if (hideWhenEmpty && definition && !parameters.length && status !== "loading" && !error) {
    return false;
  }
  return Boolean(definition || status === "loading" || error);
}

// Build the kinematics tab descriptor, or null when there is nothing to show.
// The tab is named for the system it drives; "pose" stays the word for the
// state that system holds, and for the section id persisted in tab layouts.
export function buildPoseControlsTab(props = {}) {
  if (!poseControlsHaveContent(props.runtime, { hideWhenEmpty: props.hideWhenEmpty })) {
    return null;
  }
  return {
    id: props.value || "pose",
    title: props.title || "Kinematics",
    content: <PoseControlsSection {...props} />
  };
}

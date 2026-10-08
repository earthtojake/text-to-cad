import {
  articulationControls,
  articulationPoses,
  openingControlValues,
  poseControlValues
} from "@text-to-cad/core/common/articulation.js";
import { resolveParameterNumberControlStep } from "../../workbench/parameterControls.js";
import {
  poseControlDisplayValue,
  poseControlWrite,
  poseDisplayValues,
  poseDrivenDofs
} from "../../workbench/poseDrivenControls.js";
import { Slider } from "@text-to-cad/ui/primitives/slider";
import {
  NO_PRESET_VALUE, DEFAULT_POSE_VALUE, positionValuesAreDefault,
  KinematicsPoseRow
} from "../../../kit/inspector/kinematicsControls.jsx";
import {
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetSliderField,
  FileSheetStatusText,
  parseFileSheetNumberInput
} from "../../../kit/inspector/FileSheet.js";

// The host coordinates pose ownership with Animation; these rows stay editable.

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

// A value's unit as its compact field shows it: degrees as the sign ("90.0°"), others after a space.
function unitSuffix(unit) {
  const text = String(unit || "").trim();
  return !text ? "" : /^(deg|degrees?|°)$/i.test(text) ? "°" : ` ${text}`;
}

// The model's named configurations, straight off the articulation. A preset is a full
// configuration, not a patch: applying one puts every control it does not name back at
// its rest value, so clicking two presets in a row can never leave a joint from the first
// one behind.
function poseNamesFromDefinition(definition) {
  return Object.keys(articulationPoses(definition?.articulation)).filter((name) => String(name || "").trim());
}

// Which named pose the model is IN, or "" when a control has been moved since. Same
// question the robot sheet asks of its group states, so the dropdown reads the same
// way in both: the preset that is on, or "None".
export function activePoseName(definition, values) {
  for (const poseName of poseNamesFromDefinition(definition)) {
    const preset = poseControlValues(definition?.articulation, poseName);
    const matches = Object.entries(preset).every(([control, value]) => {
      const current = values?.[control];
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

// Resolve the selected authored pose from the shared position runtime.
export function posePresetSelection(runtime) {
  const definition = runtime?.definition;
  const poseNames = poseNamesFromDefinition(definition);
  const pickedPose = String(runtime?.activePose || "");
  const activePose = runtime?.positionActive === false ? NO_PRESET_VALUE
    : pickedPose && poseNames.includes(pickedPose) ? pickedPose
    : positionValuesAreDefault(runtime?.parameterValues, openingControlValues(definition?.articulation)) ? DEFAULT_POSE_VALUE
    : activePoseName(definition, runtime?.parameterValues || {}) || NO_PRESET_VALUE;
  return { poseNames, activePose };
}

export default function PoseControlsSection({ runtime = null }) {
  const onReset = runtime?.onResetMotion || runtime?.onResetParameters;
  const definition = runtime?.definition || null;
  const controls = articulationControls(definition?.articulation);
  const status = String(runtime?.status || "").trim();
  const error = String(runtime?.error || "").trim();
  const values = runtime?.parameterValues || {};
  const { poseNames, activePose } = posePresetSelection(runtime);
  // Back-drive routing: which members a coupling drives, and what every row's
  // value is. Both are pure functions of the articulation and the current
  // values, so a driven slider needs no state of its own.
  const drivenDofs = poseDrivenDofs(definition);
  const displayValues = poseDisplayValues(definition, values);
  const changeParameter = (parameterId, value) => {
    const write = poseControlWrite({ definition, values, parameterId, value });
    runtime?.onParameterChange?.(write.id, write.value);
  };
  if (!poseControlsHaveContent(runtime)) {
    return null;
  }

  return (
    <>
      {status === "loading" ? (
        <FileSheetStatusText className="py-2">Loading pose...</FileSheetStatusText>
      ) : null}
      {error ? (
        <FileSheetStatusText tone="error" className="py-2">{error}</FileSheetStatusText>
      ) : null}

      {definition ? (
        <>
          {poseNames.length ? (
            <KinematicsPoseRow
              poses={poseNames.map((poseName) => ({ value: poseName, label: poseName }))}
              activeValue={activePose}
              onReset={onReset}
              onSelect={(poseName) => runtime?.onApplyPose?.(poseName)}
            />
          ) : null}
          {controls.map((control) => {
            const driver = drivenDofs[control.id] || null;
            const label = String(control.label || control.id);
            const currentValue = poseControlDisplayValue({
              driven: drivenDofs,
              displayValues,
              values,
              parameter: control
            });
            const controlStep = resolveParameterNumberControlStep(control);
            return (
              <FileSheetSliderField
                key={control.id}
                label={label}
                labelTitle={driver ? `${label} · driven by ${driver.control}` : label}
                value={`${formatControlNumber(currentValue)}${unitSuffix(control.unit)}`}
                onValueCommit={(nextValue) => {
                  changeParameter(control.id, parseFileSheetNumberInput(nextValue, {
                    fallback: currentValue,
                    min: control.min,
                    max: control.max
                  }));
                }}
                valueInputProps={{ ariaLabel: `${label} slider value` }}
              >
                <Slider
                  className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
                  value={[Number(currentValue) || 0]}
                  min={control.min}
                  max={control.max}
                  step={controlStep}
                  onValueChange={(nextValue) => changeParameter(control.id, nextValue?.[0] ?? currentValue)}
                  thumbProps={{ "aria-label": label }}
                />
              </FileSheetSliderField>
            );
          })}
          {!controls.length && !poseNames.length ? <FileSheetStatusText>No pose controls.</FileSheetStatusText> : null}
        </>
      ) : null}
    </>
  );
}

// Whether the pose controls would render any content for this runtime.
export function poseControlsHaveContent(runtime) {
  const status = String(runtime?.status || "").trim();
  const error = String(runtime?.error || "").trim();
  return Boolean(runtime?.definition || status === "loading" || error);
}

import {
  poseControlDisplayValue,
  poseControlWrite,
  poseDisplayValues,
  poseDrivenDofs
} from "../../workbench/poseDrivenControls.js";
import {
  NO_PRESET_VALUE, DEFAULT_POSE_VALUE, positionValuesAreDefault,
  KinematicsPoseRow
} from "../../../kit/inspector/kinematicsControls.jsx";
import { FileSheetStatusText } from "../../../kit/inspector/FileSheet.js";
import { parameterRow } from "../../../kit/inspector/parameterRow.jsx";

// The host coordinates pose ownership with Animation; these rows stay editable.

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

// Resolve the selected authored pose from the shared position runtime.
export function posePresetSelection(runtime) {
  const definition = runtime?.definition;
  const poseNames = poseNamesFromDefinition(definition);
  const pickedPose = String(runtime?.activePose || "");
  const activePose = runtime?.positionActive === false ? NO_PRESET_VALUE
    : pickedPose && poseNames.includes(pickedPose) ? pickedPose
    : positionValuesAreDefault(runtime?.parameterValues, definition?.defaultParameterValues) ? DEFAULT_POSE_VALUE
    : activePoseName(definition, runtime?.parameterValues || {}) || NO_PRESET_VALUE;
  return { poseNames, activePose };
}

export default function PoseControlsSection({ runtime = null }) {
  const onReset = runtime?.onResetMotion || runtime?.onResetParameters;
  const definition = runtime?.definition || null;
  const parameters = Array.isArray(definition?.parameters) ? definition.parameters : [];
  const status = String(runtime?.status || "").trim();
  const error = String(runtime?.error || "").trim();
  const values = runtime?.parameterValues || {};
  const { poseNames, activePose } = posePresetSelection(runtime);
  // Back-drive routing: which members a coupling drives, and what every DOF's
  // effective value is. Both are pure functions of the definition and the
  // current values, so a driven slider needs no state of its own.
  const drivenDofs = poseDrivenDofs(definition);
  const displayValues = poseDisplayValues(definition, values);
  const changeParameter = (parameterId, value) => {
    const write = poseControlWrite({ driven: drivenDofs, values, parameterId, value });
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
          {parameters.map((parameter) => {
            const driver = drivenDofs[parameter.id] || null;
            const currentValue = poseControlDisplayValue({
              driven: drivenDofs,
              displayValues,
              values,
              parameter
            });
            // A number goes through the back-drive routing; every other type is written as it is.
            const numeric = !["boolean", "enum", "color", "button", "string"].includes(parameter.type);
            return parameterRow({
              parameter,
              value: currentValue,
              labelTitle: driver ? `${parameter.label} · driven by ${driver.coupling}` : parameter.label,
              onChange: (nextValue) => numeric ? changeParameter(parameter.id, nextValue) : runtime?.onParameterChange?.(parameter.id, nextValue)
            });
          })}
          {!parameters.length && !poseNames.length ? <FileSheetStatusText>No pose controls.</FileSheetStatusText> : null}
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

import { RotateCcw } from "lucide-react";
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
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetButtonRow,
  FileSheetColorPicker,
  FileSheetControlRow,
  FileSheetSelectRow,
  FileSheetSliderField,
  FileSheetStatusText,
  FileSheetSubsection,
  FileSheetBooleanToggle,
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
  title = "Kinematics",
  runtime = null,
  loadingLabel = "Loading pose...",
  noParametersLabel = "No pose controls.",
  hideWhenEmpty = false,
  showEnableToggle = false,
  enableLabel = "Enable",
  enableAriaLabel = "",
  resetTitle = "Reset pose"
}) {
  const definition = runtime?.definition || null;
  const parameters = Array.isArray(definition?.parameters) ? definition.parameters : [];
  const status = String(runtime?.status || "").trim();
  const error = String(runtime?.error || "").trim();
  const values = runtime?.parameterValues || {};
  const enabled = runtime?.enabled !== false;
  const poseNames = poseNamesFromDefinition(definition);
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
        <FileSheetSubsection
          title={title}
          // The mate gate rides this heading on the shared right-edge control axis rather
          // than owning a "Module" section for one switch.
          trailing={showEnableToggle ? (
            <FileSheetBooleanToggle
              checked={enabled}
              onCheckedChange={(checked) => runtime?.onEnabledChange?.(checked)}
              ariaLabel={enableAriaLabel || enableLabel}
            />
          ) : null}
        >
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
                  disabled={!enabled}
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
                  disabled={!enabled}
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
                      disabled={!enabled}
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
                    disabled={!enabled}
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
                      disabled={!enabled}
                      inputMode="text"
                      ariaLabel={`${parameter.label} value`}
                      className="w-40 max-w-[min(12rem,55vw)] text-left tabular-nums"
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
                    <span className="ml-1 opacity-70">{`· driven by ${driver.coupling}`}</span>
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
                  disabled: !enabled,
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
                  disabled={!enabled}
                  aria-label={parameter.label}
                />
              </FileSheetSliderField>
            );
          })}
          {runtime?.onResetParameters ? (
            <FileSheetButtonRow>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className={cn(compactButtonClasses, "justify-center")}
                onClick={() => runtime.onResetParameters()}
                title={resetTitle}
              >
                <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                <span>Reset</span>
              </Button>
            </FileSheetButtonRow>
          ) : null}
        </FileSheetSubsection>
      ) : null}

      {/* Presets follow the sliders they drive: each one is a named configuration
          the model itself declares, so it belongs to this tab and not to a menu. */}
      {definition && poseNames.length ? (
        <FileSheetSubsection title="Presets">
          <FileSheetButtonRow columns={poseNames.length > 1 ? 2 : 1}>
            {poseNames.map((poseName) => (
              <Button
                key={poseName}
                type="button"
                variant="outline"
                size="sm"
                className={cn(compactButtonClasses, "justify-center")}
                onClick={() => runtime?.onApplyPose?.(poseName)}
                disabled={!enabled}
                title={`Apply the ${poseName} pose`}
              >
                <span className="truncate">{poseName}</span>
              </Button>
            ))}
          </FileSheetButtonRow>
        </FileSheetSubsection>
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

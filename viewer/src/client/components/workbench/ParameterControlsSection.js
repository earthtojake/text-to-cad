import { Pause, Play, RotateCcw } from "lucide-react";
import { cn } from "@/ui/utils";
import { resolveParameterNumberControlStep } from "@/workbench/parameterControls";
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
  FileSheetToggleRow,
  FileSheetValueInput,
  parseFileSheetNumberInput
} from "./FileSheet";

const compactButtonClasses = FILE_SHEET_COMPACT_BUTTON_CLASSES;
const PARAMETER_ANIMATION_SPEED_MIN = 0.1;
const PARAMETER_ANIMATION_SPEED_MAX = 3;

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

function formatSeconds(value) {
  const numericValue = Math.max(Number(value) || 0, 0);
  return `${numericValue.toFixed(numericValue >= 10 ? 1 : 2)}s`;
}

function parseAnimationSpeedInput(value, fallbackValue = 1) {
  return parseFileSheetNumberInput(value, {
    fallback: fallbackValue,
    min: PARAMETER_ANIMATION_SPEED_MIN,
    max: PARAMETER_ANIMATION_SPEED_MAX
  });
}

// The default animation time control: it reads elapsed time straight off the
// runtime's animation state. A consumer whose elapsed time lives in a store
// that ticks during playback (the STEP module) passes its own through the
// `TimeControl` prop so the slider tracks the animation instead of sitting
// still between renders. Contract: { animationState, duration, enabled,
// onScrub, label }.
export function ParameterAnimationTimeControl({
  animationState = {},
  duration,
  enabled,
  onScrub,
  label = "parameter"
}) {
  const elapsedSec = Number(animationState.elapsedSec) || 0;
  return (
    <FileSheetSliderField
      label="Time"
      value={formatSeconds(elapsedSec)}
      onValueCommit={(nextValue) => {
        onScrub?.(parseFileSheetNumberInput(nextValue, {
          fallback: elapsedSec,
          min: 0,
          max: duration
        }));
      }}
      valueInputProps={{
        disabled: !enabled,
        ariaLabel: `${label} animation time value`
      }}
    >
      <Slider
        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
        value={[elapsedSec]}
        min={0}
        max={duration}
        step={0.01}
        onValueChange={(nextValue) => onScrub?.(nextValue?.[0] ?? 0)}
        disabled={!enabled}
        aria-label={`${label} animation time`}
      />
    </FileSheetSliderField>
  );
}

export default function ParameterControlsSection({
  value = "parameters",
  title = "Parameters",
  runtime = null,
  label = "parameter",
  loadingLabel = "Loading parameters...",
  noParametersLabel = "No parameters.",
  hideWhenEmpty = false,
  showEnableToggle = false,
  enableLabel = "Enable",
  enableAriaLabel = "",
  animationAriaLabel = "Animation",
  resetTitle = "Reset parameters",
  TimeControl = ParameterAnimationTimeControl
}) {
  const definition = runtime?.definition || null;
  const parameters = Array.isArray(definition?.parameters) ? definition.parameters : [];
  const animations = Array.isArray(definition?.animations) ? definition.animations : [];
  const status = String(runtime?.status || "").trim();
  const error = String(runtime?.error || "").trim();
  const values = runtime?.parameterValues || {};
  const animationState = runtime?.animationState || {};
  const animationDuration = Math.max(Number(animationState.duration) || 1, 0.001);
  const enabled = runtime?.enabled !== false;
  if (!parameterControlsHasContent(runtime, { hideWhenEmpty })) {
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

      {definition && showEnableToggle ? (
        <FileSheetSubsection title="Module">
          <FileSheetToggleRow
            label={enableLabel}
            checked={enabled}
            onCheckedChange={(checked) => runtime?.onEnabledChange?.(checked)}
            ariaLabel={enableAriaLabel || enableLabel}
          />
        </FileSheetSubsection>
      ) : null}

      {/* Playback is its own group above the parameters: it acts on time, not
          on the model's inputs, and it is absent for most models. */}
      {definition && animations.length ? (
        <FileSheetSubsection title="Animation">
          {animations.length > 1 ? (
            // The section's primary control: which clip is selected reframes the
            // transport and the time/speed rows beneath it.
            <FileSheetSelectRow
              stacked
              label="Clip"
              value={String(animationState.activeId || animations[0]?.id || "")}
              onValueChange={(nextValue) => runtime?.onAnimationSelect?.(nextValue)}
              disabled={!enabled}
              ariaLabel={animationAriaLabel}
              options={animations.map((animation) => ({
                value: animation.id,
                label: animation.label
              }))}
            />
          ) : null}
          {/* Transport sits under the clip it drives. "Restart" is deliberately
              not called "Reset": it returns playback to zero, where the tab's
              one Reset returns the parameters to their defaults. */}
          <FileSheetButtonRow columns={2}>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={cn(compactButtonClasses, "justify-center")}
              onClick={() => runtime?.onAnimationPlayToggle?.()}
              disabled={!enabled}
              aria-label={`${animationState.playing ? "Pause" : "Play"} ${label} animation`}
              title={`${animationState.playing ? "Pause" : "Play"} ${label} animation`}
            >
              {animationState.playing ? (
                <Pause className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
              ) : (
                <Play className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
              )}
              <span>{animationState.playing ? "Pause" : "Play"}</span>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={cn(compactButtonClasses, "justify-center")}
              onClick={() => runtime?.onAnimationReset?.()}
              disabled={!enabled}
              aria-label={`Restart ${label} animation`}
              title="Restart"
            >
              <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
              <span>Restart</span>
            </Button>
          </FileSheetButtonRow>
          <FileSheetToggleRow
            label="Loop"
            checked={animationState.loopEnabled !== false}
            onCheckedChange={(checked) => runtime?.onAnimationLoopToggle?.(checked)}
            disabled={!enabled}
            ariaLabel="Loop animation playback"
          />
          <TimeControl
            animationState={animationState}
            duration={animationDuration}
            enabled={enabled}
            onScrub={runtime?.onAnimationScrub}
            label={label}
          />
          <FileSheetSliderField
            label="Speed"
            value={`${formatControlNumber(animationState.speed || 1)}x`}
            onValueCommit={(nextValue) => {
              runtime?.onAnimationSpeedChange?.(
                parseAnimationSpeedInput(nextValue, animationState.speed || 1)
              );
            }}
            valueInputProps={{
              disabled: !enabled,
              ariaLabel: `${label} animation speed value`
            }}
          >
            <Slider
              className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
              value={[Number(animationState.speed) || 1]}
              min={PARAMETER_ANIMATION_SPEED_MIN}
              max={PARAMETER_ANIMATION_SPEED_MAX}
              step={0.1}
              onValueChange={(nextValue) => runtime?.onAnimationSpeedChange?.(nextValue?.[0] ?? 1)}
              disabled={!enabled}
              aria-label={`${label} animation speed`}
            />
          </FileSheetSliderField>
        </FileSheetSubsection>
      ) : null}

      {definition ? (
        <FileSheetSubsection title={title}>
          {!parameters.length ? (
            <FileSheetStatusText>{noParametersLabel}</FileSheetStatusText>
          ) : null}
          {parameters.map((parameter) => {
            const currentValue = values?.[parameter.id] ?? parameter.defaultValue;
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
                      className="w-40 max-w-[min(12rem,55vw)] text-left font-medium tabular-nums"
                    />
                  )}
                />
              );
            }
            return (
              <FileSheetSliderField
                key={parameter.id}
                label={parameter.label}
                value={`${formatControlNumber(currentValue)}${parameter.unit ? ` ${parameter.unit}` : ""}`}
                onValueCommit={(nextValue) => {
                  runtime?.onParameterChange?.(parameter.id, parseFileSheetNumberInput(nextValue, {
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
                  onValueChange={(nextValue) => runtime?.onParameterChange?.(parameter.id, nextValue?.[0] ?? currentValue)}
                  disabled={!enabled}
                  aria-label={parameter.label}
                />
              </FileSheetSliderField>
            );
          })}
          {/*
            The one reset in this tab, and it belongs to the parameters. It does
            not depend on there being an animation to reset alongside them — the
            animation's own restart button was a second thing called "Reset"
            that acted on something else entirely.
          */}
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
    </div>
  );
}

// Whether the parameter controls would render any content for this runtime.
export function parameterControlsHasContent(runtime, { hideWhenEmpty = false } = {}) {
  const definition = runtime?.definition || null;
  const parameters = Array.isArray(definition?.parameters) ? definition.parameters : [];
  const animations = Array.isArray(definition?.animations) ? definition.animations : [];
  const status = String(runtime?.status || "").trim();
  const error = String(runtime?.error || "").trim();
  const hasControls = parameters.length > 0 || animations.length > 0;
  if (hideWhenEmpty && definition && !hasControls && status !== "loading" && !error) {
    return false;
  }
  return Boolean(definition || status === "loading" || error);
}

// Build a parameter-controls tab descriptor, or null when there is nothing to show.
export function buildParameterControlsTab(props = {}) {
  if (!parameterControlsHasContent(props.runtime, { hideWhenEmpty: props.hideWhenEmpty })) {
    return null;
  }
  return {
    id: props.value || "parameters",
    title: props.title || "Parameters",
    content: <ParameterControlsSection {...props} />
  };
}

import { ClipboardPaste, Copy, Pause, Play, RotateCcw } from "lucide-react";
import { cn } from "@/ui/utils";
import { resolveParameterNumberControlStep } from "@/workbench/parameterControls";
import { Button } from "../ui/button";
import { ColorPicker } from "../ui/color-picker";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "../ui/select";
import { Slider } from "../ui/slider";
import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_COMPACT_INPUT_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetControlRow,
  FileSheetSection,
  FileSheetSectionBody,
  FileSheetSliderField,
  FileSheetToggleRow,
  FileSheetValueInput,
  parseFileSheetNumberInput
} from "./FileSheet";

const compactButtonClasses = FILE_SHEET_COMPACT_BUTTON_CLASSES;
const compactInputClasses = FILE_SHEET_COMPACT_INPUT_CLASSES;
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
  animationAriaLabel = "Animation",
  copyTitle = "Copy parameter JSON",
  pasteTitle = "Paste parameter JSON",
  resetTitle = "Reset parameters"
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
  const hasControls = parameters.length > 0 || animations.length > 0;
  if (hideWhenEmpty && definition && !hasControls && status !== "loading" && !error) {
    return null;
  }
  const hasBody = definition || status === "loading" || error;

  if (!hasBody) {
    return null;
  }

  return (
    <FileSheetSection value={value} title={title}>
      <FileSheetSectionBody>
        {definition && showEnableToggle ? (
          <FileSheetToggleRow
            label={enableLabel}
            checked={enabled}
            onCheckedChange={(checked) => runtime?.onEnabledChange?.(checked)}
            ariaLabel={enableLabel}
          />
        ) : null}

        {status === "loading" ? (
          <p className="px-3 py-2 text-xs text-[var(--ui-text-muted)]">{loadingLabel}</p>
        ) : null}
        {error ? (
          <p className="whitespace-pre-line px-3 py-2 text-xs text-destructive">{error}</p>
        ) : null}

        {definition && animations.length ? (
          <>
            {animations.length > 1 ? (
              <FileSheetControlRow label="Animation">
                <Select
                  value={String(animationState.activeId || animations[0]?.id || "")}
                  onValueChange={(nextValue) => runtime?.onAnimationSelect?.(nextValue)}
                  disabled={!enabled}
                >
                  <SelectTrigger size="sm" className="h-7 !text-[11px]" aria-label={animationAriaLabel}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {animations.map((animation) => (
                      <SelectItem key={animation.id} value={animation.id}>
                        {animation.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FileSheetControlRow>
            ) : null}
            <FileSheetControlRow>
              <div className="grid grid-cols-2 gap-2">
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
                  <span>Reset</span>
                </Button>
              </div>
            </FileSheetControlRow>
            <FileSheetSliderField
              label="Time"
              value={formatSeconds(animationState.elapsedSec)}
              onValueCommit={(nextValue) => {
                runtime?.onAnimationScrub?.(parseFileSheetNumberInput(nextValue, {
                  fallback: animationState.elapsedSec,
                  min: 0,
                  max: animationDuration
                }));
              }}
              valueInputProps={{
                disabled: !enabled,
                ariaLabel: `${label} animation time value`
              }}
            >
              <Slider
                className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
                value={[Number(animationState.elapsedSec) || 0]}
                min={0}
                max={animationDuration}
                step={0.01}
                onValueChange={(nextValue) => runtime?.onAnimationScrub?.(nextValue?.[0] ?? 0)}
                disabled={!enabled}
                aria-label={`${label} animation time`}
              />
            </FileSheetSliderField>
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
          </>
        ) : null}

        {definition && !parameters.length ? (
          <p className="px-3 py-2 text-xs text-[var(--ui-text-muted)]">{noParametersLabel}</p>
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
              <FileSheetControlRow key={parameter.id} label={parameter.label}>
                <Select
                  value={String(currentValue ?? "")}
                  onValueChange={(nextValue) => runtime?.onParameterChange?.(parameter.id, nextValue)}
                  disabled={!enabled}
                >
                  <SelectTrigger size="sm" className="h-7 !text-[11px]" aria-label={parameter.label}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {parameter.options.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FileSheetControlRow>
            );
          }
          if (parameter.type === "color") {
            return (
              <FileSheetControlRow
                key={parameter.id}
                label={parameter.label}
                trailing={(
                  <ColorPicker
                    value={String(currentValue || "#ffffff")}
                    onChange={(nextValue) => runtime?.onParameterChange?.(parameter.id, nextValue)}
                    disabled={!enabled}
                    className={cn(compactInputClasses, "w-fit justify-start gap-1.5 px-1.5")}
                    swatchClassName="size-3.5"
                    popoverAlign="end"
                    aria-label={parameter.label}
                  />
                )}
              />
            );
          }
          if (parameter.type === "button") {
            return (
              <FileSheetControlRow key={parameter.id}>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className={cn(compactButtonClasses, "w-full justify-center")}
                  onClick={() => runtime?.onParameterChange?.(parameter.id, Number(currentValue || 0) + 1)}
                  disabled={!enabled}
                >
                  {parameter.label}
                </Button>
              </FileSheetControlRow>
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
        {definition && parameters.length ? (
          <>
            <FileSheetControlRow className="pt-2">
              <div className="grid grid-cols-2 gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className={cn(compactButtonClasses, "justify-center")}
                  onClick={() => {
                    void runtime?.onCopyParams?.();
                  }}
                  title={copyTitle}
                >
                  <Copy className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                  <span>Copy parameters</span>
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className={cn(compactButtonClasses, "justify-center")}
                  onClick={() => {
                    void runtime?.onPasteParams?.();
                  }}
                  title={pasteTitle}
                >
                  <ClipboardPaste className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                  <span>Paste parameters</span>
                </Button>
              </div>
            </FileSheetControlRow>
            {runtime?.onResetParameters ? (
              <FileSheetControlRow>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className={cn(compactButtonClasses, "w-full justify-center")}
                  onClick={() => runtime.onResetParameters()}
                  title={resetTitle}
                >
                  <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                  <span>Reset parameters</span>
                </Button>
              </FileSheetControlRow>
            ) : null}
          </>
        ) : null}
      </FileSheetSectionBody>
    </FileSheetSection>
  );
}

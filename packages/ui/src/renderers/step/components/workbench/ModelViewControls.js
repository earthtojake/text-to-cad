import { normalizeExplodedViewSettings } from "@hardcore/core/lib/displaySettings.js";
import { normalizeViewSettings } from "@hardcore/core/common/viewSettings.js";
import { clipAxisBounds, normalizeStepClipSettings } from "@hardcore/core/lib/viewer/clipPlane.js";
import { ToggleGroup, ToggleGroupItem } from "@hardcore/ui/primitives/toggle-group";
import { Slider } from "@hardcore/ui/primitives/slider";
import {
  FILE_SHEET_PRECISION_SLIDER_CLASSES, FileSheetCheckboxRow, FileSheetSliderField, FileSheetValueInput,
  parseFileSheetNumberInput
} from "../../../kit/inspector/FileSheet.js";

const AXES = Object.freeze(["x", "y", "z"]);

function clamp(value, min, max) {
  return Math.min(Math.max(Number(value) || 0, min), max);
}

function formatNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "0";
}

function SettingsSlider({ label, value, min, max, step = 0.01, suffix = "", digits = 2, disabled = false, hideLabel = false, onChange }) {
  const numericValue = Number.isFinite(Number(value)) ? Number(value) : min;
  return (
    <FileSheetSliderField compact hideLabel={hideLabel}
      label={label}
      value={`${formatNumber(numericValue, digits)}${suffix}`}
      onValueCommit={(draft) => onChange(parseFileSheetNumberInput(draft, {
        fallback: numericValue,
        min,
        max
      }))}
      valueInputProps={{ disabled, ariaLabel: `${label} value` }}
    >
      <Slider
        value={[numericValue]}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onValueChange={(next) => onChange(clamp(next[0], min, max))}
        thumbProps={{ "aria-label": label }}
        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
      />
    </FileSheetSliderField>
  );
}

// Persistent model effects are separate from Display and its presets.
export function CrossSectionControls({ viewSettings, onViewSettingsPatch, bounds }) {
  const clip = normalizeStepClipSettings(normalizeViewSettings(viewSettings).clip);
  const axis = clip.axis;
  const { min, max } = clipAxisBounds(bounds, axis);
  const range = max - min;
  const neutral = clip.invert ? 0 : 1;
  const offset = clip.enabled ? clip.offset : neutral;
  const amount = (clip.invert ? offset : 1 - offset) * 100;
  const setClip = patch => onViewSettingsPatch({ clip: patch });
  const changeOffset = nextOffset => setClip({
    offsets: { [axis]: nextOffset }, enabled: Math.abs(nextOffset - neutral) > 1e-6
  });
  return <>
    <div className="flex items-center justify-between gap-1 px-2">
      <ToggleGroup type="single" value={axis} aria-label="Clip axis" className="rounded-sm bg-muted p-0.5"
        onValueChange={nextAxis => {
          if (!nextAxis) return;
          const nextOffset = clip.enabled ? clip.offsets[nextAxis] : neutral;
          setClip({ axis: nextAxis, offsets: { [nextAxis]: nextOffset }, enabled: Math.abs(nextOffset - neutral) > 1e-6 });
        }}>
        {AXES.map(value => <ToggleGroupItem key={value} value={value} aria-label={`Clip ${value.toUpperCase()} axis`}
          className="h-5 min-w-0 w-6 rounded-sm px-1 text-tiny data-[state=on]:bg-background data-[state=on]:shadow-xs">{value.toUpperCase()}</ToggleGroupItem>)}
      </ToggleGroup>
      <FileSheetCheckboxRow label="Flip" className="gap-1 px-0" checked={clip.invert}
        onCheckedChange={invert => setClip({ invert, ...(!clip.enabled ? { offsets: { x: invert ? 0 : 1, y: invert ? 0 : 1, z: invert ? 0 : 1 } } : {}) })} />
    </div>
    <div className="flex items-center gap-2 px-2 pb-1">
      <Slider thumbProps={{ "aria-label": "Clip amount" }} value={[amount]} min={0} max={100}
        step={0.1} disabled={!range}
        onValueChange={([value]) => changeOffset(clip.invert ? value / 100 : 1 - value / 100)}
        className={FILE_SHEET_PRECISION_SLIDER_CLASSES} />
      <FileSheetValueInput className="w-14 shrink-0" ariaLabel="Clip amount value"
        disabled={!range} value={`${formatNumber(amount, 1)}%`}
        onValueCommit={draft => {
          const value = parseFileSheetNumberInput(draft, { fallback: amount, min: 0, max: 100 });
          changeOffset(clip.invert ? value / 100 : 1 - value / 100);
        }} />
    </div>
  </>;
}

export function ExplodeControls({ viewSettings, onViewSettingsPatch, disabled = false, compact = false }) {
  const exploded = normalizeExplodedViewSettings(normalizeViewSettings(viewSettings).exploded);
  if (compact) return <div className="px-2 py-1"><Slider thumbProps={{ "aria-label": "Explode amount" }}
    value={[exploded.enabled ? exploded.amount * 100 : 0]} min={0} max={100} step={1} disabled={disabled}
    onValueChange={([amount]) => onViewSettingsPatch({ exploded: { amount: amount / 100, enabled: amount > 0 } })}
    className={FILE_SHEET_PRECISION_SLIDER_CLASSES} /></div>;
  return <SettingsSlider label="Explode" hideLabel value={exploded.enabled ? exploded.amount * 100 : 0} min={0} max={100} step={1} digits={0} suffix="%" disabled={disabled}
    onChange={amount => onViewSettingsPatch({ exploded: { amount: amount / 100, enabled: true } })} />;
}


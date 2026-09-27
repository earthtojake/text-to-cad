import { normalizeExplodedViewSettings } from "@hardcore/core/lib/displaySettings.js";
import { normalizeViewSettings } from "@hardcore/core/common/viewSettings.js";
import { clipAxisBounds, normalizeStepClipSettings } from "@hardcore/core/lib/viewer/clipPlane.js";
import { Slider } from "@hardcore/ui/primitives/slider";
import { FILE_SHEET_PRECISION_SLIDER_CLASSES, FileSheetSelectRow } from "../../../kit/inspector/FileSheet.js";

const AXES = Object.freeze(["x", "y", "z"]);

function formatNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "0";
}

// Persistent model effects are separate from Display and its presets. Clip and Explode are drawn
// alike: the amount in the panel's heading, one row for a body — Explode's a slider, Clip's the
// axis it cuts along and then its slider.
function clipState(viewSettings, bounds) {
  const clip = normalizeStepClipSettings(normalizeViewSettings(viewSettings).clip);
  const { min, max } = clipAxisBounds(bounds, clip.axis);
  const neutral = clip.invert ? 0 : 1;
  const offset = clip.enabled ? clip.offset : neutral;
  return { clip, neutral, range: max - min, amount: (clip.invert ? offset : 1 - offset) * 100 };
}

/** How far Clip cuts, for its panel's heading. */
export function clipSummary(viewSettings) {
  return `${formatNumber(clipState(viewSettings, null).amount, 0)}%`;
}

const AXIS_OPTIONS = Object.freeze(AXES.map(value => ({ value, label: value.toUpperCase() })));

/** Clip's axis, left of its slider: a compact X / Y / Z dropdown, the size of Pose's. */
function ClipAxisSelect({ viewSettings, onViewSettingsPatch }) {
  const { clip, neutral } = clipState(viewSettings, null);
  return <FileSheetSelectRow hideLabel className="w-auto shrink-0 px-0" triggerClassName="!h-6 w-auto gap-1 !px-1.5 text-tiny"
    value={clip.axis} ariaLabel="Clip axis" options={AXIS_OPTIONS}
    onValueChange={nextAxis => {
      if (!nextAxis || nextAxis === clip.axis) return;
      const nextOffset = clip.enabled ? clip.offsets[nextAxis] : neutral;
      onViewSettingsPatch({ clip: { axis: nextAxis, offsets: { [nextAxis]: nextOffset }, enabled: Math.abs(nextOffset - neutral) > 1e-6 } });
    }} />;
}

// The Clip panel's body: its axis, then one slider, which applies the cut as it leaves zero and
// removes it at zero.
export function CrossSectionControls({ viewSettings, onViewSettingsPatch, bounds }) {
  const { clip, neutral, range, amount } = clipState(viewSettings, bounds);
  const changeOffset = nextOffset => onViewSettingsPatch({ clip: {
    offsets: { [clip.axis]: nextOffset }, enabled: Math.abs(nextOffset - neutral) > 1e-6
  } });
  return <div className="flex min-w-0 items-center gap-2 px-2 py-1">
    <ClipAxisSelect viewSettings={viewSettings} onViewSettingsPatch={onViewSettingsPatch} />
    <Slider thumbProps={{ "aria-label": "Clip amount" }} value={[amount]} min={0} max={100}
      step={0.1} disabled={!range}
      onValueChange={([value]) => changeOffset(clip.invert ? value / 100 : 1 - value / 100)}
      className={FILE_SHEET_PRECISION_SLIDER_CLASSES} />
  </div>;
}

// The Explode panel: one slider, which applies the effect as it leaves zero and removes it at zero.
export function ExplodeControls({ viewSettings, onViewSettingsPatch }) {
  const exploded = normalizeExplodedViewSettings(normalizeViewSettings(viewSettings).exploded);
  return <div className="px-2 py-1"><Slider thumbProps={{ "aria-label": "Explode amount" }}
    value={[exploded.enabled ? exploded.amount * 100 : 0]} min={0} max={100} step={1}
    onValueChange={([amount]) => onViewSettingsPatch({ exploded: { amount: amount / 100, enabled: amount > 0 } })}
    className={FILE_SHEET_PRECISION_SLIDER_CLASSES} /></div>;
}


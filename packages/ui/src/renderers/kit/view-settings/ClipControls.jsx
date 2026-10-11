import { normalizeViewSettings } from "@text-to-cad/core/common/viewSettings.js";
import { clipAxisBounds, normalizeStepClipSettings } from "@text-to-cad/core/lib/viewer/clipPlane.js";
import { Slider } from "@text-to-cad/ui/primitives/slider";
import { FILE_SHEET_PRECISION_SLIDER_CLASSES, FileSheetSelectRow } from "../inspector/FileSheet.js";

// The Clip section's panel, for every view that offers it (`ViewFeatures.sections`): the amount in
// the panel's heading, one row for a body — the axis it cuts along and then its slider. The view
// settings own the effect; what a cut does to a scene is its renderer's.

const AXES = Object.freeze(["x", "y", "z"]);
const AXIS_OPTIONS = Object.freeze(AXES.map(value => ({ value, label: value.toUpperCase() })));

/** The settings that leave no cut: what a fresh panel starts at and what its X puts back. */
export const NEUTRAL_CLIP = Object.freeze({ enabled: false, axis: "x", offsets: Object.freeze({ x: 1, y: 1, z: 1 }), invert: false });

function clipState(viewSettings, bounds) {
  const clip = normalizeStepClipSettings(normalizeViewSettings(viewSettings).clip);
  const { min, max } = clipAxisBounds(bounds, clip.axis);
  const neutral = clip.invert ? 0 : 1;
  const offset = clip.enabled ? clip.offset : neutral;
  return { clip, neutral, range: max - min, amount: (clip.invert ? offset : 1 - offset) * 100 };
}

/** Whether the view cuts the model: Clip is on and away from its neutral end. */
export function clipApplied(viewSettings) {
  const { clip, neutral } = clipState(viewSettings, null);
  return clip.enabled && Math.abs(clip.offsets[clip.axis] - neutral) > 1e-6;
}

/** How far Clip cuts, for its panel's heading. */
export function clipSummary(viewSettings) {
  const amount = Number(clipState(viewSettings, null).amount);
  return `${Number.isFinite(amount) ? amount.toFixed(0) : "0"}%`;
}

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

/**
 * The Clip panel's body: its axis, then one slider, which applies the cut as it leaves zero and
 * removes it at zero. `bounds` is the box it cuts through (disabled while it has no extent).
 */
export function ClipControls({ viewSettings, onViewSettingsPatch, bounds }) {
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

/** Clip's strip icon: a cut sphere. */
export function ClipIcon(props) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M16 4.5a8.5 8.5 0 1 0 0 15" />
    <ellipse cx="16" cy="12" rx="3" ry="7.5" />
  </svg>;
}

import { normalizeExplodedViewSettings } from "@text-to-cad/core/lib/displaySettings.js";
import { normalizeViewSettings } from "@text-to-cad/core/common/viewSettings.js";
import { clipAmount, clipAtForAmount, clipAxisBounds, normalizeStepClipSettings } from "@text-to-cad/core/lib/viewer/clipPlane.js";
import { Slider } from "@text-to-cad/ui/primitives/slider";
import { FILE_SHEET_PRECISION_SLIDER_CLASSES, FileSheetSelectRow } from "../../../kit/inspector/FileSheet.js";

const AXES = Object.freeze(["x", "y", "z"]);

function formatNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "0";
}

// Persistent model effects are separate from Display and its presets. Clip and Explode are drawn
// alike: the amount in the panel's heading, one row for a body — Explode's a slider, Clip's the
// axis it cuts along and then its slider.
//
// Clip's view holds where its plane stands (`at`, millimetres); the panel shows the share of the
// model it cuts away, measured on `bounds` — the model at rest, the box the plane is placed in.
function clipState(viewSettings, bounds) {
  const clip = normalizeStepClipSettings(normalizeViewSettings(viewSettings).clip);
  const { min, max } = clipAxisBounds(bounds, clip.axis);
  return { clip, range: max - min, amount: clipAmount(clip, bounds) * 100 };
}

/** How far Clip cuts, for its panel's heading. */
export function clipSummary(viewSettings, bounds) {
  return `${formatNumber(clipState(viewSettings, bounds).amount, 0)}%`;
}

const AXIS_OPTIONS = Object.freeze(AXES.map(value => ({ value, label: value.toUpperCase() })));

/** Clip's axis, left of its slider: a compact X / Y / Z dropdown, the size of Pose's. */
function ClipAxisSelect({ viewSettings, onViewSettingsPatch, bounds }) {
  const { clip, amount } = clipState(viewSettings, bounds);
  return <FileSheetSelectRow hideLabel className="w-auto shrink-0 px-0" triggerClassName="!h-6 w-auto gap-1 !px-1.5 text-tiny"
    value={clip.axis} ariaLabel="Clip axis" options={AXIS_OPTIONS}
    onValueChange={nextAxis => {
      if (!nextAxis || nextAxis === clip.axis) return;
      // An axis alone is not an effect. A cut keeps its share on the new axis; with no box to
      // measure it on, it goes through the middle.
      const { min, max } = clipAxisBounds(bounds, nextAxis);
      const at = clip.enabled && max > min ? clipAtForAmount({ ...clip, axis: nextAxis }, bounds, amount / 100) : undefined;
      onViewSettingsPatch({ clip: { axis: nextAxis, ...(at !== undefined ? { at } : {}) } });
    }} />;
}

// The Clip panel's body: its axis, then one slider, which applies the cut as it leaves zero and
// removes it at zero.
export function CrossSectionControls({ viewSettings, onViewSettingsPatch, bounds }) {
  const { clip, range, amount } = clipState(viewSettings, bounds);
  return <div className="flex min-w-0 items-center gap-2 px-2 py-1">
    <ClipAxisSelect viewSettings={viewSettings} onViewSettingsPatch={onViewSettingsPatch} bounds={bounds} />
    <Slider thumbProps={{ "aria-label": "Clip amount" }} value={[amount]} min={0} max={100}
      step={0.1} disabled={!range}
      onValueChange={([value]) => onViewSettingsPatch({ clip: {
        enabled: value > 0, at: clipAtForAmount(clip, bounds, value / 100)
      } })}
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


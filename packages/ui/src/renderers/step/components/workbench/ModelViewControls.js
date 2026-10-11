import { normalizeExplodedViewSettings } from "@text-to-cad/core/lib/displaySettings.js";
import { normalizeViewSettings } from "@text-to-cad/core/common/viewSettings.js";
import { Slider } from "@text-to-cad/ui/primitives/slider";
import { FILE_SHEET_PRECISION_SLIDER_CLASSES } from "../../../kit/inspector/FileSheet.js";

// Persistent model effects are separate from Display and its presets. Clip and Explode are drawn
// alike: the amount in the panel's heading, one row for a body — Explode's a slider, Clip's the
// axis it cuts along and then its slider. Clip's panel is the kit's, shared with every view that
// offers the Clip section (`kit/view-settings/ClipControls.jsx`).
export { ClipControls as CrossSectionControls, clipSummary } from "../../../kit/view-settings/ClipControls.jsx";

// The Explode panel: one slider, which applies the effect as it leaves zero and removes it at zero.
export function ExplodeControls({ viewSettings, onViewSettingsPatch }) {
  const exploded = normalizeExplodedViewSettings(normalizeViewSettings(viewSettings).exploded);
  return <div className="px-2 py-1"><Slider thumbProps={{ "aria-label": "Explode amount" }}
    value={[exploded.enabled ? exploded.amount * 100 : 0]} min={0} max={100} step={1}
    onValueChange={([amount]) => onViewSettingsPatch({ exploded: { amount: amount / 100, enabled: amount > 0 } })}
    className={FILE_SHEET_PRECISION_SLIDER_CLASSES} /></div>;
}


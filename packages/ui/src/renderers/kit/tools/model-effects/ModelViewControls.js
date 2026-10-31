import { normalizeExplodedViewSettings } from "@text-to-cad/core/lib/displaySettings.js";
import { clipAmount, clipAtForAmount, clipAxisBounds, normalizeStepClipSettings } from "@text-to-cad/core/lib/viewer/clipPlane.js";
import { ChevronDown } from "lucide-react";
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuSeparator, DropdownMenuTrigger
} from "@text-to-cad/ui/primitives/dropdown-menu";
import { DropdownMenu as MenuPrimitive } from "radix-ui";
import { Slider } from "@text-to-cad/ui/primitives/slider";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../../lib/floatingSurface.js";
import { FILE_SHEET_PRECISION_SLIDER_CLASSES } from "../../inspector/FileSheet.js";
import { useControlUsage } from "../../../../usage/controls.js";
import { useI18n } from "@text-to-cad/ui/i18n";

const AXES = Object.freeze(["x", "y", "z"]);

function formatNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "0";
}

// These controls read the resolved scene's Clip and Explode groups. Public display
// validation belongs to the settings store; resolved scene groups are not a saved display.
// Persistent model effects are separate from Display and its presets. Clip and Explode are drawn
// alike: the amount in the panel's heading, one row for a body — Explode's a slider, Clip's the
// axis it cuts along (whose dropdown holds Clip's settings too) and then its slider.
//
// Clip's view holds where its plane stands (`at`, millimetres); the panel shows the share of the
// model it cuts away, measured on `bounds` — the model at rest, the box the plane is placed in.
function clipState(viewSettings, bounds) {
  const clip = normalizeStepClipSettings(viewSettings?.clip);
  const { min, max } = clipAxisBounds(bounds, clip.axis);
  return { clip, range: max - min, amount: clipAmount(clip, bounds) * 100 };
}

/** How far Clip cuts, for its panel's heading. */
export function clipSummary(viewSettings, bounds) {
  return `${formatNumber(clipState(viewSettings, bounds).amount, 0)}%`;
}

const AXIS_OPTIONS = Object.freeze(AXES.map(value => ({ value, label: value.toUpperCase() })));

// An axis's button: the app menu's Theme buttons (24px square, its radius, the menu's type), the axis in
// hand in the accent a highlighted item wears, the others in the item's own colour.
const AXIS_ITEM_CLASS = "grid size-6 cursor-default place-items-center rounded-sm text-tiny leading-4 text-foreground outline-none transition-colors focus:bg-accent focus:text-accent-foreground data-[state=checked]:bg-accent data-[state=checked]:text-accent-foreground";

// A press in this menu keeps it open: an axis as each setting does, so several change in one go.
const keepOpen = event => event.preventDefault();

/** Clip's axis and settings, left of its slider: a borderless button reading the axis in hand, as the
 *  row's other buttons are, whose dropdown holds all of Clip but the cut, as narrow as they are —
 *  first X, Y and Z, the Theme row's buttons (the axis in hand lit), a rule, then **Part colours** (each
 *  part's cap in its own colour; off, every cap one amber) and **Reverse** (which side of the plane
 *  is kept). None of them applies a cut; an axis or Reverse turns a cut keeping its share. They are
 *  settings, so Reset, which takes the cut away, leaves them be. */
function ClipAxisSelect({ viewSettings, onViewSettingsPatch, bounds }) {
  const { clip, amount } = clipState(viewSettings, bounds);
  const controls = useControlUsage();
  const { t } = useI18n();
  const choose = nextAxis => {
      if (!nextAxis || nextAxis === clip.axis) return;
      controls.used(`clip_axis_${nextAxis}`);
      // An axis alone is not an effect. A cut keeps its share on the new axis; with no box to
      // measure it on, it goes through the middle.
      const { min, max } = clipAxisBounds(bounds, nextAxis);
      const at = clip.enabled && max > min ? clipAtForAmount({ ...clip, axis: nextAxis }, bounds, amount / 100) : undefined;
      onViewSettingsPatch({ clip: { axis: nextAxis, ...(at !== undefined ? { at } : {}) } });
  };
  const reverse = invert => {
    controls.used("clip_reverse");
    // A cut turns round keeping its share; with no cut only the side changes (placing the plane would cut).
    const flipped = { ...clip, invert };
    onViewSettingsPatch({ clip: clip.enabled ? { invert, at: clipAtForAmount(flipped, bounds, amount / 100) } : { invert } });
  };
  return <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>
      <ToolbarButton tooltip={false} label={t("clip.axisCurrent", { axis: clip.axis.toUpperCase() })} data-clip-axis={clip.axis}
        className="w-auto shrink-0 gap-0.5 px-1 text-tiny aria-expanded:bg-sidebar-accent aria-expanded:text-sidebar-accent-foreground">
        {clip.axis.toUpperCase()}<ChevronDown className="size-2.5 opacity-60" aria-hidden="true" />
      </ToolbarButton>
    </DropdownMenuTrigger>
    {/* Closes with no exit animation, so a quick second press always reaches the button. */}
    <DropdownMenuContent align="start" sideOffset={4} collisionPadding={8}
      className={cn(FLOATING_SURFACE_CLASS, "w-max min-w-0 data-[state=closed]:animate-none!")}>
      {/* As narrow as its settings: first the axes, a compact group of the Theme row's buttons in a row
          as tall as an item; a rule; then the settings, Display's checkbox items, with no glyphs. */}
      <div className="flex min-h-7 items-center px-1 py-0.5" data-clip-axis-row="">
        <MenuPrimitive.RadioGroup value={clip.axis} onValueChange={choose} aria-label={t("clip.axis")} className="flex items-center gap-0.5">
          {AXIS_OPTIONS.map(option => <MenuPrimitive.RadioItem key={option.value} value={option.value} onSelect={keepOpen}
            className={AXIS_ITEM_CLASS} data-clip-axis-option={option.value}>{option.label}</MenuPrimitive.RadioItem>)}
        </MenuPrimitive.RadioGroup>
      </div>
      <DropdownMenuSeparator />
      <DropdownMenuCheckboxItem checked={clip.partColors} onSelect={keepOpen} data-clip-part-colors=""
        onCheckedChange={checked => { controls.used("clip_part_colors"); onViewSettingsPatch({ clip: { partColors: checked === true } }); }}>
        {t("clip.partColours")}
      </DropdownMenuCheckboxItem>
      <DropdownMenuCheckboxItem checked={clip.invert} onSelect={keepOpen} data-clip-reverse=""
        onCheckedChange={checked => reverse(checked === true)}>
        {t("clip.reverse")}
      </DropdownMenuCheckboxItem>
    </DropdownMenuContent>
  </DropdownMenu>;
}

// Clip's controls: its axis, then one slider, which applies the cut as it leaves zero and removes it
// at zero. `className` lays them out where they sit, and `sliderClassName` draws the slider.
export function CrossSectionControls({ viewSettings, onViewSettingsPatch, bounds, className = "flex min-w-0 items-center gap-2 px-2 py-1",
  sliderClassName = FILE_SHEET_PRECISION_SLIDER_CLASSES }) {
  const { clip, range, amount } = clipState(viewSettings, bounds);
  const controls = useControlUsage();
  const { t } = useI18n();
  return <div className={className}>
    <ClipAxisSelect viewSettings={viewSettings} onViewSettingsPatch={onViewSettingsPatch} bounds={bounds} />
    <Slider thumbProps={{ "aria-label": t("clip.amount") }} value={[amount]} min={0} max={100}
      step={0.1} disabled={!range}
      onValueChange={([value]) => { controls.changed("clip_amount"); onViewSettingsPatch({ clip: {
        enabled: value > 0, at: clipAtForAmount(clip, bounds, value / 100)
      } }); }}
      className={sliderClassName} />
  </div>;
}

// Explode's control: one slider, which applies the effect as it leaves zero and removes it at zero.
// `className` draws it where it sits (its sub-toolbar's slider).
export function ExplodeControls({ viewSettings, onViewSettingsPatch, className = FILE_SHEET_PRECISION_SLIDER_CLASSES }) {
  const exploded = normalizeExplodedViewSettings(viewSettings?.exploded);
  const controls = useControlUsage();
  const { t } = useI18n();
  return <Slider thumbProps={{ "aria-label": t("explode.amount") }}
    value={[exploded.enabled ? exploded.amount * 100 : 0]} min={0} max={100} step={1}
    onValueChange={([amount]) => { controls.changed("explode_amount"); onViewSettingsPatch({ exploded: { amount: amount / 100, enabled: amount > 0 } }); }}
    className={className} />;
}

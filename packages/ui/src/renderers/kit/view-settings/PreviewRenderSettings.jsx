import { Minus, Plus, RotateCcw } from "lucide-react";
import { previewSettingsChanged, resolvePreviewSettings } from "@text-to-cad/core/common/viewSettings.js";
import { Button } from "@text-to-cad/ui/primitives/button";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@text-to-cad/ui/primitives/select";
import { Slider } from "@text-to-cad/ui/primitives/slider";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { useI18n } from "@text-to-cad/ui/i18n";
import {
  FILE_SHEET_SELECT_TRIGGER_CLASSES, FileSheetColorPicker, FileSheetSettingRow,
  FileSheetSettingsSection, FileSheetValueInput
} from "../inspector/FileSheet.js";
import { SUB_TOOLBAR_SLIDER_CLASS } from "../tools/SubToolbar.jsx";

// Every control fills the row's control column at the row's 24px height.
const CONTROL_CLASS = "!h-6 w-full min-w-0";
// A dropdown or colour is as wide as its value, at the row's right end, where every control ends.
const CHOICE_WIDTH_CLASS = "ml-auto w-fit max-w-full";

// `label` is what the row shows, short under its section's heading ("Opacity" under Floor); `name`
// is the control's accessible name, whole ("Floor opacity").
function Choice({ label, name = label, value, options, onChange, disabled = false }) {
  return <FileSheetSettingRow label={label} disabled={disabled}>
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger aria-label={name} size="sm" className={cn(FILE_SHEET_SELECT_TRIGGER_CLASSES, CONTROL_CLASS, CHOICE_WIDTH_CLASS)}><SelectValue /></SelectTrigger>
      <SelectContent>{options.map(([id, title]) => <SelectItem key={id} value={id}>{title}</SelectItem>)}</SelectContent>
    </Select>
  </FileSheetSettingRow>;
}
function Range({ label, name = label, value, onChange, min = 0, max = 1, step = 0.01, disabled = false,
  scale = 100, format = v => `${Math.round(v * 100)}%` }) {
  const { t } = useI18n();
  const commit = draft => {
    // FileSheetValueInput also commits an untouched blur. Its formatted readout may be
    // rounded, so only a changed draft is an edit to Preview's sparse settings.
    if (draft === format(value)) return;
    const parsed = Number.parseFloat(draft) / scale;
    if (!Number.isFinite(parsed)) return;
    const clamped = Math.min(max, Math.max(min, parsed));
    const precision = String(step).split(".")[1]?.length || 0;
    const next = Number(clamped.toFixed(precision));
    if (next !== value) onChange(next);
  };
  return <FileSheetSettingRow label={label} disabled={disabled}>
    <Slider className={cn(SUB_TOOLBAR_SLIDER_CLASS, "px-1")} value={[value]} min={min} max={max} step={step} disabled={disabled}
      thumbProps={{ "aria-label": name }} onValueChange={([next]) => onChange(next)} />
    <FileSheetValueInput ariaLabel={t("render.valueOf", { name })} value={format(value)} onValueCommit={commit} disabled={disabled}
      className="h-6 w-13 px-1.5" />
  </FileSheetSettingRow>;
}
function Color({ label, name = label, value, onChange, disabled = false }) {
  return <FileSheetSettingRow label={label} disabled={disabled}>
    <FileSheetColorPicker aria-label={name} value={value} onChange={onChange} disabled={disabled} className={cn("!h-6 min-w-0", CHOICE_WIDTH_CLASS)} />
  </FileSheetSettingRow>;
}

/** By part's palette: a swatch per colour, then add and remove, wrapping in the control column. */
function Palette({ colors, onChange }) {
  const { t } = useI18n();
  const iconButton = (label, Icon, disabled, onClick) => <TooltipHint content={label}>
    <Button type="button" variant="ghost" size="icon-xs" aria-label={label} disabled={disabled} onClick={onClick}
      className="size-5 text-muted-foreground hover:text-foreground"><Icon className="size-3.5" aria-hidden="true" /></Button>
  </TooltipHint>;
  return <FileSheetSettingRow label={t("render.palette")} className="h-auto min-h-6 items-start [&>span]:pt-1">
    <div className="flex flex-wrap gap-1 py-0.5">
      {colors.map((value, index) => <FileSheetColorPicker key={index} aria-label={t("render.partColourN", { n: index + 1 })} value={value} showValue={false}
        className="!size-5 justify-center p-0" swatchClassName="size-3"
        onChange={color => onChange(colors.map((entry, i) => i === index ? color : entry))} />)}
      {iconButton(t("render.addColour"), Plus, colors.length >= 50, () => onChange([...colors, "#94a3b8"]))}
      {iconButton(t("render.removeLastColour"), Minus, colors.length <= 1, () => onChange(colors.slice(0, -1)))}
    </div>
  </FileSheetSettingRow>;
}

/**
 * Preview's own settings (Render's part colours, lighting, background and floor), every one visible
 * without opening sections. `settings` is Preview's sparse settings; `display` the file's, for the
 * appearance it pins.
 */
export function PreviewRenderSettings({ settings = {}, display = {}, appearance = "light", lightingQuality = "preview", onPatch, onReset }) {
  const { t } = useI18n();
  const options = { appearance: display?.appearance ?? (appearance === "dark" ? "dark" : "light"), lightingQuality };
  const look = resolvePreviewSettings(settings, options);
  const patch = (name, value) => onPatch({ [name]: value });
  const color = (name, title, disabled = false) => <Color label={t("render.colour")} name={title} value={look[name].color} disabled={disabled} onChange={color => patch(name, { color })} />;
  const opacity = (name, title) => <Range label={t("render.opacity")} name={title} value={look[name].opacity} onChange={opacity => patch(name, { opacity })} />;
  return <div className="flex min-h-0 flex-1 flex-col">
    <ScrollArea className="min-h-0 flex-1">
      <div className="p-1">
        <FileSheetSettingsSection title={t("render.partColours")}>
          <Choice label={t("render.source")} name={t("render.colourSource")} value={look.parts.colorMode} options={[["original", t("render.source.original")], ["single", t("render.source.single")], ["by-part", t("render.source.byPart")]]}
            onChange={colorMode => patch("parts", { colorMode })} />
          {look.parts.colorMode === "by-part"
            ? <Palette colors={look.parts.colors} onChange={colors => patch("parts", { colors })} />
            : color("parts", t("render.partColour"), look.parts.colorMode !== "single")}
        </FileSheetSettingsSection>
        <FileSheetSettingsSection title={t("render.lighting")}>
          <Choice label={t("render.quality")} value={look.lighting.quality} options={[["preview", t("render.quality.preview")], ["final", t("render.quality.final")]]} onChange={quality => patch("lighting", { quality })} />
          <Range label={t("render.exposure")} value={look.lighting.exposure} min={-5} max={5} step={0.1} scale={1} format={v => `${v.toFixed(1)} EV`} onChange={exposure => patch("lighting", { exposure })} />
          <Range label={t("render.rotation")} value={look.lighting.rotation} min={-180} max={180} step={1} scale={1} format={v => `${v}°`} onChange={rotation => patch("lighting", { rotation })} />
          <Range label={t("render.softbox")} name={t("render.softboxSize")} value={look.lighting.size} min={0.25} max={3} step={0.05} scale={1} format={v => `${v.toFixed(2)}×`} onChange={size => patch("lighting", { size })} />
          <Range label={t("render.fill")} value={look.lighting.fill} onChange={fill => patch("lighting", { fill })} />
        </FileSheetSettingsSection>
        <FileSheetSettingsSection title={t("render.background")}>
          {color("background", t("render.backgroundColour"))}{opacity("background", t("render.backgroundOpacity"))}
        </FileSheetSettingsSection>
        {/* The floor switches on and off: its section's heading checkbox; off, the section folds to it. */}
        <FileSheetSettingsSection title={t("render.floor")} enabled={look.floor.enabled} onEnabledChange={enabled => patch("floor", { enabled })}>
          {color("floor", t("render.floorColour"))}{opacity("floor", t("render.floorOpacity"))}
          <Choice label={t("render.placement")} value={look.floor.placement} options={[["lowest", t("render.placement.lowest")], ["origin", t("render.placement.origin")]]} onChange={placement => patch("floor", { placement })} />
          <Choice label={t("render.finish")} value={look.floor.finish} options={[["matte", t("render.finish.matte")], ["glossy", t("render.finish.glossy")]]} onChange={finish => patch("floor", { finish })} />
        </FileSheetSettingsSection>
      </div>
    </ScrollArea>
    <div className="shrink-0 border-t border-border p-1">
      <Button type="button" variant="ghost" size="xs" className="h-7 w-full justify-start gap-2 px-2 text-tiny font-normal text-muted-foreground hover:text-foreground"
        disabled={!previewSettingsChanged(settings, options)} onClick={onReset}>
        <RotateCcw className="size-3.5" aria-hidden="true" />{t("render.reset")}
      </Button>
    </div>
  </div>;
}

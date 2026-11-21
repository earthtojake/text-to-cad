import { Minus, Plus } from "lucide-react";
import { previewSettingsChanged, resolvePreviewSettings } from "@cad/core/common/viewSettings.js";
import { Button } from "@cad/ui/primitives/button";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { english } from "@cad/ui/i18n";
import { FileSheetColorPicker } from "../inspector/FileSheet.js";

/**
 * Preview's own settings (Render's part colours, lighting, background and floor) as the sections of its settings card
 * (`kit/shell/PreviewSettings.jsx`, `SettingsCard.jsx`'s rows), every one visible without opening anything: **Part
 * colours** (its Source, then its Colour or By part's palette), **Lighting** (Quality, Exposure, Rotation, Softbox,
 * Fill), **Background** (Colour, Opacity) and **Floor**, a switch heading its rows (Colour, Opacity, Placement, Finish)
 * while it is on.
 *
 * `render`: `{ settings, display, appearance, lightingQuality, partColours, onPatch, onReset }` — Preview's sparse
 * settings, the file's display (for the appearance it pins), the app's, and the writes. `partColours` false for a view
 * whose scene wears no surface look (its picture is its colours): Part colours, which would change nothing there, is
 * left out.
 */

/** `render`'s settings resolved, and whether Reset has anything to put back. */
export function previewRenderState({ settings = {}, display = {}, appearance = "light", lightingQuality = "preview" } = {}) {
  const options = { appearance: display?.appearance ?? (appearance === "dark" ? "dark" : "light"), lightingQuality };
  return { look: resolvePreviewSettings(settings, options), changed: previewSettingsChanged(settings, options) };
}

// A number's commit from its typed value: only a changed draft is an edit to Preview's sparse settings (the value also
// commits an untouched blur, and its readout may be rounded).
const commitOf = ({ value, onChange, min, max, step, scale, format }) => draft => {
  if (draft === format(value)) return;
  const parsed = Number.parseFloat(draft) / scale;
  if (!Number.isFinite(parsed)) return;
  const precision = String(step).split(".")[1]?.length || 0;
  const next = Number(Math.min(max, Math.max(min, parsed)).toFixed(precision));
  if (next !== value) onChange(next);
};

/** By part's palette: a swatch per colour, then add and remove, wrapping at the row's right. */
function Palette({ colors, onChange, t }) {
  const iconButton = (label, Icon, disabled, onClick) => <TooltipHint content={label}>
    <Button type="button" variant="ghost" size="icon-xs" aria-label={label} disabled={disabled} onClick={onClick}
      className="cad-hit size-5 text-muted-foreground hover:text-foreground"><Icon className="size-3.5" aria-hidden="true" /></Button>
  </TooltipHint>;
  return <div className="flex flex-wrap justify-end gap-1 py-0.5">
    {colors.map((value, index) => <FileSheetColorPicker key={index} aria-label={t("render.partColourN", { n: index + 1 })} value={value} showValue={false}
      className="!size-5 justify-center p-0" swatchClassName="size-3"
      onChange={color => onChange(colors.map((entry, i) => i === index ? color : entry))} />)}
    {iconButton(t("render.addColour"), Plus, colors.length >= 50, () => onChange([...colors, "#94a3b8"]))}
    {iconButton(t("render.removeLastColour"), Minus, colors.length <= 1, () => onChange(colors.slice(0, -1)))}
  </div>;
}

/** Preview's Render sections, after Orbit's (`PreviewSettings.jsx`). */
export function previewRenderSections(render, t = english) {
  const { partColours = true, onPatch } = render;
  const { look } = previewRenderState(render);
  const patch = (name, value) => onPatch({ [name]: value });
  const choice = (id, label, name, value, entries, onChange) => ({ kind: "select", id, label, name, value,
    options: entries.map(([entry, title]) => ({ value: entry, label: title })), onChange });
  const range = (id, label, name, value, onChange, { min = 0, max = 1, step = 0.01, scale = 100, format = v => `${Math.round(v * 100)}%` } = {}) => ({
    kind: "slider", id, label, name, value, min, max, step, scale, text: format(value), valueLabel: t("render.valueOf", { name }), onChange,
    onCommit: commitOf({ value, onChange, min, max, step, scale, format }) });
  const color = (id, name, group, disabled = false) => ({ kind: "color", id, label: t("render.colour"), name, value: look[group].color, disabled,
    onChange: value => patch(group, { color: value }) });
  const opacity = (id, name, group) => range(id, t("render.opacity"), name, look[group].opacity, value => patch(group, { opacity: value }));
  return [
    partColours ? [
      { kind: "heading", id: "parts", label: t("render.partColours") },
      choice("parts-source", t("render.source"), t("render.colourSource"), look.parts.colorMode,
        [["original", t("render.source.original")], ["single", t("render.source.single")], ["by-part", t("render.source.byPart")]], colorMode => patch("parts", { colorMode })),
      look.parts.colorMode === "by-part"
        ? { kind: "custom", id: "parts-palette", label: t("render.palette"), node: <Palette colors={look.parts.colors} onChange={colors => patch("parts", { colors })} t={t} /> }
        : color("parts-colour", t("render.partColour"), "parts", look.parts.colorMode !== "single")
    ] : [],
    [
      { kind: "heading", id: "lighting", label: t("render.lighting") },
      choice("lighting-quality", t("render.quality"), t("render.quality"), look.lighting.quality,
        [["preview", t("render.quality.preview")], ["final", t("render.quality.final")]], quality => patch("lighting", { quality })),
      range("lighting-exposure", t("render.exposure"), t("render.exposure"), look.lighting.exposure, exposure => patch("lighting", { exposure }),
        { min: -5, max: 5, step: 0.1, scale: 1, format: v => `${v.toFixed(1)} EV` }),
      range("lighting-rotation", t("render.rotation"), t("render.rotation"), look.lighting.rotation, rotation => patch("lighting", { rotation }),
        { min: -180, max: 180, step: 1, scale: 1, format: v => `${v}°` }),
      range("lighting-size", t("render.softbox"), t("render.softboxSize"), look.lighting.size, size => patch("lighting", { size }),
        { min: 0.25, max: 3, step: 0.05, scale: 1, format: v => `${v.toFixed(2)}×` }),
      range("lighting-fill", t("render.fill"), t("render.fill"), look.lighting.fill, fill => patch("lighting", { fill }))
    ],
    [
      { kind: "heading", id: "background", label: t("render.background") },
      color("background-colour", t("render.backgroundColour"), "background"),
      opacity("background-opacity", t("render.backgroundOpacity"), "background")
    ],
    [
      // The floor switches on and off: its section's heading's switch; off, the section folds to it.
      { kind: "switch", head: true, id: "floor", label: t("render.floor"), value: look.floor.enabled, onChange: enabled => patch("floor", { enabled }) },
      ...(look.floor.enabled ? [
        color("floor-colour", t("render.floorColour"), "floor"),
        opacity("floor-opacity", t("render.floorOpacity"), "floor"),
        choice("floor-placement", t("render.placement"), t("render.placement"), look.floor.placement,
          [["lowest", t("render.placement.lowest")], ["origin", t("render.placement.origin")]], placement => patch("floor", { placement })),
        choice("floor-finish", t("render.finish"), t("render.finish"), look.floor.finish,
          [["matte", t("render.finish.matte")], ["glossy", t("render.finish.glossy")]], finish => patch("floor", { finish }))
      ] : [])
    ]
  ];
}

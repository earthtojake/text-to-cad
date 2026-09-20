import { useMemo } from "react";
import { Blend, Expand, Plus, RotateCcw, RotateCw, Sun, SunDim, X } from "lucide-react";
import { normalizeExplodedViewSettings } from "@hardcore/core/lib/displaySettings.js";
import { EDGELESS_SURFACE_STYLE_VALUES, EDGELESS_VIEW_PRESET_VALUES, normalizeViewSettings, resolveViewSettings, viewSettingsAreCustom } from "@hardcore/core/common/viewSettings.js";
import { clipAxisBounds, clipAxisPosition, DEFAULT_STEP_CLIP_SETTINGS, normalizeStepClipSettings } from "@hardcore/core/lib/viewer/clipPlane.js";
import { MAX_THEME_FILL_COLORS } from "@hardcore/core/lib/themeSettings.js";
import { FILE_SHEET_SECTION_IDS } from "../../workbench/fileSheetSections.js";
import { Button } from "@hardcore/ui/primitives/button";
import { Slider } from "@hardcore/ui/primitives/slider";
import { DISPLAY_MODE_OPTIONS } from "../viewer/DisplayModeOptions.js";
import { OrthographicProjectionIcon, PerspectiveProjectionIcon } from "../viewer/ProjectionModeIcons.js";
import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES, FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetButtonRow, FileSheetColorPicker, FileSheetColorProperty, FileSheetCheckboxRow,
  FileSheetGatedSection, FileSheetControlRow, FileSheetSelectRow, FileSheetSliderField,
  FileSheetStaticSection, FileSheetFieldGrid, FileSheetNumberProperty, parseFileSheetNumberInput
} from "./FileSheet.js";

const PROJECTION_OPTIONS = [
  { value: "orthographic", label: "Orthographic", Icon: OrthographicProjectionIcon },
  { value: "perspective", label: "Perspective", Icon: PerspectiveProjectionIcon }
];
const PART_COLOR_OPTIONS = [
  { value: "original", label: "Original" }, { value: "single", label: "Single color" }, { value: "by-part", label: "Color by part" }
];
const SURFACE_STYLE_OPTIONS = [
  { value: "shaded", label: "Shaded" }, { value: "flat", label: "Flat" },
  { value: "hidden", label: "Hidden" }, { value: "off", label: "Off" }
];

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
        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
      />
    </FileSheetSliderField>
  );
}

function explodablePartCount(meshData) {
  const parts = Array.isArray(meshData?.parts) ? meshData.parts : [];
  return parts.filter((part) => part && (part.bounds || part.sourceBounds) &&
    String(part.id || part.occurrenceId || "").trim()).length;
}

function ColorPalette({ colors, onChange }) {
  const palette = Array.isArray(colors) && colors.length ? colors : ["#ffffff"];
  const commit = (next) => onChange(next.filter(Boolean).slice(0, MAX_THEME_FILL_COLORS));
  return (
    <FileSheetControlRow label="Colors" value={`${palette.length}/${MAX_THEME_FILL_COLORS}`}>
      <div className="flex flex-wrap gap-1.5">
        {palette.map((color, index) => (
          <div key={`${index}:${color}`} className="group relative">
            <FileSheetColorPicker
              value={color}
              swatchClassName="size-5"
              onChange={(nextColor) => commit(palette.map((entry, colorIndex) => (
                colorIndex === index ? nextColor : entry
              )))}
              aria-label={`Part color ${index + 1}`}
            />
            {palette.length > 1 ? (
              <Button
                type="button"
                variant="outline"
                size="icon-xs"
                className="absolute -right-1.5 -top-1.5 size-4 rounded-full bg-background p-0 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"
                onClick={() => commit(palette.filter((_, colorIndex) => colorIndex !== index))}
                aria-label={`Remove part color ${index + 1}`}
              >
                <X className="size-2.5" aria-hidden="true" />
              </Button>
            ) : null}
          </div>
        ))}
        {palette.length < MAX_THEME_FILL_COLORS ? (
          <Button
            type="button"
            variant="outline"
            size="icon-sm"
            className="size-7"
            onClick={() => commit([...palette, palette[palette.length - 1] || "#ffffff"])}
            aria-label="Add part color"
          >
            <Plus className="size-3.5" aria-hidden="true" />
          </Button>
        ) : null}
      </div>
    </FileSheetControlRow>
  );
}

function ClipSettings({ viewSettings, onViewSettingsPatch, onGroupEnabledChange, bounds }) {
  const clip = normalizeStepClipSettings(viewSettings.clip);
  const setClip = (patch) => onViewSettingsPatch({ clip: patch });
  return (
    <FileSheetGatedSection title="Clip" enabled={clip.enabled} onEnabledChange={(enabled) => onGroupEnabledChange("clip", enabled)}>
      {AXES.map((axis) => {
        const offset = clip.offsets?.[axis] ?? DEFAULT_STEP_CLIP_SETTINGS.offsets[axis];
        const axisBounds = clipAxisBounds(bounds, axis);
        const range = Math.max(axisBounds.max - axisBounds.min, 0);
        const position = clipAxisPosition(bounds, {
          ...clip,
          axis,
          offset,
          offsets: { ...clip.offsets, [axis]: offset }
        });
        const changeOffset = (nextOffset) => setClip({
          axis,
          offsets: { [axis]: nextOffset },
          enabled: true
        });
        return (
          <FileSheetSliderField compact
            key={axis}
            label={axis.toUpperCase()}
            value={`${formatNumber(position, Math.abs(position) >= 100 ? 0 : 2)} mm`}
            onValueCommit={(draft) => {
              const nextPosition = parseFileSheetNumberInput(draft, {
                fallback: position,
                min: axisBounds.min,
                max: axisBounds.max
              });
              changeOffset(range > 0 ? (nextPosition - axisBounds.min) / range : offset);
            }}
            valueInputProps={{ disabled: !range, ariaLabel: `Clip ${axis.toUpperCase()} position` }}
          >
            <Slider
              value={[offset]}
              min={0}
              max={1}
              step={0.001}
              disabled={!range}
              onValueChange={(next) => changeOffset(next[0])}
              className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
            />
          </FileSheetSliderField>
        );
      })}
      <FileSheetCheckboxRow label="Flip" checked={clip.invert} onCheckedChange={(invert) => setClip({ invert })} />
    </FileSheetGatedSection>
  );
}

function NumberProperty({ label, Icon, value, min, max, unit = "", digits = 2, onChange }) {
  return <FileSheetNumberProperty label={label} Icon={Icon} value={`${Number(value).toFixed(digits)}${unit}`}
    onValueCommit={draft => onChange(parseFileSheetNumberInput(draft, { fallback: value, min, max }))} />;
}

export function DisplaySettingsSection({
  viewSettings = {}, resolvedView, hostAppearance = "light", lightingQuality = "final", onViewSettingsPatch, onGroupEnabledChange, onModeChange, onViewReset,
  clipBounds = null, explodeMeshData = null, edgeStatus = "idle", edgeError = "", cadModel = true
}) {
  const settings = useMemo(() => normalizeViewSettings(viewSettings), [viewSettings]);
  const view = resolvedView || resolveViewSettings(settings, { appearance: hostAppearance, lightingQuality, cadModel });
  // A file that is not a CAD model has no Edges, Explode or Clip section and none of the presets made of edges.
  const modeOptions = cadModel ? DISPLAY_MODE_OPTIONS : DISPLAY_MODE_OPTIONS.filter(option => EDGELESS_VIEW_PRESET_VALUES.includes(option.value));
  const surfaceStyleOptions = cadModel ? SURFACE_STYLE_OPTIONS : SURFACE_STYLE_OPTIONS.filter(option => EDGELESS_SURFACE_STYLE_VALUES.includes(option.value));
  const setGroup = (group, patch) => onViewSettingsPatch({ [group]: {
    ...(group === "surfaces" ? { enabled: true } : {}), ...patch
  } });
  const custom = viewSettingsAreCustom(settings, { appearance: hostAppearance, lightingQuality, cadModel });
  const selectedMode = modeOptions.find(option => option.value === view.mode) || modeOptions[0];
  const ModeIcon = selectedMode.Icon;
  const presetLabel = selectedMode.label;
  const projection = view.camera.projection;
  const selectedProjection = PROJECTION_OPTIONS.find(option => option.value === projection) || PROJECTION_OPTIONS[0];
  const ProjectionIcon = selectedProjection.Icon;
  const exploded = normalizeExplodedViewSettings(settings.exploded);
  const explodedDisabled = Boolean(explodeMeshData) && explodablePartCount(explodeMeshData) <= 1;
  const section = (group, title, children) => (
    <FileSheetGatedSection title={title} enabled={view[group].enabled} onEnabledChange={enabled => onGroupEnabledChange(group, enabled)}>
      {children}
    </FileSheetGatedSection>
  );
  const color = (group, label, className) => <FileSheetColorProperty className={className} label={label} value={view[group].color}
    onChange={value => setGroup(group, { color: value })} opacity={view[group].opacity}
    onOpacityChange={opacity => setGroup(group, { opacity })} />;
  return (
    <div data-cad-display-settings-section="true">
      <FileSheetStaticSection title="Mode">
        <FileSheetFieldGrid>
          <FileSheetSelectRow hideLabel className="px-0" label="Mode" value={custom ? "" : selectedMode.value} placeholder="Custom" onValueChange={onModeChange}
            triggerContent={custom ? undefined : <span className="flex min-w-0 items-center gap-1"><ModeIcon className="size-3 shrink-0" aria-hidden="true" /><span className="truncate">{presetLabel}</span></span>}
            triggerClassName="gap-1 px-1.5 [&_svg]:size-3"
            options={modeOptions.map(({ Icon, ...option }) => ({ ...option, icon: <Icon className="size-3.5" aria-hidden="true" /> }))} />
          <FileSheetSelectRow hideLabel className="px-0" label="Projection" triggerClassName="gap-1 px-1.5 [&_svg]:size-3"
            value={projection} onValueChange={value => setGroup("camera", { enabled: true, projection: value })}
            triggerContent={<span className="flex min-w-0 items-center gap-1"><ProjectionIcon className="size-3 shrink-0" /><span className="truncate">{selectedProjection.label}</span></span>}
            options={PROJECTION_OPTIONS.map(({ Icon, ...option }) => ({ ...option, icon: <Icon className="size-3.5" aria-hidden="true" /> }))} />
        </FileSheetFieldGrid>
      </FileSheetStaticSection>
      <FileSheetStaticSection title="Surfaces">
        <FileSheetFieldGrid>
          <FileSheetSelectRow hideLabel className="px-0" label="Surface style" value={view.surfaces.style} onValueChange={style => setGroup("surfaces", { style })} options={surfaceStyleOptions} />
          <FileSheetSelectRow hideLabel className="px-0" label="Parts" value={view.surfaces.colorMode} onValueChange={colorMode => setGroup("surfaces", { colorMode })} options={PART_COLOR_OPTIONS} />
        </FileSheetFieldGrid>
        {view.surfaces.colorMode === "single" ? color("surfaces", "Part color") : null}
        {view.surfaces.colorMode === "by-part" ? <ColorPalette colors={view.surfaces.colors} onChange={colors => setGroup("surfaces", { colors })} /> : null}
        {view.surfaces.colorMode !== "single" ? <FileSheetFieldGrid columns={1}><NumberProperty label="Surface opacity" Icon={Blend} value={view.surfaces.opacity * 100} min={0} max={100} unit="%" digits={0} onChange={value => setGroup("surfaces", { opacity: value / 100 })} /></FileSheetFieldGrid> : null}
      </FileSheetStaticSection>
      {/* Explode separates a CAD model's parts and Clip sections its solids; a mesh, a robot
          or a drawing has neither, so it is offered neither. */}
      {cadModel && <>
        <FileSheetGatedSection title="Explode" enabled={exploded.enabled} onEnabledChange={enabled => onGroupEnabledChange("exploded", enabled)}>
          <SettingsSlider label="Explode" hideLabel value={exploded.enabled ? exploded.amount * 100 : 0} min={0} max={100} step={1} digits={0} suffix="%" disabled={explodedDisabled}
            onChange={amount => onViewSettingsPatch({ exploded: { amount: amount / 100, enabled: true } })} />
        </FileSheetGatedSection>
        <ClipSettings viewSettings={settings} onViewSettingsPatch={onViewSettingsPatch} onGroupEnabledChange={onGroupEnabledChange} bounds={clipBounds} />
      </>}
      {cadModel && section("edges", "Edges", <FileSheetFieldGrid>
        <FileSheetSelectRow hideLabel className="px-0" label="Edge visibility" value={view.edges.visibility} onValueChange={visibility => setGroup("edges", { visibility })}
          options={[{ value: "visible", label: "Visible" }, { value: "all", label: "All" }]} />
        <FileSheetColorProperty className="px-0" label="Edge color" value={view.edges.color} onChange={value => setGroup("edges", { color: value })} />
      </FileSheetFieldGrid>)}
      {section("grid", "Grid", color("grid", "Grid color"))}
      {section("axes", "Axes", color("axes", "Axis color"))}
      {section("lighting", "Lighting", <>
        <FileSheetSelectRow hideLabel label="Quality" value={view.lighting.quality} onValueChange={quality => setGroup("lighting", { quality })}
          options={[{ value: "preview", label: "Preview" }, { value: "final", label: "Final" }]} />
        <FileSheetFieldGrid className="gap-1">
          <NumberProperty label="Exposure" Icon={Sun} value={view.lighting.exposure} min={-5} max={5} unit=" EV" digits={1} onChange={exposure => setGroup("lighting", { exposure })} />
          <NumberProperty label="Rotation" Icon={RotateCw} value={view.lighting.rotation} min={-180} max={180} unit="°" digits={0} onChange={rotation => setGroup("lighting", { rotation })} />
          <NumberProperty label="Softbox size" Icon={Expand} value={view.lighting.size} min={0.25} max={3} unit="×" onChange={size => setGroup("lighting", { size })} />
          <NumberProperty label="Fill ratio" Icon={SunDim} value={view.lighting.fill * 100} min={0} max={100} unit="%" digits={0} onChange={value => setGroup("lighting", { fill: value / 100 })} />
        </FileSheetFieldGrid>
      </>)}
      {section("background", "Background", color("background", "Background color"))}
      {section("floor", "Floor", <FileSheetFieldGrid>
        <FileSheetSelectRow hideLabel className="px-0" label="Floor position" value={view.floor.placement} onValueChange={placement => setGroup("floor", { placement })}
          options={[{ value: "origin", label: "Model origin" }, { value: "lowest", label: "Lowest point" }]} />
        {color("floor", "Floor color", "px-0")}
      </FileSheetFieldGrid>)}
      {cadModel && edgeStatus === "loading" ? <p role="status" className="px-2 text-tiny text-muted-foreground">Preparing edges…</p> : null}
      {cadModel && edgeError ? <p role="alert" className="px-2 text-tiny text-destructive">Couldn’t load edges. {edgeError}</p> : null}
      <div className="py-2">
        <FileSheetButtonRow columns={1}>
          <Button type="button" variant="outline" size="sm" title={`Reset to ${presetLabel}`} className={FILE_SHEET_COMPACT_BUTTON_CLASSES} onClick={onViewReset}>
            <RotateCcw className="size-3.5" aria-hidden="true" />Reset
          </Button>
        </FileSheetButtonRow>
      </div>
    </div>
  );
}

export function buildDisplaySettingsTab(props) {
  return { id: FILE_SHEET_SECTION_IDS.VIEW, title: "View", content: <DisplaySettingsSection {...props} /> };
}

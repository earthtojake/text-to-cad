import { useMemo } from "react";
import { Plus, X } from "lucide-react";
import {
  CAD_DISPLAY_MODE,
  CAD_PART_COLOR_MODE,
  normalizeDisplaySettings,
  normalizeExplodedViewSettings
} from "@hardcore/core/lib/displaySettings.js";
import { CAMERA_PROJECTION } from "@hardcore/core/common/camera.js";
import {
  buildStepClipPatch,
  clipAxisBounds,
  clipAxisPosition,
  DEFAULT_STEP_CLIP_SETTINGS,
  normalizeStepClipSettings
} from "@hardcore/core/lib/viewer/clipPlane.js";
import { MAX_THEME_FILL_COLORS } from "@hardcore/core/lib/themeSettings.js";
import { FILE_SHEET_SECTION_IDS } from "../../workbench/fileSheetSections.js";
import { Button } from "@hardcore/ui/primitives/button";
import { Slider } from "@hardcore/ui/primitives/slider";
import { DISPLAY_MODE_OPTIONS } from "../viewer/DisplayModeOptions.js";
import {
  OrthographicProjectionIcon,
  PerspectiveProjectionIcon
} from "../viewer/ProjectionModeIcons.js";
import {
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetColorPicker,
  FileSheetColorRow,
  FileSheetControlRow,
  FileSheetSelectRow,
  FileSheetSliderField,
  FileSheetSubsection,
  FileSheetToggleRow,
  parseFileSheetNumberInput
} from "./FileSheet.js";
import { RenderSettingsPanel } from "./RenderSettingsTab.js";

const PROJECTION_OPTIONS = Object.freeze([
  {
    value: CAMERA_PROJECTION.ORTHOGRAPHIC,
    label: "Orthographic",
    title: "Parallel projection for CAD inspection",
    Icon: OrthographicProjectionIcon
  },
  {
    value: CAMERA_PROJECTION.PERSPECTIVE,
    label: "Perspective",
    title: "Depth projection with vanishing lines",
    Icon: PerspectiveProjectionIcon
  }
]);

const PART_COLOR_OPTIONS = Object.freeze([
  { value: CAD_PART_COLOR_MODE.ORIGINAL, label: "Original" },
  { value: CAD_PART_COLOR_MODE.SINGLE, label: "Single color" },
  { value: CAD_PART_COLOR_MODE.BY_PART, label: "Color by part" }
]);

const AXES = Object.freeze(["x", "y", "z"]);

function clamp(value, min, max) {
  return Math.min(Math.max(Number(value) || 0, min), max);
}

function formatNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "0";
}

function SettingsSlider({ label, value, min, max, step = 0.01, suffix = "", digits = 2, disabled = false, onChange }) {
  const numericValue = Number.isFinite(Number(value)) ? Number(value) : min;
  return (
    <FileSheetSliderField
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

function ClipSettings({ displaySettings, updateDisplaySettings, bounds }) {
  const clip = normalizeStepClipSettings(displaySettings.clip);
  const setClip = (patch) => updateDisplaySettings((current) => {
    const normalized = normalizeDisplaySettings(current);
    return { ...normalized, clip: buildStepClipPatch(normalized.clip, patch) };
  });
  return (
    <FileSheetSubsection title="Clip">
      <FileSheetToggleRow
        label="Flip"
        checked={clip.invert}
        onCheckedChange={(invert) => setClip({ invert })}
      />
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
          enabled: nextOffset > 0
        });
        return (
          <FileSheetSliderField
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
    </FileSheetSubsection>
  );
}

export function DisplaySettingsSection({
  observedFocalLength,
  displaySettings,
  updateDisplaySettings,
  projection = CAMERA_PROJECTION.ORTHOGRAPHIC,
  onProjectionChange,
  rendering = false,
  scene = null,
  onModeChange = null,
  onPayloadValueChange = null,
  onQualityChange = null,
  onRenderReset = null,
  clipBounds = null,
  explodeMeshData = null,
  edgeStatus = "idle",
  edgeError = ""
}) {
  const display = useMemo(() => normalizeDisplaySettings(displaySettings), [displaySettings]);
  const setDisplay = (patch) => updateDisplaySettings((current) => ({
    ...normalizeDisplaySettings(current),
    ...patch
  }));
  const setEdges = (patch) => setDisplay({ edges: { ...display.edges, ...patch } });
  const setPartColor = (patch) => setDisplay({ partColor: { ...display.partColor, ...patch } });
  const setGuide = (guide, patch) => setDisplay({
    guides: {
      ...display.guides,
      [guide]: { ...display.guides[guide], ...patch }
    }
  });
  const exploded = normalizeExplodedViewSettings(display.exploded);
  const explodedAmount = exploded.enabled ? exploded.amount : 0;
  const explodedDisabled = Boolean(explodeMeshData) && explodablePartCount(explodeMeshData) <= 1;
  const selectedMode = rendering ? CAD_DISPLAY_MODE.RENDER : display.mode;
  const changeMode = (mode) => {
    if (onModeChange) {
      onModeChange(mode);
      return;
    }
    if (mode !== CAD_DISPLAY_MODE.RENDER) {
      setDisplay({ mode });
    }
  };
  const setRenderValue = (path, value) => onPayloadValueChange?.(path, value);

  return (
    <div className="py-2" data-cad-display-settings-section="true">
      <FileSheetSubsection title="View">
        <FileSheetSelectRow stacked label="Mode" value={selectedMode} onValueChange={changeMode} options={DISPLAY_MODE_OPTIONS} />
        <FileSheetSelectRow
          label="Projection"
          value={projection}
          onValueChange={onProjectionChange}
          options={PROJECTION_OPTIONS.map(({ Icon, ...option }) => ({
            ...option,
            icon: <Icon className="size-3.5" aria-hidden="true" />
          }))}
        />
        {projection === CAMERA_PROJECTION.PERSPECTIVE ? (
          <SettingsSlider
            label="Lens"
            value={scene?.camera?.focalLength ?? observedFocalLength}
            min={20}
            max={200}
            step={1}
            suffix=" mm"
            digits={0}
            onChange={(value) => setRenderValue(["camera", "focalLength"], value)}
          />
        ) : null}
        <FileSheetSelectRow label="Parts" value={display.partColor.mode} onValueChange={(mode) => setPartColor({ mode })} options={PART_COLOR_OPTIONS} />
        {display.partColor.mode === CAD_PART_COLOR_MODE.SINGLE ? (
          <FileSheetColorRow label="Color" value={display.partColor.color} onChange={(color) => setPartColor({ color })} />
        ) : null}
        {display.partColor.mode === CAD_PART_COLOR_MODE.BY_PART ? (
          <ColorPalette colors={display.partColor.colors} onChange={(colors) => setPartColor({ colors })} />
        ) : null}
        <FileSheetToggleRow label="Grid" checked={display.guides.grid.enabled} onCheckedChange={(enabled) => setGuide("grid", { enabled })} />
        <FileSheetToggleRow label="Origin axes" checked={display.guides.axis.enabled} onCheckedChange={(enabled) => setGuide("axis", { enabled })} />
        {display.guides.axis.enabled ? (
          <>
            <FileSheetColorRow label="Axis color" value={display.guides.axis.color} onChange={(color) => setGuide("axis", { color })} />
            <SettingsSlider label="Axis opacity" value={display.guides.axis.opacity} min={0} max={1} onChange={(opacity) => setGuide("axis", { opacity })} />
          </>
        ) : null}
        {edgeStatus === "loading" ? <p role="status" className="px-3 py-1 text-xs text-muted-foreground">Preparing edges…</p> : null}
        {edgeError ? <p role="alert" className="px-3 py-1 text-xs text-destructive">Couldn’t load edges. {edgeError}</p> : null}
        <FileSheetToggleRow label="Silhouette" checked={display.edges.silhouette} onCheckedChange={(silhouette) => setEdges({ silhouette })} />
      </FileSheetSubsection>

      <ClipSettings displaySettings={display} updateDisplaySettings={updateDisplaySettings} bounds={clipBounds} />

      <FileSheetSubsection title="Explode">
        <SettingsSlider
          label="Amount"
          value={explodedAmount * 100}
          min={0}
          max={100}
          step={1}
          digits={0}
          suffix="%"
          disabled={explodedDisabled}
          onChange={(amount) => setDisplay({ exploded: { amount: amount / 100, enabled: amount > 0 } })}
        />
      </FileSheetSubsection>

      {rendering ? (
        <RenderSettingsPanel
          scene={scene}
          onQualityChange={onQualityChange}
          onPayloadValueChange={onPayloadValueChange}
          onReset={onRenderReset}
        />
      ) : null}
    </div>
  );
}

export function buildDisplaySettingsTab(props) {
  return {
    id: FILE_SHEET_SECTION_IDS.VIEW,
    title: "View",
    content: <DisplaySettingsSection {...props} />
  };
}

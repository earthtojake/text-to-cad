// The Studio editor's own chunk: lens, exposure, softbox, backdrop and ground.
// Reached only through Render mode, so RenderSettingsTab.js imports it lazily
// and an Inspect-only load never fetches it.
import { RotateCcw } from "lucide-react";
import { RENDER_QUALITY_PRESETS } from "@hardcore/core/common/sceneSettings.js";
import { Button } from "@hardcore/ui/primitives/button";
import { Slider } from "@hardcore/ui/primitives/slider";
import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetButtonRow,
  FileSheetColorRow,
  FileSheetSelectRow,
  FileSheetSliderField,
  FileSheetSubsection,
  FileSheetToggleRow,
  parseFileSheetNumberInput
} from "./FileSheet.js";

const QUALITY_OPTIONS = Object.freeze(RENDER_QUALITY_PRESETS.map((preset) => ({
  value: preset.id,
  label: preset.label
})));

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function formatNumber(value, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(digits) : "0";
}

function RenderSlider({ label, value, min, max, step = 0.01, unit = "", digits = 2, onChange }) {
  const numericValue = Number.isFinite(Number(value)) ? Number(value) : min;
  return (
    <FileSheetSliderField
      label={label}
      value={`${formatNumber(numericValue, digits)}${unit}`}
      onValueCommit={(draft) => onChange(parseFileSheetNumberInput(draft, {
        fallback: numericValue,
        min,
        max
      }))}
      valueInputProps={{ ariaLabel: `${label} value` }}
    >
      <Slider
        value={[numericValue]}
        min={min}
        max={max}
        step={step}
        onValueChange={(next) => onChange(clamp(Number(next[0]), min, max))}
        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
      />
    </FileSheetSliderField>
  );
}

export default function RenderSettingsContent({
  scene,
  onQualityChange,
  onPayloadValueChange,
  onReset
}) {
  const payload = scene.render.payload || {};
  const configuration = scene.render.configuration;
  const effectiveQualityLabel = QUALITY_OPTIONS.find(({ value }) => value === configuration.quality)?.label || "Final";
  const setValue = (path, value) => onPayloadValueChange?.(path, value);

  return (
    <div className="py-2" data-cad-render-settings-section="true">
      <FileSheetSubsection title="Setup">
        <FileSheetSelectRow
          label="Quality"
          value={payload.quality || ""}
          onValueChange={onQualityChange}
          options={QUALITY_OPTIONS}
          triggerContent={<span className="truncate">{effectiveQualityLabel}</span>}
        />
      </FileSheetSubsection>

      <FileSheetSubsection title="Camera">
        <RenderSlider label="Lens" value={scene.camera.focalLength} min={20} max={200} step={1} unit=" mm" digits={0} onChange={(value) => setValue(["camera", "focalLength"], value)} />
        <RenderSlider label="Exposure" value={configuration.exposure} min={-5} max={5} step={0.1} unit=" EV" digits={1} onChange={(value) => setValue(["exposure"], value)} />
      </FileSheetSubsection>

      <FileSheetSubsection title="Lighting">
        <RenderSlider label="Rotation" value={configuration.lighting.rotation} min={-180} max={180} step={1} unit="°" digits={0} onChange={(value) => setValue(["lighting", "rotation"], value)} />
        <RenderSlider label="Softbox size" value={configuration.lighting.size} min={0.25} max={3} step={0.05} digits={2} onChange={(value) => setValue(["lighting", "size"], value)} />
        <RenderSlider label="Fill ratio" value={configuration.lighting.fill} min={0} max={1} step={0.01} digits={2} onChange={(value) => setValue(["lighting", "fill"], value)} />
      </FileSheetSubsection>

      <FileSheetSubsection title="Backdrop">
        <FileSheetToggleRow label="Transparent" checked={configuration.backdrop.transparent} onCheckedChange={(value) => setValue(["backdrop", "transparent"], value)} />
        <FileSheetColorRow label="Color" value={configuration.backdrop.color} disabled={configuration.backdrop.transparent} onChange={(value) => setValue(["backdrop", "color"], value)} />
        <FileSheetToggleRow label="Ground" checked={configuration.backdrop.ground} onCheckedChange={(value) => setValue(["backdrop", "ground"], value)} />
        {configuration.backdrop.ground && (
          <FileSheetSelectRow
            label="Ground position"
            value={configuration.backdrop.groundPlacement}
            onValueChange={(value) => setValue(["backdrop", "groundPlacement"], value)}
            options={[
              { value: "lowest", label: "Lowest point" },
              { value: "origin", label: "Model origin" }
            ]}
          />
        )}
      </FileSheetSubsection>

      <FileSheetButtonRow columns={1}>
        <Button type="button" variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES} onClick={onReset}>
          <RotateCcw className="size-3.5" aria-hidden="true" />
          Reset
        </Button>
      </FileSheetButtonRow>
    </div>
  );
}

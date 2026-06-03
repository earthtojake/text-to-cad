import { RotateCcw } from "lucide-react";
import { cn } from "@/ui/utils";
import {
  DEFAULT_IMPLICIT_GRAPHICS_SETTINGS,
  IMPLICIT_GRAPHICS_LIMITS,
  implicitGraphicsSettingsEqual,
  normalizeImplicitGraphicsSettings
} from "@/workbench/implicitGraphicsSettings";
import { Button } from "../ui/button";
import { Slider } from "../ui/slider";
import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetControlRow,
  FileSheetSection,
  FileSheetSectionBody,
  FileSheetSliderField,
  FileSheetToggleRow,
  parseFileSheetNumberInput
} from "./FileSheet";

function formatScale(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return "1.00x";
  }
  return `${numericValue.toFixed(2)}x`;
}

function updateSetting(runtime, key, value) {
  runtime?.onSettingsChange?.((current) => ({
    ...normalizeImplicitGraphicsSettings(current),
    [key]: value
  }));
}

function renderScaleSlider({ label, settingKey, settings, runtime }) {
  const limits = IMPLICIT_GRAPHICS_LIMITS[settingKey];
  const value = settings[settingKey];
  return (
    <FileSheetSliderField
      label={label}
      value={formatScale(value)}
      onValueCommit={(nextValue) => {
        updateSetting(runtime, settingKey, parseFileSheetNumberInput(nextValue, {
          fallback: value,
          min: limits.min,
          max: limits.max
        }));
      }}
      valueInputProps={{
        ariaLabel: `${label} value`
      }}
    >
      <Slider
        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
        value={[value]}
        min={limits.min}
        max={limits.max}
        step={limits.step}
        onValueChange={(nextValue) => updateSetting(runtime, settingKey, nextValue?.[0] ?? value)}
        aria-label={label}
      />
    </FileSheetSliderField>
  );
}

export default function ImplicitGraphicsSection({
  runtime = null,
  value = "graphics",
  title = "Graphics"
}) {
  const settings = normalizeImplicitGraphicsSettings(runtime?.settings);
  const hasModelColors = Boolean(runtime?.model?.colorSource);
  const hasDefaultSettings = implicitGraphicsSettingsEqual(settings, DEFAULT_IMPLICIT_GRAPHICS_SETTINGS);

  return (
    <FileSheetSection value={value} title={title}>
      <FileSheetSectionBody>
        {renderScaleSlider({
          label: "Resolution",
          settingKey: "resolutionScale",
          settings,
          runtime
        })}
        {renderScaleSlider({
          label: "Motion resolution",
          settingKey: "interactionResolutionScale",
          settings,
          runtime
        })}
        {renderScaleSlider({
          label: "Ray detail",
          settingKey: "detail",
          settings,
          runtime
        })}
        {renderScaleSlider({
          label: "Normal smoothing",
          settingKey: "normalSmoothing",
          settings,
          runtime
        })}
        <FileSheetToggleRow
          label="Model colors"
          checked={settings.modelColors && hasModelColors}
          disabled={!hasModelColors}
          onCheckedChange={(checked) => updateSetting(runtime, "modelColors", checked)}
          ariaLabel="Model colors"
        />
        <FileSheetToggleRow
          label="Soft shadows"
          checked={settings.shadows}
          onCheckedChange={(checked) => updateSetting(runtime, "shadows", checked)}
          ariaLabel="Soft shadows"
        />
        <FileSheetToggleRow
          label="Ambient occlusion"
          checked={settings.ambientOcclusion}
          onCheckedChange={(checked) => updateSetting(runtime, "ambientOcclusion", checked)}
          ariaLabel="Ambient occlusion"
        />
        <FileSheetToggleRow
          label="Rim light"
          checked={settings.rimLight}
          onCheckedChange={(checked) => updateSetting(runtime, "rimLight", checked)}
          ariaLabel="Rim light"
        />
        <FileSheetControlRow className="pt-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className={cn(FILE_SHEET_COMPACT_BUTTON_CLASSES, "w-full justify-center")}
            disabled={hasDefaultSettings}
            onClick={() => runtime?.onSettingsChange?.(DEFAULT_IMPLICIT_GRAPHICS_SETTINGS)}
            title="Reset graphics"
          >
            <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
            <span>Reset graphics</span>
          </Button>
        </FileSheetControlRow>
      </FileSheetSectionBody>
    </FileSheetSection>
  );
}

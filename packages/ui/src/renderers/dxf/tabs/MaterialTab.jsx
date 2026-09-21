import { Slider } from "@hardcore/ui/primitives/slider";
import {
  FILE_SHEET_PRECISION_SLIDER_CLASSES, FileSheetCascadeSelectRow, FileSheetSectionBody,
  FileSheetSelectRow, FileSheetSliderField, FileSheetSubsection
} from "../../kit/inspector/FileSheet.js";
import {
  DXF_MATERIAL_PRESETS, DXF_THICKNESS_MAX_MM, DXF_UNIT_OPTIONS, dxfDisplayLength, dxfFormatLength,
  dxfMaterialPreset, dxfParseLengthToMm, dxfUnitOption, normalizeDxfMaterial, normalizeDxfThicknessMm,
  normalizeDxfUnits
} from "../dxfSettings.js";
import { DxfResetRow } from "./DxfResetRow.jsx";

/** The stock this sheet is cut from: what it is measured in, what it is made of, how thick. */
export function MaterialTab({ settings }) {
  const { state } = settings;
  const unit = dxfUnitOption(state.units);
  const thickness = normalizeDxfThicknessMm(state.thicknessMm);
  const preset = dxfMaterialPreset(state.material);
  return (
    <FileSheetSectionBody>
      <FileSheetSubsection>
        {/* Units first: it reframes every dimensional row below it. */}
        <FileSheetSelectRow
          label="Units"
          value={normalizeDxfUnits(state.units)}
          onValueChange={next => settings.setUnits(next)}
          options={DXF_UNIT_OPTIONS.map(({ value, label }) => ({ value, label }))}
        />
        <FileSheetCascadeSelectRow
          label="Material"
          value={preset.value}
          onValueChange={next => settings.setMaterial(normalizeDxfMaterial(next, preset.value))}
          options={DXF_MATERIAL_PRESETS.map(({ value, label, group }) => ({ value, label, group }))}
        />
        <FileSheetSliderField
          label="Thickness"
          value={dxfFormatLength(thickness, unit)}
          onValueCommit={next => settings.setThickness(dxfParseLengthToMm(next, unit, thickness))}
          valueInputProps={{ ariaLabel: "Thickness value", min: 0, max: dxfDisplayLength(DXF_THICKNESS_MAX_MM, unit) }}
        >
          <Slider
            aria-label="Thickness"
            className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
            value={[dxfDisplayLength(thickness, unit)]}
            min={0}
            max={dxfDisplayLength(DXF_THICKNESS_MAX_MM, unit)}
            step={unit.sliderStep}
            onValueChange={([next]) => settings.setThickness(next * unit.mmPerUnit)}
          />
        </FileSheetSliderField>
      </FileSheetSubsection>

      <DxfResetRow label="Reset material settings" onReset={settings.resetMaterial} />
    </FileSheetSectionBody>
  );
}

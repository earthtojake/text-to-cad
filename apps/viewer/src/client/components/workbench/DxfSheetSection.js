import { RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";

import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FileSheetControlRow,
  FileSheetFieldGrid,
  FileSheetInlineControlRow,
  FileSheetSectionBody,
  FileSheetSegmentedControl,
  FileSheetStatusText,
  FileSheetSubsection,
  FileSheetToggleRow,
  FileSheetValueField
} from "./FileSheet";
import { FILE_SHEET_SECTION_IDS } from "@/workbench/fileSheetSections";

/**
 * The Sheet tab of a dimensioned DRAWING (a document with a frame, views and
 * dimensions), in place of the flat-pattern Material tab: a sheet has no stock
 * thickness or material to fold, it has paper, a scale, a projection and line
 * work to show or hide.
 *
 * Everything here is render-time. The facts are read from the drawing itself
 * (title block and frame); the line weight re-renders the sheet through the
 * server's SVG route; the line-work switches are the same layer visibility the
 * Layers tab drives, named for what the layers MEAN on a drawing.
 */

export const DXF_LINE_WEIGHT_OPTIONS = Object.freeze([
  { value: "fine", label: "Fine", scale: 0.6 },
  { value: "normal", label: "Normal", scale: 1 },
  { value: "bold", label: "Bold", scale: 1.6 }
]);
export const DXF_DEFAULT_LINE_WEIGHT = "normal";

export function normalizeDxfLineWeight(value, fallback = DXF_DEFAULT_LINE_WEIGHT) {
  const text = String(value || "").trim().toLowerCase();
  return DXF_LINE_WEIGHT_OPTIONS.some((option) => option.value === text) ? text : fallback;
}

export function dxfLineWeightScale(value) {
  return DXF_LINE_WEIGHT_OPTIONS.find((option) => option.value === normalizeDxfLineWeight(value))?.scale ?? 1;
}

/** How the dimensions READ: the file's own numbers, or restated in a unit; how many
 *  places; and how large the text and arrows are. The server re-renders each DIMENSION
 *  from its measured value, so nothing here changes what the drawing measures. */
export const DXF_DIMENSION_UNIT_OPTIONS = Object.freeze([
  { value: "drawn", label: "As drawn" },
  { value: "mm", label: "mm" },
  { value: "in", label: "in" }
]);
export const DXF_DIMENSION_DECIMAL_OPTIONS = Object.freeze([
  { value: "drawn", label: "Auto" },
  { value: "0", label: "0" },
  { value: "1", label: "0.0" },
  { value: "2", label: "0.00" },
  { value: "3", label: "0.000" }
]);
export const DXF_DIMENSION_TEXT_OPTIONS = Object.freeze([
  { value: "small", label: "Small", scale: 0.7 },
  { value: "normal", label: "Normal", scale: 1 },
  { value: "large", label: "Large", scale: 1.4 }
]);
export const DXF_DEFAULT_DIMENSION_DISPLAY = Object.freeze({ units: "drawn", decimals: "drawn", text: "normal" });

export function normalizeDxfDimensionDisplay(value) {
  const pick = (options, candidate, fallback) => {
    const text = String(candidate ?? "").trim().toLowerCase();
    return options.some((option) => option.value === text) ? text : fallback;
  };
  return {
    units: pick(DXF_DIMENSION_UNIT_OPTIONS, value?.units, DXF_DEFAULT_DIMENSION_DISPLAY.units),
    decimals: pick(DXF_DIMENSION_DECIMAL_OPTIONS, value?.decimals, DXF_DEFAULT_DIMENSION_DISPLAY.decimals),
    text: pick(DXF_DIMENSION_TEXT_OPTIONS, value?.text, DXF_DEFAULT_DIMENSION_DISPLAY.text)
  };
}

/** The /__cad/drawing query parameters a dimension display asks for; none at the default. */
export function dxfDimensionDisplayParams(value) {
  const display = normalizeDxfDimensionDisplay(value);
  const params = {};
  if (display.units !== "drawn") params.dunits = display.units;
  if (display.decimals !== "drawn") params.ddec = display.decimals;
  const scale = DXF_DIMENSION_TEXT_OPTIONS.find((option) => option.value === display.text)?.scale ?? 1;
  if (scale !== 1) params.dtext = String(scale);
  return params;
}

/** Drawing layers with a standing meaning, in the order a draughtsman would list them. */
export const DXF_DRAWING_LINE_WORK = Object.freeze([
  { layer: "HIDDEN", label: "Hidden lines" },
  { layer: "CENTER", label: "Centre lines" },
  { layer: "DIM", label: "Dimensions" },
  { layer: "NOTES", label: "Notes" },
  { layer: "TITLE", label: "Title block" }
]);

function titleCase(value) {
  return String(value || "").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function DxfSheetSettings({
  facts = null,
  lineWeight = DXF_DEFAULT_LINE_WEIGHT,
  onLineWeightChange,
  dimensionDisplay = DXF_DEFAULT_DIMENSION_DISPLAY,
  onDimensionDisplayChange,
  dimensionCount = 0,
  layers = [],
  hiddenLayers = [],
  onLayerVisibilityChange,
  onReset
}) {
  const layerNames = new Set(layers.map((layer) => String(layer?.name || "").toUpperCase()));
  const hidden = new Set(Array.isArray(hiddenLayers) ? hiddenLayers : []);
  const lineWork = DXF_DRAWING_LINE_WORK.filter((entry) => layerNames.has(entry.layer));
  const dimensions = normalizeDxfDimensionDisplay(dimensionDisplay);
  const setDimension = (key, next) => onDimensionDisplayChange?.(normalizeDxfDimensionDisplay({ ...dimensions, [key]: next }));
  const fields = [
    ["Paper", facts?.paper],
    ["Scale", facts?.scale],
    ["Units", facts?.units ? facts.units.toUpperCase() : ""],
    ["Projection", facts?.projection ? titleCase(facts.projection) : ""],
    ["Revision", facts?.revision],
    ["Sheet", facts?.sheet]
  ].filter(([, value]) => Boolean(value));

  return (
    <FileSheetSectionBody>
      <FileSheetSubsection title={facts?.title || "Sheet"}>
        {facts?.partNumber ? (
          <FileSheetStatusText>{facts.partNumber}</FileSheetStatusText>
        ) : null}
        {fields.length ? (
          <FileSheetFieldGrid columns={2}>
            {fields.map(([label, value]) => (
              <FileSheetValueField key={label} label={label} value={value} />
            ))}
          </FileSheetFieldGrid>
        ) : (
          <FileSheetStatusText>No title block in this drawing.</FileSheetStatusText>
        )}
      </FileSheetSubsection>

      {dimensionCount > 0 ? (
        <FileSheetSubsection title={`Dimensions · ${dimensionCount}`}>
          <FileSheetInlineControlRow label="Units">
            <FileSheetSegmentedControl
              ariaLabel="Dimension units"
              value={dimensions.units}
              onChange={(next) => setDimension("units", next)}
              options={DXF_DIMENSION_UNIT_OPTIONS.map(({ value, label }) => ({ value, label }))}
              fit
            />
          </FileSheetInlineControlRow>
          <FileSheetControlRow label="Precision">
            <FileSheetSegmentedControl
              ariaLabel="Dimension precision"
              value={dimensions.decimals}
              onChange={(next) => setDimension("decimals", next)}
              options={DXF_DIMENSION_DECIMAL_OPTIONS.map(({ value, label }) => ({ value, label }))}
            />
          </FileSheetControlRow>
          <FileSheetInlineControlRow label="Text size">
            <FileSheetSegmentedControl
              ariaLabel="Dimension text size"
              value={dimensions.text}
              onChange={(next) => setDimension("text", next)}
              options={DXF_DIMENSION_TEXT_OPTIONS.map(({ value, label }) => ({ value, label }))}
              fit
            />
          </FileSheetInlineControlRow>
        </FileSheetSubsection>
      ) : null}

      <FileSheetSubsection title="Display">
        <FileSheetInlineControlRow label="Line weight">
          <FileSheetSegmentedControl
            ariaLabel="Line weight"
            value={normalizeDxfLineWeight(lineWeight)}
            onChange={(next) => onLineWeightChange?.(normalizeDxfLineWeight(next, lineWeight))}
            options={DXF_LINE_WEIGHT_OPTIONS.map(({ value, label }) => ({ value, label }))}
            fit
          />
        </FileSheetInlineControlRow>
        {lineWork.map((entry) => (
          <FileSheetToggleRow
            key={entry.layer}
            label={entry.label}
            checked={!hidden.has(entry.layer)}
            onCheckedChange={(visible) => onLayerVisibilityChange?.(entry.layer, visible)}
          />
        ))}
      </FileSheetSubsection>

      {onReset ? (
        <FileSheetControlRow label={null}>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className={`${FILE_SHEET_COMPACT_BUTTON_CLASSES} w-full justify-center`}
            onClick={() => onReset()}
            aria-label="Reset sheet display"
            title="Reset"
          >
            <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
            <span>Reset</span>
          </Button>
        </FileSheetControlRow>
      ) : null}
    </FileSheetSectionBody>
  );
}

export function buildDxfSheetTab(props) {
  return {
    id: FILE_SHEET_SECTION_IDS.DXF_SHEET,
    title: "Sheet",
    content: <DxfSheetSettings {...props} />
  };
}

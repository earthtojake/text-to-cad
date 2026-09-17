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
  layers = [],
  hiddenLayers = [],
  onLayerVisibilityChange,
  onReset
}) {
  const layerNames = new Set(layers.map((layer) => String(layer?.name || "").toUpperCase()));
  const hidden = new Set(Array.isArray(hiddenLayers) ? hiddenLayers : []);
  const lineWork = DXF_DRAWING_LINE_WORK.filter((entry) => layerNames.has(entry.layer));
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

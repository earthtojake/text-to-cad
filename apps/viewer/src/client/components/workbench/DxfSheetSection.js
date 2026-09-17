import { Move, Plus, RotateCcw, Send, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/ui/utils";

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
  FileSheetValueField,
  FILE_SHEET_COMPACT_INPUT_CLASSES
} from "./FileSheet";
import { drawingEditSnippet } from "@/workbench/drawingEdits";
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
  onReset,
  // Editing (a cadgen sheet with tagged views): the views to move, the dimensions
  // to select and tolerance, the staged edits, and the tool in hand.
  views = [],
  sheetDimensions = [],
  edits = [],
  editTool = "",
  onEditToolChange,
  pickedPointCount = 0,
  selectedDimension = "",
  onSelectDimension,
  onAddTolerance,
  onDiscardEdit,
  onDiscardEdits,
  onSendEdits,
  sendLabel = "Send to drawing"
}) {
  const [toleranceDraft, setToleranceDraft] = useState("");
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

      {views.length ? (
        <FileSheetSubsection title={`Views · ${views.length}`}>
          <div className="space-y-px px-1">
            {views.map((view) => (
              <div key={view.name} className="flex min-w-0 items-center gap-2 rounded-md px-1 py-1 text-[11px]">
                <span className="min-w-0 flex-1 truncate font-medium uppercase text-sidebar-foreground">{view.name}</span>
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  {view.at ? `at ${Math.round(view.at[0])}, ${Math.round(view.at[1])}` : `${Math.round(view.maxX - view.minX)} × ${Math.round(view.maxY - view.minY)}`}
                </span>
              </div>
            ))}
          </div>
          <FileSheetControlRow label={null}>
            <Button
              type="button"
              variant={editTool === "move" ? "secondary" : "outline"}
              size="sm"
              className={`${FILE_SHEET_COMPACT_BUTTON_CLASSES} w-full justify-center`}
              aria-pressed={editTool === "move"}
              aria-label="Move views"
              onClick={() => onEditToolChange?.(editTool === "move" ? "" : "move")}
            >
              <Move className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
              <span>{editTool === "move" ? "Drag a view on the sheet, then click again to stop" : "Move views"}</span>
            </Button>
          </FileSheetControlRow>
        </FileSheetSubsection>
      ) : null}

      {dimensionCount > 0 ? (
        <FileSheetSubsection title={`Dimensions · ${dimensionCount}`}>
          {sheetDimensions.length ? (
            <div className="max-h-48 space-y-px overflow-y-auto px-1">
              {sheetDimensions.map((dimension) => {
                const key = `${dimension.view}:${dimension.index}`;
                const selected = selectedDimension === key;
                return (
                  <button
                    key={key}
                    type="button"
                    className={cn(
                      "flex w-full min-w-0 items-center gap-2 rounded-md px-1 py-1 text-left text-[11px] hover:bg-sidebar-accent/60",
                      selected && "bg-sidebar-accent text-sidebar-accent-foreground"
                    )}
                    aria-pressed={selected}
                    onClick={() => { onSelectDimension?.(selected ? "" : key); setToleranceDraft(""); }}
                  >
                    <span className="shrink-0 uppercase text-muted-foreground">{dimension.view}</span>
                    <span className="min-w-0 flex-1 truncate font-medium tabular-nums text-sidebar-foreground">{dimension.value || "—"}</span>
                    <span className="shrink-0 text-muted-foreground">{dimension.kind === "callout" ? "callout" : `#${Number(dimension.index) + 1 || dimension.index}`}</span>
                  </button>
                );
              })}
            </div>
          ) : null}
          {selectedDimension && onAddTolerance ? (
            <FileSheetControlRow label="Tolerance">
              <div className="flex items-center gap-2">
                <Input
                  className={`${FILE_SHEET_COMPACT_INPUT_CLASSES} flex-1`}
                  placeholder="±0.1, 0.05/0.02 or H7"
                  aria-label="Tolerance or fit for the selected dimension"
                  value={toleranceDraft}
                  onChange={(event) => setToleranceDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && toleranceDraft.trim()) {
                      onAddTolerance(selectedDimension, toleranceDraft.trim());
                      setToleranceDraft("");
                    }
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
                  disabled={!toleranceDraft.trim()}
                  onClick={() => { onAddTolerance(selectedDimension, toleranceDraft.trim()); setToleranceDraft(""); }}
                >
                  Apply
                </Button>
              </div>
            </FileSheetControlRow>
          ) : null}
          {onEditToolChange && views.length ? (
            <FileSheetControlRow label={null}>
              <Button
                type="button"
                variant={editTool === "pick" ? "secondary" : "outline"}
                size="sm"
                className={`${FILE_SHEET_COMPACT_BUTTON_CLASSES} w-full justify-center`}
                aria-pressed={editTool === "pick"}
                aria-label="Add dimension"
                onClick={() => onEditToolChange(editTool === "pick" ? "" : "pick")}
              >
                <Plus className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                <span>{editTool === "pick" ? (pickedPointCount ? "Click the second point" : "Click the first point on the sheet") : "Add dimension"}</span>
              </Button>
            </FileSheetControlRow>
          ) : null}
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

      {edits.length ? (
        <FileSheetSubsection title={`Staged edits · ${edits.length}`}>
          <div className="space-y-px px-1">
            {edits.map((edit) => (
              <div key={edit.id} className="flex min-w-0 items-start gap-1 rounded-md px-1 py-1 text-[11px]">
                <span className="min-w-0 flex-1 break-words text-sidebar-foreground" title={drawingEditSnippet(edit, { views, dimensions: sheetDimensions })}>
                  {edit.kind === "move" ? `Move ${edit.view} by ${edit.dx}, ${edit.dy}`
                    : edit.kind === "dim" ? `New dimension in ${edit.view}`
                      : `${edit.view} #${Number(edit.index) + 1 || edit.index}: ${edit.spec}`}
                </span>
                <Button type="button" variant="ghost" size="icon-sm" className="size-5 shrink-0 text-muted-foreground hover:text-foreground"
                  aria-label="Discard this edit" onClick={() => onDiscardEdit?.(edit.id)}>
                  <X className="size-3" strokeWidth={1.8} aria-hidden="true" />
                </Button>
              </div>
            ))}
          </div>
          <FileSheetStatusText>Previewed in red on the sheet. Nothing is saved until the script changes.</FileSheetStatusText>
          <FileSheetControlRow label={null}>
            <div className="flex items-center gap-2">
              <Button type="button" variant="default" size="sm" className="h-7 flex-1 justify-center text-[11px]"
                aria-label={sendLabel} onClick={() => onSendEdits?.()}>
                <Send className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                <span>{sendLabel}</span>
              </Button>
              <Button type="button" variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
                aria-label="Discard all edits" onClick={() => onDiscardEdits?.()}>
                Discard
              </Button>
            </div>
          </FileSheetControlRow>
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

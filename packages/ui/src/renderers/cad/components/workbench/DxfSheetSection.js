import { ChevronDown, ChevronRight, Move, Ruler, RotateCcw, Send, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@hardcore/ui/primitives/button";
import { Input } from "@hardcore/ui/primitives/input";
import { cn } from "@hardcore/ui/utils";

import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_COMPACT_INPUT_CLASSES,
  FileSheetControlRow,
  FileSheetInlineControlRow,
  FileSheetSectionBody,
  FileSheetSegmentedControl,
  FileSheetSelectRow,
  FileSheetStatusText,
  FileSheetSubsection
} from "./FileSheet.js";
import { drawingEditSnippet } from "../../workbench/drawingEdits.js";
import { FILE_SHEET_SECTION_IDS } from "../../workbench/fileSheetSections.js";

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
  { layer: "HIDDEN", label: "Hidden" },
  { layer: "CENTER", label: "Centre" },
  { layer: "DIM", label: "Dims" },
  { layer: "NOTES", label: "Notes" },
  { layer: "TITLE", label: "Title" }
]);

function titleCase(value) {
  return String(value || "").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/** A small toggle chip: pressed = shown. */
function Chip({ pressed, onClick, children, title, className }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      title={title}
      onClick={onClick}
      className={cn(
        "h-6 rounded-md border px-2 text-[11px] leading-none transition-colors",
        pressed
          ? "border-transparent bg-sidebar-accent text-sidebar-accent-foreground"
          : "border-border/70 text-muted-foreground hover:text-foreground",
        className
      )}
    >
      {children}
    </button>
  );
}

function editLabel(edit) {
  if (edit.kind === "move") return `Move ${edit.view} by ${edit.dx}, ${edit.dy}`;
  if (edit.kind === "dim") return `New dimension in ${edit.view}`;
  if (edit.kind === "dia") return `Ø${Math.round(edit.r * 200) / 100} callout in ${edit.view}`;
  if (edit.kind === "rad") return `R${Math.round(edit.r * 100) / 100} callout in ${edit.view}`;
  if (edit.kind === "ang") return `Angle in ${edit.view}`;
  if (edit.kind === "del") return `Remove ${edit.view} ${/^overall/.test(String(edit.index)) ? edit.index.replace("overall-", "overall ") : `#${Number(edit.index) + 1 || edit.index}`}`;
  return `${edit.view} #${Number(edit.index) + 1 || edit.index}: ${edit.spec}`;
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
  onRemoveDimension,
  onDiscardEdit,
  onDiscardEdits,
  onSendEdits,
  sendLabel = "Send to chat"
}) {
  const [toleranceDraft, setToleranceDraft] = useState("");
  const [listOpen, setListOpen] = useState(false);
  const layerNames = new Set(layers.map((layer) => String(layer?.name || "").toUpperCase()));
  const hidden = new Set(Array.isArray(hiddenLayers) ? hiddenLayers : []);
  const lineWork = DXF_DRAWING_LINE_WORK.filter((entry) => layerNames.has(entry.layer));
  const dimensions = normalizeDxfDimensionDisplay(dimensionDisplay);
  const setDimension = (key, next) => onDimensionDisplayChange?.(normalizeDxfDimensionDisplay({ ...dimensions, [key]: next }));
  const factLine = [
    facts?.paper ? facts.paper.split(" · ")[0] : "",
    facts?.scale,
    facts?.units ? facts.units.toUpperCase() : "",
    facts?.projection ? titleCase(facts.projection) : "",
    facts?.revision ? `Rev ${facts.revision}` : "",
    facts?.sheet ? `Sheet ${facts.sheet}` : ""
  ].filter(Boolean).join(" · ");
  const editable = views.length > 0 && Boolean(onEditToolChange);
  const pickHint = editTool !== "pick" ? ""
    : pickedPointCount ? "Click empty sheet to place it, or pick a second edge, corner or hole for a distance or angle"
      : "Pick an edge, hole, arc, corner or midpoint, then click where the dimension goes. Two picks give a distance or angle. Pick a dimension to change or remove it";

  return (
    <FileSheetSectionBody>
      <FileSheetSubsection title={facts?.title || "Sheet"}>
        {facts?.partNumber ? <FileSheetStatusText>{facts.partNumber}</FileSheetStatusText> : null}
        {factLine ? <FileSheetStatusText>{factLine}</FileSheetStatusText> : null}
        {!facts?.partNumber && !factLine ? <FileSheetStatusText>No title block in this drawing.</FileSheetStatusText> : null}
      </FileSheetSubsection>

      {editable ? (
        <FileSheetSubsection title="Edit">
          <div className="flex flex-wrap items-center gap-1 px-2">
            {views.map((view) => (
              <Chip key={view.name} pressed={false} title={view.at ? `at ${Math.round(view.at[0])}, ${Math.round(view.at[1])} mm` : undefined}>
                {view.name.toUpperCase()}
              </Chip>
            ))}
          </div>
          <FileSheetControlRow label={null}>
            <div className="flex min-w-0 items-center gap-2">
              <Button
                type="button"
                variant={editTool === "pick" ? "secondary" : "outline"}
                size="sm"
                className={`${FILE_SHEET_COMPACT_BUTTON_CLASSES} min-w-0 flex-1 justify-center`}
                aria-pressed={editTool === "pick"}
                aria-label="Smart dimension"
                onClick={() => onEditToolChange(editTool === "pick" ? "" : "pick")}
              >
                <Ruler className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                <span className="truncate">Dimension</span>
              </Button>
              <Button
                type="button"
                variant={editTool === "move" ? "secondary" : "outline"}
                size="sm"
                className={`${FILE_SHEET_COMPACT_BUTTON_CLASSES} min-w-0 flex-1 justify-center`}
                aria-pressed={editTool === "move"}
                aria-label="Move views"
                onClick={() => onEditToolChange(editTool === "move" ? "" : "move")}
              >
                <Move className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                <span className="truncate">Move</span>
              </Button>
            </div>
          </FileSheetControlRow>
          {pickHint ? <FileSheetStatusText>{pickHint}</FileSheetStatusText> : null}
          {editTool === "move" ? <FileSheetStatusText>Drag a view on the sheet. Click Move again to stop.</FileSheetStatusText> : null}
        </FileSheetSubsection>
      ) : null}

      {dimensionCount > 0 ? (
        <FileSheetSubsection title={`Dimensions · ${dimensionCount}`}>
          {sheetDimensions.length ? (
            <button
              type="button"
              className="flex w-full items-center gap-1 px-2 text-[11px] text-muted-foreground hover:text-foreground"
              aria-expanded={listOpen}
              onClick={() => setListOpen((open) => !open)}
            >
              {listOpen ? <ChevronDown className="size-3" aria-hidden="true" /> : <ChevronRight className="size-3" aria-hidden="true" />}
              <span>{listOpen ? "Hide list" : "Show list, pick one to change or remove"}</span>
            </button>
          ) : null}
          {listOpen && sheetDimensions.length ? (
            <div className="max-h-44 space-y-px overflow-y-auto px-1">
              {sheetDimensions.map((dimension) => {
                const key = `${dimension.view}:${dimension.index}`;
                const selected = selectedDimension === key;
                return (
                  <button
                    key={key}
                    type="button"
                    className={cn(
                      "flex w-full min-w-0 items-center gap-2 rounded-md px-1 py-0.5 text-left text-[11px] hover:bg-sidebar-accent/60",
                      selected && "bg-sidebar-accent text-sidebar-accent-foreground"
                    )}
                    aria-pressed={selected}
                    onClick={() => { onSelectDimension?.(selected ? "" : key); setToleranceDraft(""); }}
                  >
                    <span className="w-12 shrink-0 truncate uppercase text-muted-foreground">{dimension.view}</span>
                    <span className="min-w-0 flex-1 truncate font-medium tabular-nums text-sidebar-foreground">{dimension.value || "—"}</span>
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
                <Button type="button" variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
                  disabled={!toleranceDraft.trim()}
                  onClick={() => { onAddTolerance(selectedDimension, toleranceDraft.trim()); setToleranceDraft(""); }}>
                  Apply
                </Button>
                {onRemoveDimension ? (
                  <Button type="button" variant="outline" size="sm" className={FILE_SHEET_COMPACT_BUTTON_CLASSES}
                    aria-label="Remove the selected dimension" title="Remove this dimension"
                    onClick={() => { onRemoveDimension(selectedDimension); setToleranceDraft(""); }}>
                    Remove
                  </Button>
                ) : null}
              </div>
            </FileSheetControlRow>
          ) : null}
          <FileSheetSelectRow
            label="Units"
            value={dimensions.units}
            onValueChange={(next) => setDimension("units", next)}
            options={DXF_DIMENSION_UNIT_OPTIONS.map(({ value, label }) => ({ value, label }))}
          />
          <FileSheetSelectRow
            label="Precision"
            value={dimensions.decimals}
            onValueChange={(next) => setDimension("decimals", next)}
            options={DXF_DIMENSION_DECIMAL_OPTIONS.map(({ value, label }) => ({ value, label }))}
          />
          <FileSheetSelectRow
            label="Text"
            value={dimensions.text}
            onValueChange={(next) => setDimension("text", next)}
            options={DXF_DIMENSION_TEXT_OPTIONS.map(({ value, label }) => ({ value, label }))}
          />
        </FileSheetSubsection>
      ) : null}

      {edits.length ? (
        <FileSheetSubsection title={`Staged edits · ${edits.length}`}>
          <div className="space-y-px px-1">
            {edits.map((edit) => (
              <div key={edit.id} className="flex min-w-0 items-center gap-1 rounded-md px-1 py-0.5 text-[11px]">
                <span className="min-w-0 flex-1 truncate text-sidebar-foreground" title={drawingEditSnippet(edit, { views, dimensions: sheetDimensions })}>
                  {editLabel(edit)}
                </span>
                <Button type="button" variant="ghost" size="icon-sm" className="size-5 shrink-0 text-muted-foreground hover:text-foreground"
                  aria-label="Discard this edit" onClick={() => onDiscardEdit?.(edit.id)}>
                  <X className="size-3" strokeWidth={1.8} aria-hidden="true" />
                </Button>
              </div>
            ))}
          </div>
          <FileSheetControlRow label={null}>
            <div className="flex items-center gap-2">
              <Button type="button" variant="default" size="sm" className="h-7 flex-1 justify-center text-[11px]"
                aria-label={sendLabel} title="Previewed in red. Nothing is saved until the script changes." onClick={() => onSendEdits?.()}>
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
        <FileSheetInlineControlRow label="Lines">
          <FileSheetSegmentedControl
            ariaLabel="Line weight"
            value={normalizeDxfLineWeight(lineWeight)}
            onChange={(next) => onLineWeightChange?.(normalizeDxfLineWeight(next, lineWeight))}
            options={DXF_LINE_WEIGHT_OPTIONS.map(({ value, label }) => ({ value, label }))}
            fit
          />
        </FileSheetInlineControlRow>
        {lineWork.length ? (
          <div className="flex flex-wrap items-center gap-1 px-2">
            {lineWork.map((entry) => (
              <Chip
                key={entry.layer}
                pressed={!hidden.has(entry.layer)}
                title={hidden.has(entry.layer) ? `Show ${entry.label.toLowerCase()}` : `Hide ${entry.label.toLowerCase()}`}
                onClick={() => onLayerVisibilityChange?.(entry.layer, hidden.has(entry.layer))}
              >
                {entry.label}
              </Chip>
            ))}
          </div>
        ) : null}
        {onReset ? (
          <FileSheetControlRow label={null}>
            <Button type="button" variant="outline" size="sm"
              className={`${FILE_SHEET_COMPACT_BUTTON_CLASSES} w-full justify-center`}
              onClick={() => onReset()} aria-label="Reset sheet display" title="Reset">
              <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
              <span>Reset</span>
            </Button>
          </FileSheetControlRow>
        ) : null}
      </FileSheetSubsection>
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

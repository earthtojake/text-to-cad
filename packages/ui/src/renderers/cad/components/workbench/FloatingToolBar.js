import SelectionFilterMenu from "./SelectionFilterMenu.jsx";
import { MEASURE_SELECTION_FILTERS, SELECTION_FILTERS } from "../../workbench/selectionFilter.js";
import { CirclePlay, Hand, MousePointer2, PenTool, Ruler } from "lucide-react";
import { renderCapabilities, supportsTool } from "@hardcore/core/lib/renderCapabilities.js";
import { TooltipProvider } from "@hardcore/ui/primitives/tooltip";
import { DrawingToolbar } from "../../../../drawing/toolbar.jsx";
import { ToolbarButton } from "./ToolbarButton.js";

const FLOATING_TOOL_BAR_SURFACE_CLASS = "bg-background border border-border text-foreground shadow-sm";

function InteractionToolBar({
  renderFormat, floatingCadToolbarPosition, selectionFilter = null, onSelectionFilterChange,
  selectionFilterNotice = "", selectionToolActive, referenceSelectionPending = false,
  referenceSelectionUnavailable = false, referenceSelectionDeferred = false,
  drawToolActive, measureModeActive = false, measurementPanel = null,
  measureDisabled = false, measureSupported = null, measureSnapFilter = null, onMeasureSnapFilterChange,
  panToolActive, animateAvailable = false, animateToolActive = false, handleSelectTabToolMode,
  viewerLoading, selectedMeshData, drawing,
}) {
  const canMeasure = measureSupported ?? renderCapabilities(renderFormat).measure;
  const selectDisabled = viewerLoading || !selectedMeshData || referenceSelectionPending || referenceSelectionUnavailable || referenceSelectionDeferred;
  const selectActive = !referenceSelectionDeferred && selectionToolActive;
  const selectLabel = referenceSelectionPending ? "Preparing selection" : "Select";
  const selectTool = <ToolbarButton label={selectLabel} active={selectActive} disabled={selectDisabled}
    aria-pressed={selectActive} aria-description={selectionFilter !== null ? "Select again to choose a selection filter" : undefined}
    onPointerDown={event => { if (!selectActive) event.preventDefault(); }}
    onKeyDown={event => {
      if (!selectActive && ["Enter", " ", "ArrowDown"].includes(event.key)) {
        event.preventDefault(); handleSelectTabToolMode("references");
      }
    }}
    onClick={() => handleSelectTabToolMode("references")}>
    <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />
  </ToolbarButton>;
  // Measure works like Select: the first press takes up the tool, a press while
  // it is active opens what it snaps to. It does not toggle off; another tool or
  // Escape ends the session.
  const measureTool = <ToolbarButton label="Measure" active={measureModeActive}
    disabled={viewerLoading || !selectedMeshData || measureDisabled} aria-pressed={measureModeActive}
    aria-description={measureSnapFilter !== null ? "Measure again to choose what measurements snap to" : undefined}
    onPointerDown={event => { if (!measureModeActive) event.preventDefault(); }}
    onKeyDown={event => {
      if (!measureModeActive && ["Enter", " ", "ArrowDown"].includes(event.key)) {
        event.preventDefault(); handleSelectTabToolMode("measure");
      }
    }}
    onClick={() => { if (!measureModeActive || measureSnapFilter === null) handleSelectTabToolMode("measure"); }}>
    <Ruler className="size-3" strokeWidth={2} aria-hidden="true" />
  </ToolbarButton>;
  return (<div className="absolute z-20 flex max-w-[calc(100%-28px)] flex-col items-end gap-1"
    data-cad-toolbar="tools" style={floatingCadToolbarPosition}>
    <TooltipProvider delayDuration={250}>
      <div role="group" aria-label="Interaction tools" className={`pointer-events-auto inline-flex min-h-8 max-w-full flex-wrap items-center gap-0.5 rounded-md p-1 ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}>
        {supportsTool(renderFormat, "select") && (selectionFilter !== null
          ? <SelectionFilterMenu value={selectionFilter} onChange={onSelectionFilterChange} trigger={selectTool} /> : selectTool)}
        {supportsTool(renderFormat, "pan") && <ToolbarButton label="Pan" active={panToolActive} onClick={() => handleSelectTabToolMode("pan")}
          disabled={viewerLoading || !selectedMeshData} aria-pressed={panToolActive}>
          <Hand className="size-3" strokeWidth={2} aria-hidden="true" />
        </ToolbarButton>}
        {canMeasure && (measureSnapFilter !== null
          ? <SelectionFilterMenu options={MEASURE_SELECTION_FILTERS} menuLabel="Snap to" hint="" value={measureSnapFilter}
            onChange={onMeasureSnapFilterChange} trigger={measureTool} /> : measureTool)}
        {supportsTool(renderFormat, "draw") && <ToolbarButton label="Draw" active={drawToolActive} onClick={() => handleSelectTabToolMode("draw")}
          disabled={viewerLoading || !selectedMeshData} aria-pressed={drawToolActive}>
          <PenTool className="size-3" strokeWidth={2} aria-hidden="true" />
        </ToolbarButton>}
        {/* Rightmost, and only in a file that has routines: no routines, no button (never a disabled one). Its controls are the playbar, the bottom action while it is active. */}
        {animateAvailable && <ToolbarButton label="Animate" active={animateToolActive} onClick={() => handleSelectTabToolMode("animate")}
          disabled={viewerLoading || !selectedMeshData} aria-pressed={animateToolActive}>
          <CirclePlay className="size-3" strokeWidth={2} aria-hidden="true" />
        </ToolbarButton>}
      </div>
    </TooltipProvider>
      {selectionToolActive && selectionFilter !== null && selectionFilter !== "all" && (
        <div className={`pointer-events-auto max-w-full rounded-md px-2 py-0.5 text-micro text-muted-foreground ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}>
          {SELECTION_FILTERS.find(item => item.id === selectionFilter)?.label}
        </div>
      )}
      {selectionToolActive && selectionFilterNotice && <p role="status" className="max-w-56 rounded-md border bg-background px-2 py-1 text-micro text-muted-foreground shadow-sm">{selectionFilterNotice}</p>}


      {measureModeActive && measureSnapFilter !== null && measureSnapFilter !== "all" && (
        <div className={`pointer-events-auto max-w-full rounded-md px-2 py-0.5 text-micro text-muted-foreground ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}>
          {MEASURE_SELECTION_FILTERS.find(item => item.id === measureSnapFilter)?.label}
        </div>
      )}
      {measureModeActive && measurementPanel}
      {supportsTool(renderFormat, "draw") && drawToolActive
        ? <DrawingToolbar drawing={drawing} /> : null}
    </div>
  );

}

export default function FloatingToolBar({ previewMode, selectedEntry, ...props }) {
  return !selectedEntry || previewMode ? null : <InteractionToolBar {...props} />;
}

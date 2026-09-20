import SelectionFilterMenu from "./SelectionFilterMenu.jsx";
import { MEASURE_SELECTION_FILTERS, SELECTION_FILTERS } from "../../workbench/selectionFilter.js";
import { CirclePlay, MousePointer2, PenTool, Rotate3d, Ruler } from "lucide-react";
import { renderCapabilities, supportsTool } from "@hardcore/core/lib/renderCapabilities.js";
import { DrawingToolbar } from "../../../../drawing/toolbar.jsx";
import KitFloatingToolBar, { FLOATING_TOOL_BAR_SURFACE_CLASS } from "../../../kit/tools/FloatingToolBar.js";

// This renderer's tools, in order, for the file on screen. The kit's strip draws
// whatever list it is handed; which tools a format has, what they are called and
// what a press does is decided here.
export function cadInteractionTools({
  renderFormat, selectionFilter = null, onSelectionFilterChange,
  selectionFilterNotice = "", selectionToolActive, referenceSelectionPending = false,
  referenceSelectionUnavailable = false, referenceSelectionDeferred = false,
  drawToolActive, measureModeActive = false, measurementPanel = null,
  measureDisabled = false, measureSupported = null, measureSnapFilter = null, onMeasureSnapFilterChange,
  animateAvailable = false, animateToolActive = false,
  poseAvailable = false, poseToolActive = false, poseLeads = false, handleSelectTabToolMode,
  viewerLoading, selectedMeshData, drawing,
}) {
  const canMeasure = measureSupported ?? renderCapabilities(renderFormat).measure;
  const selectDisabled = viewerLoading || !selectedMeshData || referenceSelectionPending || referenceSelectionUnavailable || referenceSelectionDeferred;
  const selectActive = !referenceSelectionDeferred && selectionToolActive;
  const idle = viewerLoading || !selectedMeshData;
  const selectTool = supportsTool(renderFormat, "select") ? {
    id: "references",
    label: referenceSelectionPending ? "Preparing selection" : "Select",
    icon: <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />,
    active: selectActive, disabled: selectDisabled,
    description: selectionFilter !== null ? "Select again to choose a selection filter" : undefined,
    secondPressOpensMenu: true,
    onSelect: () => handleSelectTabToolMode("references"),
    menu: selectionFilter !== null
      ? trigger => <SelectionFilterMenu value={selectionFilter} onChange={onSelectionFilterChange} trigger={trigger} /> : undefined,
    subToolbar: selectionToolActive && ((selectionFilter !== null && selectionFilter !== "all") || selectionFilterNotice) ? <>
      {selectionFilter !== null && selectionFilter !== "all" && (
        <div className={`pointer-events-auto max-w-full rounded-md px-2 py-0.5 text-micro text-muted-foreground ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}>
          {SELECTION_FILTERS.find(item => item.id === selectionFilter)?.label}
        </div>
      )}
      {selectionFilterNotice && <p role="status" className="max-w-56 rounded-md border bg-background px-2 py-1 text-micro text-muted-foreground shadow-sm">{selectionFilterNotice}</p>}
    </> : null,
  } : null;
  // Measure works like Select: the first press takes up the tool, a press while
  // it is active opens what it snaps to. It does not toggle off; another tool or
  // Escape ends the session.
  const measureTool = canMeasure ? {
    id: "measure", label: "Measure",
    icon: <Ruler className="size-3" strokeWidth={2} aria-hidden="true" />,
    active: measureModeActive, disabled: idle || measureDisabled,
    description: measureSnapFilter !== null ? "Measure again to choose what measurements snap to" : undefined,
    secondPressOpensMenu: true,
    onSelect: () => { if (!measureModeActive || measureSnapFilter === null) handleSelectTabToolMode("measure"); },
    menu: measureSnapFilter !== null
      ? trigger => <SelectionFilterMenu options={MEASURE_SELECTION_FILTERS} menuLabel="Snap to" hint="" value={measureSnapFilter}
        onChange={onMeasureSnapFilterChange} trigger={trigger} /> : undefined,
    subToolbar: measureModeActive && ((measureSnapFilter !== null && measureSnapFilter !== "all") || measurementPanel) ? <>
      {measureSnapFilter !== null && measureSnapFilter !== "all" && (
        <div className={`pointer-events-auto max-w-full rounded-md px-2 py-0.5 text-micro text-muted-foreground ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}>
          {MEASURE_SELECTION_FILTERS.find(item => item.id === measureSnapFilter)?.label}
        </div>
      )}
      {measurementPanel}
    </> : null,
  } : null;
  const drawTool = supportsTool(renderFormat, "draw") ? {
    id: "draw", label: "Draw",
    icon: <PenTool className="size-3" strokeWidth={2} aria-hidden="true" />,
    active: drawToolActive, disabled: idle,
    onSelect: () => handleSelectTabToolMode("draw"),
    subToolbar: drawToolActive ? <DrawingToolbar drawing={drawing} /> : null,
  } : null;
  // Only in a file with joints to drag (never a disabled button). A robot is posed
  // before it is inspected, so there Pose leads the tools; a STEP's Pose sits with
  // Animate, the other tool that moves the model.
  const poseTool = poseAvailable ? {
    id: "pose", label: "Pose",
    icon: <Rotate3d className="size-3" strokeWidth={2} aria-hidden="true" />,
    active: poseToolActive, disabled: idle,
    onSelect: () => handleSelectTabToolMode("pose"),
  } : null;
  // Rightmost, and only in a file that has routines: no routines, no button (never a disabled one). Its controls are the playbar, the bottom action while it is active.
  const animateTool = animateAvailable ? {
    id: "animate", label: "Animate",
    icon: <CirclePlay className="size-3" strokeWidth={2} aria-hidden="true" />,
    active: animateToolActive, disabled: idle,
    onSelect: () => handleSelectTabToolMode("animate"),
  } : null;
  return [poseLeads ? poseTool : null, selectTool, measureTool, drawTool, poseLeads ? null : poseTool, animateTool].filter(Boolean);
}

export default function FloatingToolBar({ previewMode, selectedEntry, floatingCadToolbarPosition, ...props }) {
  return !selectedEntry || previewMode ? null
    : <KitFloatingToolBar tools={cadInteractionTools(props)} position={floatingCadToolbarPosition} />;
}

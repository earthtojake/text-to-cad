import {
  Copy,
  Crosshair,
  Download,
  MousePointer2,
  Play,
  PenTool,
  Ruler
} from "lucide-react";
import { RENDER_FORMAT } from "../../lib/workbench/constants";
import { TooltipProvider } from "../ui/tooltip";
import DrawingToolbar from "./DrawingToolbar";
import { ToolbarButton } from "./ToolbarButton";
import { CAD_WORKSPACE_TOOLBAR_DESKTOP_WIDTH_CLASS } from "./ToolbarShell";

const FLOATING_TOOL_BAR_SURFACE_CLASS =
  "cad-glass-surface border border-sidebar-border text-sidebar-foreground shadow-sm";

function DesktopFloatingToolBar({
  renderFormat,
  floatingCadToolbarPosition,
  selectionToolActive,
  measureToolAvailable = false,
  measureToolActive = false,
  referenceSelectionPending = false,
  referenceSelectionUnavailable = false,
  urdfPosePickerAvailable = false,
  urdfPosePickerActive = false,
  handleToggleUrdfPosePicker,
  drawToolActive,
  handleSelectTabToolMode,
  explorerLoading,
  selectedMeshData,
  selectedDxfData,
  drawingToolOptions,
  drawingTool,
  handleSelectDrawingTool,
  handleUndoDrawing,
  handleRedoDrawing,
  handleClearDrawings,
  canUndoDrawing,
  canRedoDrawing,
  drawingStrokes,
  handleEnterPreviewMode,
  handleScreenshotCopy,
  handleScreenshotDownload
}) {
  const dxfMode = renderFormat === RENDER_FORMAT.DXF;
  const urdfMode = renderFormat === RENDER_FORMAT.URDF;
  const stlMode = renderFormat === RENDER_FORMAT.STL;
  const meshOnlyMode = stlMode || renderFormat === RENDER_FORMAT.THREE_MF;
  const captureDisabled = explorerLoading || (dxfMode ? !selectedDxfData : !selectedMeshData);
  const selectDisabled = explorerLoading || !selectedMeshData || referenceSelectionPending || referenceSelectionUnavailable;
  const measureDisabled = !measureToolAvailable || selectDisabled;
  const posePickerDisabled = explorerLoading || !selectedMeshData || !urdfPosePickerAvailable;
  const selectLabel = referenceSelectionUnavailable
    ? "Selectable topology unavailable"
    : referenceSelectionPending
      ? "Preparing selectable topology"
      : "Select";

  return (
    <div
      className="absolute z-20 flex flex-col items-end gap-1.5"
      style={floatingCadToolbarPosition}
    >
      <TooltipProvider delayDuration={250}>
        <div className={`pointer-events-auto inline-flex w-fit items-center gap-1 self-end rounded-md p-1 ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}>
          {!dxfMode ? (
            <>
              {!urdfMode && !meshOnlyMode ? (
                <>
                  <ToolbarButton
                    label={selectLabel}
                    active={selectionToolActive}
                    onClick={() => handleSelectTabToolMode("references")}
                    disabled={selectDisabled}
                    aria-pressed={selectionToolActive}
                  >
                    <MousePointer2 className="size-3.5" strokeWidth={2} aria-hidden="true" />
                  </ToolbarButton>

                  <ToolbarButton
                    label="Measure"
                    active={measureToolActive}
                    onClick={() => handleSelectTabToolMode("measure")}
                    disabled={measureDisabled}
                    aria-pressed={measureToolActive}
                  >
                    <Ruler className="size-3.5" strokeWidth={2} aria-hidden="true" />
                  </ToolbarButton>

                  <ToolbarButton
                    label="Draw"
                    active={drawToolActive}
                    onClick={() => handleSelectTabToolMode("draw")}
                    disabled={explorerLoading || !selectedMeshData}
                    aria-pressed={drawToolActive}
                  >
                    <PenTool className="size-3.5" strokeWidth={2} aria-hidden="true" />
                  </ToolbarButton>
                </>
              ) : null}

              {urdfMode ? (
                <ToolbarButton
                  label="Select Pose"
                  active={urdfPosePickerActive}
                  onClick={handleToggleUrdfPosePicker}
                  disabled={posePickerDisabled}
                  aria-pressed={urdfPosePickerActive}
                >
                  <Crosshair className="size-3.5" strokeWidth={2} aria-hidden="true" />
                </ToolbarButton>
              ) : null}

              <ToolbarButton
                label="Open orbit preview"
                onClick={handleEnterPreviewMode}
                disabled={explorerLoading || !selectedMeshData}
              >
                <Play className="size-3.5" strokeWidth={2} aria-hidden="true" />
              </ToolbarButton>
            </>
          ) : null}

          <ToolbarButton
            label="Copy screenshot to clipboard"
            onClick={() => {
              void handleScreenshotCopy();
            }}
            disabled={captureDisabled}
          >
            <Copy className="size-3.5" strokeWidth={2} aria-hidden="true" />
          </ToolbarButton>

          <ToolbarButton
            label="Download screenshot"
            onClick={() => {
              void handleScreenshotDownload();
            }}
            disabled={captureDisabled}
          >
            <Download className="size-3.5" strokeWidth={2} aria-hidden="true" />
          </ToolbarButton>
        </div>
      </TooltipProvider>

      {!dxfMode && !meshOnlyMode && drawToolActive ? (
        <DrawingToolbar
          className={CAD_WORKSPACE_TOOLBAR_DESKTOP_WIDTH_CLASS}
          drawingToolOptions={drawingToolOptions}
          drawingTool={drawingTool}
          handleSelectDrawingTool={handleSelectDrawingTool}
          handleUndoDrawing={handleUndoDrawing}
          handleRedoDrawing={handleRedoDrawing}
          handleClearDrawings={handleClearDrawings}
          canUndoDrawing={canUndoDrawing}
          canRedoDrawing={canRedoDrawing}
          drawingStrokes={drawingStrokes}
        />
      ) : null}
    </div>
  );
}

export default function FloatingToolBar({
  previewMode,
  selectedEntry,
  ...toolbarProps
}) {
  if (previewMode || !selectedEntry) {
    return null;
  }

  return <DesktopFloatingToolBar {...toolbarProps} />;
}

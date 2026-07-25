import { useState } from "react";
import {
  Crosshair,
  Focus,
  MousePointer2,
  Orbit,
  PanelsTopLeft,
  Pause,
  Play,
  PenTool
} from "lucide-react";
import { RENDER_FORMAT } from "@/workbench/constants";
import {
  isMeshRenderFormat,
  isRobotRenderFormat
} from "cadjs/lib/fileFormats";
import { TooltipProvider } from "../ui/tooltip";
import DrawingToolbar from "./DrawingToolbar";
import { ToolbarButton } from "./ToolbarButton";
import { CAD_WORKSPACE_TOOLBAR_DESKTOP_WIDTH_CLASS } from "./ToolbarShell";
import { DisplayProjectionControl } from "../viewer/DisplayProjectionControl";

const FLOATING_TOOL_BAR_SURFACE_CLASS =
  "cad-glass-surface border border-sidebar-border text-sidebar-foreground shadow-sm";
const FLOATING_TOOL_BAR_BUTTON_CLASSES =
  "grid size-6 shrink-0 place-items-center rounded-sm text-sidebar-foreground/70 shadow-none transition hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 disabled:pointer-events-none disabled:opacity-50 data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground";

function DesktopFloatingToolBar({
  renderFormat,
  floatingCadToolbarPosition,
  selectionToolActive,
  referenceSelectionPending = false,
  referenceSelectionUnavailable = false,
  referenceSelectionDeferred = false,
  urdfPosePickerAvailable = false,
  urdfPosePickerActive = false,
  handleToggleUrdfPosePicker,
  stepAnimationAvailable = false,
  stepAnimationPlaying = false,
  stepAnimationDisabled = false,
  handleStepAnimationPlayToggle,
  drawToolActive,
  handleSelectTabToolMode,
  displayMode,
  onDisplayModeChange,
  projection,
  onProjectionChange,
  viewerLoading,
  selectedMeshData,
  selectedDxfData,
  selectedImplicitModel,
  drawingToolOptions,
  drawingTool,
  handleSelectDrawingTool,
  handleUndoDrawing,
  handleRedoDrawing,
  handleClearDrawings,
  canUndoDrawing,
  canRedoDrawing,
  drawingStrokes,
  threeViewMarkupAvailable = false,
  handleOpenThreeViewMarkup,
  handleEnterPreviewMode,
  handleScreenshotCopy
}) {
  const [displayMenuOpen, setDisplayMenuOpen] = useState(false);
  const dxfMode = renderFormat === RENDER_FORMAT.DXF;
  const implicitMode = renderFormat === RENDER_FORMAT.IMPLICIT;
  const urdfMode = renderFormat === RENDER_FORMAT.URDF;
  const robotMode = isRobotRenderFormat(renderFormat);
  const meshOnlyMode = isMeshRenderFormat(renderFormat);
  const renderReady = implicitMode ? !!selectedImplicitModel : dxfMode ? !!selectedDxfData : !!selectedMeshData;
  const captureDisabled = viewerLoading || !renderReady;
  const selectDisabled = viewerLoading ||
    !selectedMeshData ||
    referenceSelectionPending ||
    referenceSelectionUnavailable ||
    referenceSelectionDeferred;
  const posePickerDisabled = viewerLoading || !selectedMeshData || !urdfPosePickerAvailable;
  const selectLabel = referenceSelectionPending ? "Preparing selection" : "Select";
  const showStepAnimationPlay = renderFormat === RENDER_FORMAT.STEP && stepAnimationAvailable;
  const stepAnimationPlayDisabled = viewerLoading || !selectedMeshData || stepAnimationDisabled;
  const stepAnimationLabel = stepAnimationPlaying ? "Pause" : "Play";
  const displayControlAvailable = renderFormat === RENDER_FORMAT.STEP &&
    typeof onDisplayModeChange === "function" &&
    typeof onProjectionChange === "function";

  return (
    <div
      className="absolute z-20 flex flex-col items-end gap-1"
      style={floatingCadToolbarPosition}
    >
      <TooltipProvider delayDuration={250}>
        <div className={`pointer-events-auto inline-flex h-8 w-fit items-center gap-0.5 self-end rounded-md p-1 ${FLOATING_TOOL_BAR_SURFACE_CLASS}`}>
          {!dxfMode && !implicitMode && !robotMode && !meshOnlyMode ? (
            <>
              <ToolbarButton
                label={selectLabel}
                active={referenceSelectionDeferred ? false : selectionToolActive}
                onClick={() => handleSelectTabToolMode("references")}
                disabled={selectDisabled}
                aria-pressed={referenceSelectionDeferred ? false : selectionToolActive}
              >
                <MousePointer2 className="size-3" strokeWidth={2} aria-hidden="true" />
              </ToolbarButton>

              <ToolbarButton
                label="Draw"
                active={drawToolActive}
                onClick={() => handleSelectTabToolMode("draw")}
                disabled={viewerLoading || !selectedMeshData}
                aria-pressed={drawToolActive}
              >
                <PenTool className="size-3" strokeWidth={2} aria-hidden="true" />
              </ToolbarButton>

              <ToolbarButton
                label="Orthographic markup"
                onClick={handleOpenThreeViewMarkup}
                disabled={!threeViewMarkupAvailable}
              >
                <PanelsTopLeft className="size-3" strokeWidth={2} aria-hidden="true" />
              </ToolbarButton>

              {displayControlAvailable ? (
                <DisplayProjectionControl
                  displayMode={displayMode}
                  onDisplayModeChange={onDisplayModeChange}
                  projection={projection}
                  onProjectionChange={onProjectionChange}
                  open={displayMenuOpen}
                  onOpenChange={setDisplayMenuOpen}
                  triggerClassName={FLOATING_TOOL_BAR_BUTTON_CLASSES}
                  contentAlign="end"
                  contentSide="bottom"
                  contentSideOffset={6}
                />
              ) : null}

              {showStepAnimationPlay ? (
                <ToolbarButton
                  label={stepAnimationLabel}
                  active={stepAnimationPlaying}
                  onClick={handleStepAnimationPlayToggle}
                  disabled={stepAnimationPlayDisabled}
                  aria-pressed={stepAnimationPlaying}
                >
                  {stepAnimationPlaying ? (
                    <Pause className="size-3" strokeWidth={2} aria-hidden="true" />
                  ) : (
                    <Play className="size-3" strokeWidth={2} aria-hidden="true" />
                  )}
                </ToolbarButton>
              ) : null}
            </>
          ) : null}

          {!dxfMode && urdfMode ? (
            <ToolbarButton
              label="Select Pose"
              active={urdfPosePickerActive}
              onClick={handleToggleUrdfPosePicker}
              disabled={posePickerDisabled}
              aria-pressed={urdfPosePickerActive}
            >
              <Crosshair className="size-3" strokeWidth={2} aria-hidden="true" />
            </ToolbarButton>
          ) : null}

          {!dxfMode ? (
            <ToolbarButton
              label="Orbit"
              onClick={handleEnterPreviewMode}
              disabled={viewerLoading || !renderReady}
            >
              <Orbit className="size-3" strokeWidth={2} aria-hidden="true" />
            </ToolbarButton>
          ) : null}

          <ToolbarButton
            label="Copy screenshot"
            onClick={() => {
              void handleScreenshotCopy();
            }}
            disabled={captureDisabled}
          >
            <Focus className="size-3" strokeWidth={2} aria-hidden="true" />
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

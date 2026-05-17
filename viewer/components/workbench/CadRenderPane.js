import CadViewer from "../CadViewer";
import DxfViewer from "../DxfViewer";
import { Alert, AlertDescription, AlertTitle } from "../ui/alert";
import { Button } from "../ui/button";
import { RENDER_FORMAT } from "../../lib/workbench/constants";
import { LOOK_FLOOR_MODES } from "../../lib/lookSettings";
import { VIEWER_SCENE_SCALE } from "../../lib/viewer/sceneScale";
import { VIEWER_PICK_MODE } from "../../lib/viewer/constants";

const EMPTY_LIST = Object.freeze([]);

export default function CadRenderPane({
  viewerRef,
  renderFormat,
  renderPartsIndividually = false,
  selectedMeshData,
  selectedDxfData,
  selectedDxfMeshData,
  selectedKey,
  selectedDxfKey,
  viewerPerspective,
  viewerPerspectiveRef,
  lookSettings,
  previewMode,
  isDesktop,
  viewportFrameInsets,
  viewerLoading,
  viewerAlert,
  stepUpdateInProgress,
  viewPlaneOffsetRight = 16,
  viewerMode,
  assemblyParts,
  hiddenPartIds,
  selectedPartIds,
  hoveredPartId,
  hoveredReferenceId,
  selectedReferenceIds,
  selectorRuntime,
  pickableFaces,
  pickableEdges,
  pickableVertices,
  inspectedAssemblyPartId,
  showPartLabels,
  drawToolActive,
  drawingTool,
  drawingStrokes,
  measurements,
  pendingMeasurementAnchor,
  handleDrawingStrokesChange,
  handleRemoveMeasurement,
  handlePerspectiveChange,
  handleModelHoverChange,
  handleModelReferenceActivate,
  handleModelReferenceDoubleActivate,
  handleViewerAlertChange,
  selectionCount,
  copyButtonLabel,
  handleCopySelection,
  handleScreenshotCopy,
  partIntroAnimation = null
}) {
  const viewerAlertVariant = viewerAlert?.severity === "warning" ? "warning" : "destructive";
  const viewerAlertSummaryClasses = viewerAlert?.severity === "warning" ? "text-chart-5" : "text-destructive";
  const dxfMode = renderFormat === RENDER_FORMAT.DXF;
  const urdfMode = renderFormat === RENDER_FORMAT.URDF;
  const stlMode = renderFormat === RENDER_FORMAT.STL;
  const dxfMeshPreviewReady = dxfMode && !!selectedDxfMeshData;
  const activeMeshData = dxfMeshPreviewReady ? selectedDxfMeshData : selectedMeshData;
  const activeModelKey = dxfMeshPreviewReady ? (selectedDxfKey || selectedKey) : selectedKey;
  const ctaMode = !dxfMode && !stlMode && drawToolActive
    ? "screenshot"
    : selectionCount > 0
      ? "selection"
      : "";
  const mobileBottomOverlayOffset = ctaMode === "screenshot"
    ? "calc(env(safe-area-inset-bottom, 0px) + 10.25rem)"
    : "calc(env(safe-area-inset-bottom, 0px) + 7.25rem)";
  const bottomOverlayStyle = {
    bottom: isDesktop ? "1rem" : mobileBottomOverlayOffset
  };
  const ctaLabel = ctaMode === "screenshot" ? "Copy Screenshot" : copyButtonLabel;
  const ctaTitle = ctaMode === "screenshot" ? "Copy screenshot to clipboard" : copyButtonLabel;
  const ctaDisabled = ctaMode === "screenshot" ? viewerLoading || !activeMeshData : false;

  return (
    <div className="absolute inset-0">
      {dxfMode && !dxfMeshPreviewReady ? (
        <DxfViewer
          ref={viewerRef}
          dxfData={selectedDxfData}
          modelKey={selectedDxfKey}
          onViewerAlertChange={handleViewerAlertChange}
        />
      ) : (
        <CadViewer
          ref={viewerRef}
          meshData={activeMeshData}
          modelKey={activeModelKey}
          perspective={viewerPerspective}
          perspectiveRef={viewerPerspectiveRef}
          showEdges={true}
          recomputeNormals={false}
          lookSettings={lookSettings}
          previewMode={dxfMode ? false : previewMode}
          showViewPlane={dxfMode ? true : !previewMode}
          floorModeOverride={dxfMode ? LOOK_FLOOR_MODES.GRID : ""}
          sceneScaleMode={urdfMode ? VIEWER_SCENE_SCALE.URDF : VIEWER_SCENE_SCALE.CAD}
          viewPlaneOffsetRight={viewPlaneOffsetRight}
          viewPlaneOffsetBottom={isDesktop ? "1rem" : "calc(env(safe-area-inset-bottom, 0px) + 6rem)"}
          compactViewPlane={!isDesktop}
          viewportFrameInsets={viewportFrameInsets}
          isLoading={viewerLoading}
          pickMode={urdfMode || stlMode ? VIEWER_PICK_MODE.NONE : (!dxfMode && viewerMode === "assembly" ? VIEWER_PICK_MODE.ASSEMBLY : VIEWER_PICK_MODE.AUTO)}
          renderPartsIndividually={urdfMode ? true : renderPartsIndividually}
          pickableParts={dxfMode || urdfMode || stlMode ? EMPTY_LIST : assemblyParts}
          hiddenPartIds={dxfMode || stlMode ? [] : hiddenPartIds}
          selectedPartIds={dxfMode || stlMode ? [] : selectedPartIds}
          hoveredPartId={dxfMode || stlMode ? "" : hoveredPartId}
          hoveredReferenceId={dxfMode || stlMode ? "" : hoveredReferenceId}
          selectedReferenceIds={dxfMode || stlMode ? [] : selectedReferenceIds}
          selectorRuntime={dxfMode || stlMode ? null : selectorRuntime}
          pickableFaces={dxfMode || stlMode ? [] : pickableFaces}
          pickableEdges={dxfMode || stlMode ? [] : pickableEdges}
          pickableVertices={dxfMode || stlMode ? [] : pickableVertices}
          focusedPartId={dxfMode || stlMode ? "" : inspectedAssemblyPartId}
          showPartLabels={!dxfMode && !stlMode && showPartLabels}
          drawingEnabled={!dxfMode && !stlMode && drawToolActive}
          drawingTool={drawingTool}
          drawingStrokes={dxfMode || stlMode ? [] : drawingStrokes}
          measurements={dxfMode || stlMode ? [] : measurements}
          pendingMeasurementAnchor={dxfMode || stlMode ? null : pendingMeasurementAnchor}
          onDrawingStrokesChange={handleDrawingStrokesChange}
          onRemoveMeasurement={handleRemoveMeasurement}
          onPerspectiveChange={handlePerspectiveChange}
          onHoverReferenceChange={handleModelHoverChange}
          onActivateReference={handleModelReferenceActivate}
          onDoubleActivateReference={handleModelReferenceDoubleActivate}
          onViewerAlertChange={handleViewerAlertChange}
          partIntroAnimation={partIntroAnimation}
        />
      )}
      {!previewMode && viewerAlert ? (
        <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center px-4">
          <Alert
            variant={viewerAlertVariant}
            className="cad-glass-popover pointer-events-auto w-full max-w-xl p-5 shadow-lg"
          >
            <p className={`col-start-1 text-[11px] font-semibold uppercase tracking-[0.16em] ${viewerAlertSummaryClasses}`}>
              {viewerAlert.summary || "Viewer error"}
            </p>
            <AlertTitle className="col-start-1 mt-1 line-clamp-none text-lg text-foreground">{viewerAlert.title}</AlertTitle>
            <AlertDescription className="col-start-1 mt-1 gap-2 text-sm leading-6">
              <p>{viewerAlert.message}</p>
              {viewerAlert.resolution ? (
                <p className="text-muted-foreground/80">{viewerAlert.resolution}</p>
              ) : null}
            </AlertDescription>
            {viewerAlert.command ? (
              <div className="col-start-1 mt-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  Rebuild command
                </p>
                <code className="mt-1.5 block rounded-md bg-muted px-3 py-2 text-xs leading-6 text-foreground">
                  {viewerAlert.command}
                </code>
              </div>
            ) : null}
          </Alert>
        </div>
      ) : null}
      {!previewMode && stepUpdateInProgress ? (
        <Alert
          role="status"
          className="cad-glass-popover pointer-events-none absolute left-1/2 z-20 w-auto -translate-x-1/2 px-3 py-1.5 text-[11px] font-medium text-popover-foreground shadow-sm"
          style={bottomOverlayStyle}
        >
          STEP changed. Updating/regenerating references...
        </Alert>
      ) : null}
      {!previewMode && ctaMode && !stepUpdateInProgress ? (
        <div
          className="pointer-events-none absolute left-1/2 z-20 -translate-x-1/2"
          style={bottomOverlayStyle}
        >
          <Button
            type="button"
            variant="default"
            size="sm"
            className="pointer-events-auto h-9 max-w-[min(calc(100vw-2rem),52rem)] border border-white bg-white px-4 text-[12px] font-semibold text-black shadow-lg shadow-black/20 hover:bg-white/90 focus-visible:ring-white/40 dark:border-white dark:bg-white dark:text-black dark:hover:bg-white/90"
            disabled={ctaDisabled}
            onClick={() => {
              if (ctaMode === "screenshot") {
                void handleScreenshotCopy?.();
                return;
              }
              void handleCopySelection();
            }}
            title={ctaTitle}
          >
            <span className="truncate">{ctaLabel}</span>
          </Button>
        </div>
      ) : null}
    </div>
  );
}

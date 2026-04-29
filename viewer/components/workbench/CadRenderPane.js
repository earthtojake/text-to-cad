import { useCallback, useEffect, useRef, useState } from "react";
import CadViewer from "../CadViewer";
import DxfViewer from "../DxfViewer";
import { Alert, AlertDescription, AlertTitle } from "../ui/alert";
import { Button } from "../ui/button";
import { RENDER_FORMAT } from "../../lib/workbench/constants";
import { LOOK_FLOOR_MODES } from "../../lib/lookSettings";
import { VIEWER_SCENE_SCALE } from "../../lib/viewer/sceneScale";
import { VIEWER_PICK_MODE } from "../../lib/viewer/constants";

const EMPTY_LIST = Object.freeze([]);
const MEASUREMENT_CALLOUT_DEFAULT_OFFSET = Object.freeze({ x: 18, y: -58 });

function splitMeasurementValue(value) {
  const text = String(value || "").trim();
  const match = text.match(/^(.+?)\s+(mm|cm|m)(?:\^([23]))?$/);
  if (!match) {
    return { value: text, unit: "" };
  }
  return {
    value: match[1],
    unit: match[2],
    exponent: match[3] || ""
  };
}

function MeasurementValue({ value }) {
  const parts = splitMeasurementValue(value);
  if (!parts.unit) {
    return <>{parts.value}</>;
  }
  return (
    <>
      {parts.value} {parts.unit}
      {parts.exponent ? <sup className="text-[0.62em] leading-none">{parts.exponent}</sup> : null}
    </>
  );
}

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
  drawToolActive,
  drawingTool,
  drawingStrokes,
  handleDrawingStrokesChange,
  handlePerspectiveChange,
  handleModelHoverChange,
  handleModelReferenceActivate,
  handleModelReferenceDoubleActivate,
  handleViewerAlertChange,
  selectionCount,
  copyButtonLabel,
  handleCopySelection,
  handleScreenshotCopy,
  measureToolActive = false,
  measurementResult = null,
  measurementAnchor = null,
  measurementSelectionCount = 0,
  handleClearMeasurement,
  partIntroAnimation = null
}) {
  const [measurementDragOffset, setMeasurementDragOffset] = useState(MEASUREMENT_CALLOUT_DEFAULT_OFFSET);
  const measurementDragRef = useRef(null);
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
  const measurementValue = String(measurementResult?.formattedValue || "").trim();
  const measurementTitle = String(measurementResult?.title || "").trim();
  const measurementDetail = String(measurementResult?.detail || "").trim();
  const measurementAnchorStyle = measurementAnchor && Number.isFinite(measurementAnchor.x) && Number.isFinite(measurementAnchor.y)
    ? {
      left: `${measurementAnchor.x + measurementDragOffset.x}px`,
      top: `${measurementAnchor.y + measurementDragOffset.y}px`
    }
    : {
      left: `calc(50% + ${measurementDragOffset.x}px)`,
      bottom: isDesktop ? `calc(1rem - ${measurementDragOffset.y}px)` : `calc(env(safe-area-inset-bottom, 0px) + 7.25rem - ${measurementDragOffset.y}px)`,
      transform: "translateX(-50%)"
    };
  const handleMeasurementDragStart = useCallback((event) => {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    measurementDragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      offset: measurementDragOffset
    };
  }, [measurementDragOffset]);
  const handleMeasurementDragMove = useCallback((event) => {
    const dragState = measurementDragRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId) {
      return;
    }
    setMeasurementDragOffset({
      x: dragState.offset.x + event.clientX - dragState.startX,
      y: dragState.offset.y + event.clientY - dragState.startY
    });
  }, []);
  const handleMeasurementDragEnd = useCallback((event) => {
    const dragState = measurementDragRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId) {
      return;
    }
    measurementDragRef.current = null;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
  }, []);
  useEffect(() => {
    setMeasurementDragOffset(MEASUREMENT_CALLOUT_DEFAULT_OFFSET);
  }, [measurementResult?.referenceIds?.join("|")]);

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
          measurementResult={dxfMode || stlMode ? null : measurementResult}
          selectorRuntime={dxfMode || stlMode ? null : selectorRuntime}
          pickableFaces={dxfMode || stlMode ? [] : pickableFaces}
          pickableEdges={dxfMode || stlMode ? [] : pickableEdges}
          pickableVertices={dxfMode || stlMode ? [] : pickableVertices}
          focusedPartId={dxfMode || stlMode ? "" : inspectedAssemblyPartId}
          drawingEnabled={!dxfMode && !stlMode && drawToolActive}
          drawingTool={drawingTool}
          drawingStrokes={dxfMode || stlMode ? [] : drawingStrokes}
          onDrawingStrokesChange={handleDrawingStrokesChange}
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
      {!previewMode && measureToolActive ? (
        <div
          className="pointer-events-none fixed z-30 w-fit max-w-[min(calc(100vw-2rem),28rem)]"
          style={measurementAnchorStyle}
        >
          <div className="cad-glass-popover pointer-events-auto relative rounded-[0.85rem] border border-white/38 bg-popover/76 px-5 pb-4 pt-5 text-sidebar-foreground shadow-[0_14px_34px_rgba(0,0,0,0.24),inset_0_1px_0_rgba(255,255,255,0.14)] backdrop-blur-xl">
            <button
              type="button"
              className="absolute left-1/2 top-2 z-10 flex h-5 w-12 -translate-x-1/2 cursor-grab touch-none items-center justify-center bg-transparent active:cursor-grabbing"
              aria-label="Move measurement panel"
              onPointerDown={handleMeasurementDragStart}
              onPointerMove={handleMeasurementDragMove}
              onPointerUp={handleMeasurementDragEnd}
              onPointerCancel={handleMeasurementDragEnd}
            >
              <span className="grid grid-cols-4 gap-1" aria-hidden="true">
                {Array.from({ length: 8 }).map((_, index) => (
                  <span key={index} className="size-1 rounded-full bg-white/60" />
                ))}
              </span>
            </button>
            <div className="flex min-w-0 items-center justify-between gap-8 pt-3">
              <div className="min-w-0">
                <p className="text-[0.82rem] font-semibold uppercase leading-none tracking-[0.28em] text-white/62">
                  {measurementTitle || (measurementSelectionCount ? "Measure" : "Pick edge or corner")}
                </p>
                <p className="mt-2 truncate text-[1.45rem] font-semibold leading-none text-white">
                  {measurementValue ? <MeasurementValue value={measurementValue} /> : "Select an edge, a cylinder, or two corners"}
                </p>
                {measurementDetail ? (
                  <p className="mt-1.5 truncate text-xs text-white/58">{measurementDetail}</p>
                ) : null}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 shrink-0 px-2 text-sm font-semibold text-sky-200 hover:bg-white/10 hover:text-sky-100"
                disabled={!measurementSelectionCount && !measurementResult}
                onClick={() => handleClearMeasurement?.()}
              >
                Clear
              </Button>
            </div>
          </div>
        </div>
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

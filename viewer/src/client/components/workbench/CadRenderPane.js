import { useEffect, useMemo } from "react";
import CadViewer from "../CadViewer";
import DxfViewer from "../DxfViewer";
import ImplicitCadViewer from "../ImplicitCadViewer";
import { CircleAlert, X } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "../ui/alert";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from "../ui/dropdown-menu";
import AssemblyContextMenuItems from "./AssemblyContextMenuItems";
import { cn } from "@/ui/utils";
import { RENDER_FORMAT } from "@/workbench/constants";
import {
  isMeshRenderFormat,
  isRobotRenderFormat
} from "cadjs/lib/fileFormats";
import { VIEWER_SCENE_SCALE } from "cadjs/lib/viewer/sceneScale";
import { VIEWER_PICK_MODE } from "cadjs/lib/viewer/constants";
import { useStepAnimationSnapshot } from "@/workbench/stepAnimationStore";
import { viewerPickModeForRenderPane } from "@/workbench/viewerPickMode";

const EMPTY_LIST = Object.freeze([]);
const VIEWPORT_ISSUE_META = Object.freeze({
  error: {
    label: "Error",
    borderClassName: "border-destructive/45",
    iconClassName: "border-destructive/45 bg-destructive/10 text-destructive dark:text-red-300",
    labelClassName: "text-destructive dark:text-red-300"
  },
  warning: {
    label: "Warning",
    borderClassName: "border-amber-500/45",
    iconClassName: "border-amber-500/55 bg-amber-500/10 text-amber-500 dark:text-amber-300",
    labelClassName: "text-amber-500 dark:text-amber-300"
  }
});

function viewportInsetPx(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) && numericValue > 0 ? numericValue : 0;
}

function viewportIssueMetaForAlert(alert) {
  return alert?.severity === "warning"
    ? VIEWPORT_ISSUE_META.warning
    : VIEWPORT_ISSUE_META.error;
}

function viewerContextMenuAnchorStyle(menu, viewportFrameInsets) {
  if (!menu) {
    return null;
  }
  const margin = 8;
  const viewportWidth = typeof window !== "undefined" ? window.innerWidth : 0;
  const viewportHeight = typeof window !== "undefined" ? window.innerHeight : 0;
  const minX = viewportInsetPx(viewportFrameInsets?.left) + margin;
  const minY = viewportInsetPx(viewportFrameInsets?.top) + margin;
  const maxX = viewportWidth > 0
    ? Math.max(minX, viewportWidth - viewportInsetPx(viewportFrameInsets?.right) - margin)
    : Number(menu.x) || minX;
  const maxY = viewportHeight > 0
    ? Math.max(minY, viewportHeight - viewportInsetPx(viewportFrameInsets?.bottom) - margin)
    : Number(menu.y) || minY;
  const x = Math.min(Math.max(Number(menu.x) || minX, minX), maxX);
  const y = Math.min(Math.max(Number(menu.y) || minY, minY), maxY);
  return {
    position: "fixed",
    left: `${x}px`,
    top: `${y}px`,
    width: "1px",
    height: "1px"
  };
}

function ViewerContextMenu({
  menu,
  positionStyle,
  onClose,
  onCopyReference,
  onSelect,
  onFocus,
  onExitAllIsolate,
  onHideOther,
  onHideAll,
  onHide,
  onReveal,
  onExpandSelected,
  onCollapseSelected,
  onExpandAll,
  onCollapseAll
}) {
  if (!menu || !positionStyle) {
    return null;
  }

  const itemClassName = "text-xs";
  const handleAction = (action) => {
    action?.(menu);
    onClose?.();
  };
  const selected = menu.selected === true;
  const hidden = menu.hidden === true;
  const focused = menu.focused === true;

  return (
    <DropdownMenu
      open={true}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          onClose?.();
        }
      }}
    >
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          tabIndex={-1}
          aria-hidden="true"
          className="pointer-events-none fixed size-px opacity-0"
          style={positionStyle}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        side="bottom"
        sideOffset={4}
        className="w-44"
        onContextMenu={(event) => {
          event.preventDefault();
          event.stopPropagation();
        }}
      >
        <AssemblyContextMenuItems
          Item={DropdownMenuItem}
          Separator={DropdownMenuSeparator}
          itemClassName={itemClassName}
          selected={selected}
          isolated={focused}
          hidden={hidden}
          actionCount={menu.actionCount}
          copyReferenceDisabled={!String(menu.copyText || "").trim()}
          selectDisabled={menu.selectDisabled === true}
          showIsolate={menu.showIsolate !== false}
          isolateDisabled={menu.isolateDisabled === true}
          showExitAllIsolate={menu.showExitAllIsolate === true}
          exitAllIsolateDisabled={menu.exitAllIsolateDisabled === true}
          showHideOther={menu.showHideOther !== false}
          hideOtherDisabled={menu.hideOtherDisabled === true}
          showVisibility={menu.showVisibility !== false}
          showHideAll={menu.showHideAll === true}
          hideAllDisabled={menu.hideAllDisabled === true}
          hideAllLabel={String(menu.hideAllLabel || "").trim() || (hidden ? "Reveal all instances" : "Hide all instances")}
          visibilityDisabled={menu.visibilityDisabled === true}
          showExpandCollapse={menu.showExpandCollapse === true}
          expandSelectedDisabled={menu.expandSelectedDisabled !== false}
          collapseSelectedDisabled={menu.collapseSelectedDisabled !== false}
          expandAllDisabled={menu.expandAllDisabled !== false}
          collapseAllDisabled={menu.collapseAllDisabled !== false}
          onCopyReference={() => handleAction(onCopyReference)}
          onSelect={() => handleAction(onSelect)}
          onIsolate={() => handleAction(onFocus)}
          onExitAllIsolate={() => handleAction(onExitAllIsolate)}
          onHideOther={() => handleAction(onHideOther)}
          onHideAll={() => handleAction(onHideAll)}
          onToggleVisibility={() => handleAction(hidden ? onReveal : onHide)}
          onExpandSelected={() => handleAction(onExpandSelected)}
          onCollapseSelected={() => handleAction(onCollapseSelected)}
          onExpandAll={() => handleAction(onExpandAll)}
          onCollapseAll={() => handleAction(onCollapseAll)}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default function CadRenderPane({
  viewerRef,
  renderFormat,
  renderPartsIndividually = false,
  selectedMeshData,
  selectedDxfData,
  selectedDxfMeshData,
  selectedImplicitModel,
  implicitDynamicRenderActive = false,
  implicitGraphicsSettings = null,
  selectedKey,
  selectedDxfKey,
  missingFileRef = "",
  viewerPerspective,
  viewerPerspectiveRef,
  themeSettings,
  previewMode,
  viewportFrameInsets,
  viewerLoading,
  viewerAlert,
  stepUpdateInProgress,
  referenceSelectionPending = false,
  referenceSelectionUnavailable = false,
  referenceSelectionDeferred = false,
  viewPlaneOffsetRight = 16,
  viewerMode,
  assemblyParts,
  hiddenPartIds,
  selectedPartIds,
  hoveredPartId,
  assemblyMates = EMPTY_LIST,
  selectedMateIds = EMPTY_LIST,
  hoveredMateId = "",
  hoveredReferenceId,
  selectedReferenceIds,
  selectorRuntime,
  displayEdgeRuntime,
  stepParameters = null,
  pickableFaces,
  pickableEdges,
  pickableVertices,
  focusedPartIds = "",
  displaySettings = null,
  drawToolActive,
  drawingTool,
  drawingStrokes,
  handleDrawingStrokesChange,
  handlePerspectiveChange,
  handleModelHoverChange,
  handleModelReferenceActivate,
  handleModelReferenceDoubleActivate,
  handleModelReferenceContext,
  viewerContextMenu = null,
  onViewerContextMenuClose,
  onViewerContextMenuCopyReference,
  onViewerContextMenuSelect,
  onViewerContextMenuFocus,
  onViewerContextMenuExitAllIsolate,
  onViewerContextMenuHideOther,
  onViewerContextMenuHideAll,
  onViewerContextMenuHide,
  onViewerContextMenuReveal,
  onViewerContextMenuExpandSelected,
  onViewerContextMenuCollapseSelected,
  onViewerContextMenuExpandAll,
  onViewerContextMenuCollapseAll,
  handleViewerAlertChange,
  handleStepModuleTransformDetectedChange,
  selectionCount,
  copyButtonLabel,
  handleCopySelection,
  handleScreenshotCopy,
  urdfPosePicker = null
}) {
  const liveStepAnimation = useStepAnimationSnapshot();
  const resolvedStepParameters = useMemo(() => {
    if (!stepParameters?.animationState?.playing) {
      return stepParameters;
    }
    const liveParameterValues = liveStepAnimation?.parameterValues;
    if (!liveParameterValues || typeof liveParameterValues !== "object") {
      return stepParameters;
    }
    return {
      ...stepParameters,
      parameterValues: liveParameterValues,
      animationState: {
        ...stepParameters.animationState,
        elapsedSec: liveStepAnimation.elapsedSec
      }
    };
  }, [stepParameters, liveStepAnimation]);
  const viewerAlertIconLabel = "Viewer error. See the Issues section for details.";
  const dxfMode = renderFormat === RENDER_FORMAT.DXF;
  const gcodeMode = renderFormat === RENDER_FORMAT.GCODE;
  const urdfMode = isRobotRenderFormat(renderFormat);
  const implicitMode = renderFormat === RENDER_FORMAT.IMPLICIT;
  const meshOnlyMode = isMeshRenderFormat(renderFormat);
  const pathPreviewMode = meshOnlyMode || gcodeMode;
  const dxfMeshPreviewReady = dxfMode && !!selectedDxfMeshData;
  const activeMeshData = dxfMeshPreviewReady ? selectedDxfMeshData : selectedMeshData;
  const activeModelKey = dxfMeshPreviewReady ? (selectedDxfKey || selectedKey) : selectedKey;
  const missingFileLabel = String(missingFileRef || "").trim();
  const topologySelectionPending = Boolean(referenceSelectionPending && !dxfMode && !urdfMode && !pathPreviewMode);
  const topologySelectionUnavailable = Boolean(referenceSelectionUnavailable && !dxfMode && !urdfMode && !pathPreviewMode);
  const topologySelectionDeferred = Boolean(referenceSelectionDeferred && activeMeshData && !dxfMode && !urdfMode && !pathPreviewMode);
  const urdfPosePickerActive = Boolean(urdfPosePicker?.active);
  const urdfPosePickerPrompt = "Select target";
  const posePickerExitStyle = {
    left: `calc(${Math.max(Number(viewportFrameInsets?.left) || 0, 0)}px + 0.75rem)`,
    top: `calc(${Math.max(Number(viewportFrameInsets?.top) || 0, 0)}px + 0.75rem)`
  };
  const ctaMode = !dxfMode && !pathPreviewMode && drawToolActive
    ? "screenshot"
    : selectionCount > 0
      ? "selection"
      : "";
  const bottomOverlayStyle = {
    bottom: "1rem"
  };
  const modelViewportOverlayStyle = {
    left: `${viewportInsetPx(viewportFrameInsets?.left)}px`,
    right: `${viewportInsetPx(viewportFrameInsets?.right)}px`,
    top: `${viewportInsetPx(viewportFrameInsets?.top)}px`,
    bottom: `${viewportInsetPx(viewportFrameInsets?.bottom)}px`
  };
  const modelViewportBottomOverlayStyle = {
    left: `${viewportInsetPx(viewportFrameInsets?.left)}px`,
    right: `${viewportInsetPx(viewportFrameInsets?.right)}px`,
    bottom: `calc(${viewportInsetPx(viewportFrameInsets?.bottom)}px + 1rem)`
  };
  const ctaOverlayStyle = {
    ...bottomOverlayStyle,
    left: `calc(${viewportInsetPx(viewportFrameInsets?.left)}px + 1rem)`,
    right: `calc(${viewportInsetPx(viewportFrameInsets?.right)}px + 1rem)`
  };
  const ctaLabel = ctaMode === "screenshot" ? "Copy Screenshot" : copyButtonLabel;
  const ctaTitle = ctaMode === "screenshot" ? "Copy screenshot to clipboard" : copyButtonLabel;
  const ctaDisabled = ctaMode === "screenshot" ? viewerLoading || !activeMeshData : false;
  const viewportHasRenderableContent = implicitMode
    ? !!selectedImplicitModel
    : dxfMode && !dxfMeshPreviewReady
    ? !!selectedDxfData
    : !!activeMeshData;
  const blockingViewerAlert = viewerAlert && viewerAlert.blocking !== false && (
    viewerAlert.blocking ||
    viewerAlert.severity !== "warning" ||
    !viewportHasRenderableContent
  )
    ? viewerAlert
    : null;
  const viewportIssueMeta = viewportIssueMetaForAlert(blockingViewerAlert);
  const viewerContextMenuStyle = useMemo(
    () => viewerContextMenuAnchorStyle(viewerContextMenu, viewportFrameInsets),
    [viewerContextMenu, viewportFrameInsets]
  );

  useEffect(() => {
    if (!urdfPosePickerActive || typeof window === "undefined" || typeof document === "undefined") {
      return undefined;
    }
    const handleEscape = (event) => {
      if (event.defaultPrevented) {
        return;
      }
      if (event.key !== "Escape" && event.key !== "Esc" && event.code !== "Escape") {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      urdfPosePicker?.onCancel?.();
    };
    window.addEventListener("keydown", handleEscape, true);
    document.addEventListener("keydown", handleEscape, true);
    return () => {
      window.removeEventListener("keydown", handleEscape, true);
      document.removeEventListener("keydown", handleEscape, true);
    };
  }, [urdfPosePicker, urdfPosePickerActive]);

  return (
    <div className="absolute inset-0">
      {implicitMode ? (
        <ImplicitCadViewer
          key={`implicit:${activeModelKey}`}
          ref={viewerRef}
          model={selectedImplicitModel}
          modelKey={activeModelKey}
          isLoading={viewerLoading}
          previewMode={previewMode}
          viewportFrameInsets={viewportFrameInsets}
          viewPlaneOffsetRight={viewPlaneOffsetRight}
          themeSettings={themeSettings}
          graphicsSettings={implicitGraphicsSettings}
          dynamicRenderActive={implicitDynamicRenderActive}
          perspective={viewerPerspective}
          perspectiveRef={viewerPerspectiveRef}
          onPerspectiveChange={handlePerspectiveChange}
          onViewerAlertChange={handleViewerAlertChange}
        />
      ) : dxfMode && !dxfMeshPreviewReady ? (
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
          renderFormat={renderFormat}
          perspective={viewerPerspective}
          perspectiveRef={viewerPerspectiveRef}
          showEdges={!gcodeMode}
          recomputeNormals={false}
          themeSettings={themeSettings}
          displaySettings={dxfMode || pathPreviewMode ? null : displaySettings}
          previewMode={dxfMode ? false : previewMode}
          showViewPlane={dxfMode || gcodeMode ? true : !previewMode}
          scale={urdfMode ? VIEWER_SCENE_SCALE.URDF : VIEWER_SCENE_SCALE.CAD}
          viewPlaneOffsetRight={viewPlaneOffsetRight}
          viewPlaneOffsetBottom="1rem"
          compactViewPlane={false}
          viewportFrameInsets={viewportFrameInsets}
          isLoading={viewerLoading}
          pickMode={urdfMode
            ? VIEWER_PICK_MODE.NONE
            : viewerPickModeForRenderPane({
              dxfMode,
              pathPreviewMode,
              topologySelectionPending,
              topologySelectionUnavailable,
              topologySelectionDeferred,
              viewerMode,
              focusedPartIds
            })}
          renderPartsIndividually={urdfMode ? true : (renderPartsIndividually || Boolean(resolvedStepParameters?.definition))}
          pickableParts={dxfMode || urdfMode || pathPreviewMode ? EMPTY_LIST : assemblyParts}
          hiddenPartIds={dxfMode || pathPreviewMode ? [] : hiddenPartIds}
          selectedPartIds={dxfMode || pathPreviewMode ? [] : selectedPartIds}
          hoveredPartId={dxfMode || pathPreviewMode ? "" : hoveredPartId}
          assemblyMates={dxfMode || pathPreviewMode ? [] : assemblyMates}
          selectedMateIds={dxfMode || pathPreviewMode ? [] : selectedMateIds}
          hoveredMateId={dxfMode || pathPreviewMode ? "" : hoveredMateId}
          hoveredReferenceId={dxfMode || pathPreviewMode ? "" : hoveredReferenceId}
          selectedReferenceIds={dxfMode || pathPreviewMode ? [] : selectedReferenceIds}
          selectorRuntime={dxfMode || pathPreviewMode ? null : selectorRuntime}
          displayEdgeRuntime={dxfMode || pathPreviewMode ? null : displayEdgeRuntime}
          stepParameters={dxfMode || pathPreviewMode ? null : resolvedStepParameters}
          pickableFaces={dxfMode || pathPreviewMode ? [] : pickableFaces}
          pickableEdges={dxfMode || pathPreviewMode ? [] : pickableEdges}
          pickableVertices={dxfMode || pathPreviewMode ? [] : pickableVertices}
          focusedPartId={dxfMode || pathPreviewMode ? "" : focusedPartIds}
          drawingEnabled={!dxfMode && !pathPreviewMode && drawToolActive}
          drawingTool={drawingTool}
          drawingStrokes={dxfMode || pathPreviewMode ? [] : drawingStrokes}
          onDrawingStrokesChange={handleDrawingStrokesChange}
          onPerspectiveChange={handlePerspectiveChange}
          onHoverReferenceChange={handleModelHoverChange}
          onActivateReference={handleModelReferenceActivate}
          onDoubleActivateReference={handleModelReferenceDoubleActivate}
          onContextReference={handleModelReferenceContext}
          onViewerAlertChange={handleViewerAlertChange}
          onStepModuleTransformDetectedChange={handleStepModuleTransformDetectedChange}
          urdfPosePicker={urdfPosePicker}
        />
      )}
      {!previewMode ? (
        <ViewerContextMenu
          menu={viewerContextMenu}
          positionStyle={viewerContextMenuStyle}
          onClose={onViewerContextMenuClose}
          onCopyReference={onViewerContextMenuCopyReference}
          onSelect={onViewerContextMenuSelect}
          onFocus={onViewerContextMenuFocus}
          onExitAllIsolate={onViewerContextMenuExitAllIsolate}
          onHideOther={onViewerContextMenuHideOther}
          onHideAll={onViewerContextMenuHideAll}
          onHide={onViewerContextMenuHide}
          onReveal={onViewerContextMenuReveal}
          onExpandSelected={onViewerContextMenuExpandSelected}
          onCollapseSelected={onViewerContextMenuCollapseSelected}
          onExpandAll={onViewerContextMenuExpandAll}
          onCollapseAll={onViewerContextMenuCollapseAll}
        />
      ) : null}
      {!previewMode && missingFileLabel ? (
        <div
          className="pointer-events-none absolute z-30 flex min-w-0 items-center justify-center px-4 py-4"
          style={modelViewportOverlayStyle}
        >
          <Alert
            variant="destructive"
            className="cad-glass-popover pointer-events-auto w-full max-w-xl min-w-0 p-5 text-center shadow-lg"
          >
            <p className="col-start-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-destructive">
              File does not exist
            </p>
            <AlertTitle className="col-start-1 mt-1 line-clamp-none text-lg text-foreground">File does not exist</AlertTitle>
            <AlertDescription className="col-start-1 mt-1 text-sm leading-6 text-muted-foreground">
              <code className="rounded-md bg-muted px-2 py-1 text-xs text-foreground">{missingFileLabel}</code>
            </AlertDescription>
          </Alert>
        </div>
      ) : null}
      {!previewMode && blockingViewerAlert ? (
        <div
          className="pointer-events-none absolute z-30 flex min-w-0 items-center justify-center px-3 py-3 sm:px-4"
          style={modelViewportOverlayStyle}
        >
          <div
            role="alert"
            aria-label={viewerAlertIconLabel}
            title={viewerAlertIconLabel}
            className={cn(
              "cad-glass-popover pointer-events-auto flex w-full max-w-sm min-w-0 flex-col items-center gap-2 rounded-md border px-4 py-3 text-center shadow-md",
              viewportIssueMeta.borderClassName
            )}
          >
            <span className={cn(
              "flex size-9 shrink-0 items-center justify-center rounded-full border",
              viewportIssueMeta.iconClassName
            )}>
              <CircleAlert className="size-5" strokeWidth={2} aria-hidden="true" />
            </span>
            <div className="min-w-0 max-w-full">
              <span className={cn(
                "text-[10px] font-medium uppercase tracking-[0.08em]",
                viewportIssueMeta.labelClassName
              )}>
                {viewportIssueMeta.label}
              </span>
              <div className="mt-1 line-clamp-2 min-w-0 max-w-full break-words text-sm font-medium leading-5 text-foreground">
                {viewerAlert.title || viewerAlert.summary || "Viewer issue"}
              </div>
              {viewerAlert.message ? (
                <p className="mt-1 line-clamp-3 min-w-0 max-w-full break-words text-xs leading-5 text-muted-foreground">
                  {viewerAlert.message}
                </p>
              ) : null}
              {viewerAlert.resolution ? (
                <p className="mt-1 line-clamp-2 min-w-0 max-w-full break-words text-xs leading-5 text-muted-foreground">
                  {viewerAlert.resolution}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
      {!previewMode && stepUpdateInProgress ? (
        <div className="pointer-events-none absolute z-20 flex justify-center px-4" style={modelViewportBottomOverlayStyle}>
          <Alert
            role="status"
            className="cad-glass-popover w-auto px-3 py-1.5 text-[11px] font-medium text-popover-foreground shadow-sm"
          >
            STEP changed. Updating/regenerating references...
          </Alert>
        </div>
      ) : null}
      {!previewMode && !stepUpdateInProgress && topologySelectionPending ? (
        <div className="pointer-events-none absolute z-20 flex justify-center px-4" style={modelViewportBottomOverlayStyle}>
          <Alert
            role="status"
            className="cad-glass-popover w-auto px-3 py-1.5 text-[11px] font-medium text-popover-foreground shadow-sm"
          >
            Preparing selectable topology...
          </Alert>
        </div>
      ) : null}
      {!previewMode && urdfPosePickerActive ? (
        <Button
          type="button"
          variant="outline"
          size="icon-xs"
          className="cad-glass-popover pointer-events-auto absolute z-30 size-6 rounded-md border-sidebar-border p-0 text-popover-foreground shadow-sm"
          style={posePickerExitStyle}
          onClick={() => {
            urdfPosePicker?.onCancel?.();
          }}
          aria-label="Exit Select Pose"
          title="Exit Select Pose"
        >
          <X className="size-3.5" strokeWidth={2} aria-hidden="true" />
        </Button>
      ) : null}
      {!previewMode && urdfPosePickerActive ? (
        <div className="pointer-events-none absolute z-20 flex justify-center px-4" style={modelViewportBottomOverlayStyle}>
          <Alert
            role="status"
            className="cad-glass-popover w-auto px-3 py-1.5 text-[11px] font-medium text-popover-foreground shadow-sm"
          >
            {urdfPosePickerPrompt}
          </Alert>
        </div>
      ) : null}
      {!previewMode && ctaMode && !stepUpdateInProgress && !topologySelectionPending && !topologySelectionUnavailable && !topologySelectionDeferred ? (
        <div
          className="pointer-events-none absolute z-20 flex min-w-0 justify-center"
          style={ctaOverlayStyle}
        >
          <Button
            type="button"
            variant="default"
            size="sm"
            className="pointer-events-auto h-9 w-fit min-w-0 max-w-[min(28rem,100%)] shrink overflow-hidden border border-primary/20 bg-primary/85 px-4 text-[12px] font-semibold text-primary-foreground shadow-lg shadow-black/20 hover:bg-primary/75 focus-visible:ring-primary/35 max-sm:w-full"
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
            <span className="block min-w-0 max-w-full truncate">{ctaLabel}</span>
          </Button>
        </div>
      ) : null}
    </div>
  );
}

import { useEffect, useMemo } from "react";
import CadViewer from "../CadViewer";
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
import TutorialTip from "./TutorialTip";
import { cn } from "@/ui/utils";
import { RENDER_FORMAT } from "@/workbench/constants";
import { TUTORIAL_TIP_IDS } from "@/workbench/persistence";
import {
  PARAMETER_SOURCE,
  renderCapabilities,
  supportsTool,
  viewportContentKind,
  VIEWPORT_CONTENT
} from "cadjs/lib/renderCapabilities";
import {
  CAMERA_PROJECTION,
  normalizeCameraProjection
} from "cadjs/lib/displaySettings";
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
  onResetZoom,
  onZoomToFit,
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
        {menu.global === true ? (
          <>
            {menu.showShowAll === true ? (
              <DropdownMenuItem
                className={itemClassName}
                onSelect={() => handleAction(onHideAll)}
              >
                Show all
              </DropdownMenuItem>
            ) : null}
            {menu.showShowAll === true && menu.showCameraActions !== false ? (
              <DropdownMenuSeparator />
            ) : null}
            {menu.showCameraActions !== false ? (
              <>
                <DropdownMenuItem
                  className={itemClassName}
                  disabled={menu.resetZoomDisabled === true}
                  onSelect={() => handleAction(onResetZoom)}
                >
                  Reset Zoom
                </DropdownMenuItem>
                <DropdownMenuItem
                  className={itemClassName}
                  disabled={menu.zoomToFitDisabled === true}
                  onSelect={() => handleAction(onZoomToFit)}
                >
                  Zoom To Fit
                </DropdownMenuItem>
              </>
            ) : null}
            {menu.showCameraActions !== false && menu.showExpandCollapse === true ? (
              <DropdownMenuSeparator />
            ) : null}
            {menu.showShowAll === true && menu.showCameraActions === false && menu.showExpandCollapse === true ? (
              <DropdownMenuSeparator />
            ) : null}
            {menu.showExpandCollapse === true ? (
              <>
                <DropdownMenuItem
                  className={itemClassName}
                  disabled={menu.expandAllDisabled === true}
                  onSelect={() => handleAction(onExpandAll)}
                >
                  Expand all
                </DropdownMenuItem>
                <DropdownMenuItem
                  className={itemClassName}
                  disabled={menu.collapseAllDisabled === true}
                  onSelect={() => handleAction(onCollapseAll)}
                >
                  Collapse all
                </DropdownMenuItem>
              </>
            ) : null}
          </>
        ) : (
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
            hideAllLabel={String(menu.hideAllLabel || "").trim() || "Show all"}
            visibilityDisabled={menu.visibilityDisabled === true}
            showCameraActions={menu.showCameraActions !== false}
            resetZoomDisabled={menu.resetZoomDisabled === true}
            zoomToFitDisabled={menu.zoomToFitDisabled === true}
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
            onResetZoom={() => handleAction(onResetZoom)}
            onZoomToFit={() => handleAction(onZoomToFit)}
            onExpandSelected={() => handleAction(onExpandSelected)}
            onCollapseSelected={() => handleAction(onCollapseSelected)}
            onExpandAll={() => handleAction(onExpandAll)}
            onCollapseAll={() => handleAction(onCollapseAll)}
          />
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default function CadRenderPane({
  viewerRef,
  renderFormat,
  renderPartsIndividually = false,
  selectedMeshData,
  selectedImplicitModel,
  implicitDynamicRenderActive = false,
  implicitGraphicsSettings = null,
  selectedKey,
  missingFileRef = "",
  viewerServerInfo = null,
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
  drawingThicknessScale = 1,
  planMode = false,
  bendAxisX = null,
  drawingBendLines = null,
  bendAnglesRad = null,
  drawingBends = null,
  drawingBendStyle = "boxed",
  drawingBendRadiusMm = 0,
  drawingKFactor = 0.5,
  drawingHiddenLayers = null,
  drawingOrientation = null,
  drawingMaterialColor = null,
  drawingGeometry = null,
  drawingThicknessMm = 0,
  onCameraZoomPercentChange = null,
  viewPlaneOffsetRight = 16,
  viewerMode,
  assemblyPickingActive = false,
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
  boundsAnimationActive = false,
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
  onViewerContextMenuResetZoom,
  onViewerContextMenuZoomToFit,
  onViewerContextMenuExpandSelected,
  onViewerContextMenuCollapseSelected,
  onViewerContextMenuExpandAll,
  onViewerContextMenuCollapseAll,
  handleViewerAlertChange,
  handleStepModuleTransformDetectedChange,
  selectionCount,
  copyButtonLabel,
  copyReferenceTipActive = false,
  panToolActive = false,
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
  // One capability lookup replaces the per-format mode booleans. Every gate below asks
  // what this format CAN do; none of them ask what it IS.
  const capabilities = renderCapabilities(renderFormat);
  const implicitMode = viewportContentKind(renderFormat) === VIEWPORT_CONTENT.IMPLICIT;
  const drawEnabled = supportsTool(renderFormat, "draw");
  // Formats with no per-part topology to select, annotate or explode: a plain mesh has
  // no parts, and an implicit is a single SDF body. Both hand the viewer the same
  // stripped-down prop set.
  const hasParts = capabilities.parts;
  const hasTopology = capabilities.topology;
  const displaySettingsActive = capabilities.displayModes && !!displaySettings;
  // Projection is a THEME trait, honoured by every format that declares it — not a
  // STEP privilege. Leaving the others pinned to perspective meant the default
  // workbench theme (which is orthographic) was being ignored by four formats out of
  // five. A plan view additionally forces orthographic: a top-down lock still
  // foreshortens off-centre under perspective, which is exactly what a plan view must
  // not do.
  const cadProjection = planMode
    ? CAMERA_PROJECTION.ORTHOGRAPHIC
    : capabilities.themeProjection
      ? normalizeCameraProjection(themeSettings?.projection)
      : CAMERA_PROJECTION.PERSPECTIVE;
  const stepBoundsAnimationActive = Boolean(resolvedStepParameters?.animationState?.playing);
  const cadViewerBoundsAnimationActive = Boolean(boundsAnimationActive || stepBoundsAnimationActive);
  const missingFileLabel = String(missingFileRef || "").trim();
  // A Viewer resolves paths against ITS OWN served root. Point one at an
  // absolute path belonging to a different checkout — easy to do when an
  // instance from another clone is already holding the default port — and the
  // file is simply not found. Reporting that as "file does not exist" blames
  // the model and sends you looking for a build problem that isn't there, so
  // say which of the two it actually is.
  const servedRoot = String(
    viewerServerInfo?.rootPath || viewerServerInfo?.directoryRoot || ""
  ).trim();
  const missingFileOutsideRoot = Boolean(
    missingFileLabel
    && servedRoot
    && missingFileLabel.startsWith("/")
    && !missingFileLabel.startsWith(servedRoot.endsWith("/") ? servedRoot : `${servedRoot}/`)
  );
  const topologySelectionPending = Boolean(referenceSelectionPending && hasTopology);
  const topologySelectionUnavailable = Boolean(referenceSelectionUnavailable && hasTopology);
  const topologySelectionDeferred = Boolean(referenceSelectionDeferred && selectedMeshData && hasTopology);
  const urdfPosePickerActive = Boolean(urdfPosePicker?.active);
  const urdfPosePickerPrompt = "Select target";
  const posePickerExitStyle = {
    left: `calc(${Math.max(Number(viewportFrameInsets?.left) || 0, 0)}px + 0.75rem)`,
    top: `calc(${Math.max(Number(viewportFrameInsets?.top) || 0, 0)}px + 0.75rem)`
  };
  // Is there anything on screen? For every mesh-backed format that means mesh data -- DXF
  // included, since it lost its 2D fallback in phase 3a and now renders its baked preview,
  // so a failed build must read as "nothing renderable" and let the viewer alert block.
  // An IMPLICIT renders by raymarching its own GLSL and never has mesh data, so asking the
  // same question of it would treat every healthy implicit as an empty viewport; its content
  // is the loaded model instead.
  const viewportHasRenderableContent = implicitMode ? !!selectedImplicitModel : !!selectedMeshData;
  const ctaMode = drawEnabled && drawToolActive
    ? "screenshot"
    : (hasParts || hasTopology) && selectionCount > 0
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
  const ctaDisabled = ctaMode === "screenshot"
    ? viewerLoading || !viewportHasRenderableContent
    : false;
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
      <CadViewer
        ref={viewerRef}
        meshData={selectedMeshData}
        implicitModel={implicitMode ? selectedImplicitModel : null}
        implicitGraphicsSettings={implicitMode ? implicitGraphicsSettings : null}
        implicitDynamicRenderActive={implicitMode ? implicitDynamicRenderActive : false}
        modelKey={selectedKey}
        renderFormat={renderFormat}
        drawingThicknessScale={drawingThicknessScale}
        planMode={planMode}
        bendAxisX={bendAxisX}
        drawingBendLines={drawingBendLines}
        bendAnglesRad={bendAnglesRad}
        drawingBends={drawingBends}
        drawingBendStyle={drawingBendStyle}
        drawingBendRadiusMm={drawingBendRadiusMm}
        drawingKFactor={drawingKFactor}
        drawingHiddenLayers={drawingHiddenLayers}
        drawingOrientation={drawingOrientation}
        drawingMaterialColor={drawingMaterialColor}
        drawingGeometry={drawingGeometry}
        drawingThicknessMm={drawingThicknessMm}
        onCameraZoomPercentChange={onCameraZoomPercentChange}
        perspective={viewerPerspective}
        projection={cadProjection}
        perspectiveRef={viewerPerspectiveRef}
        showEdges
        recomputeNormals={false}
        themeSettings={themeSettings}
        displaySettings={displaySettingsActive ? displaySettings : null}
        previewMode={previewMode}
        showViewPlane={!previewMode}
        scale={capabilities.sceneScale === "urdf" ? VIEWER_SCENE_SCALE.URDF : VIEWER_SCENE_SCALE.CAD}
        viewPlaneOffsetRight={viewPlaneOffsetRight}
        viewPlaneOffsetBottom="1rem"
        compactViewPlane={false}
        viewportFrameInsets={viewportFrameInsets}
        isLoading={viewerLoading}
        pickMode={!hasTopology && !hasParts
          ? VIEWER_PICK_MODE.NONE
          : viewerPickModeForRenderPane({
            panToolActive,
            topologySelectionPending,
            topologySelectionUnavailable,
            topologySelectionDeferred,
            topologyPickingActive: Boolean(
              pickableFaces?.length ||
              pickableEdges?.length ||
              pickableVertices?.length
            ),
            viewerMode,
            assemblyPickingActive,
            focusedPartIds
          })}
        panToolActive={panToolActive}
        renderPartsIndividually={capabilities.sceneScale === "urdf"
          ? true
          : (renderPartsIndividually || Boolean(resolvedStepParameters?.definition))}
        pickableParts={hasParts ? assemblyParts : EMPTY_LIST}
        hiddenPartIds={hasParts ? hiddenPartIds : []}
        selectedPartIds={hasParts ? selectedPartIds : []}
        hoveredPartId={hasParts ? hoveredPartId : ""}
        assemblyMates={hasParts ? assemblyMates : []}
        selectedMateIds={hasParts ? selectedMateIds : []}
        hoveredMateId={hasParts ? hoveredMateId : ""}
        hoveredReferenceId={hasTopology ? hoveredReferenceId : ""}
        selectedReferenceIds={hasTopology ? selectedReferenceIds : []}
        selectorRuntime={hasTopology ? selectorRuntime : null}
        displayEdgeRuntime={hasTopology ? displayEdgeRuntime : null}
        stepParameters={capabilities.params === PARAMETER_SOURCE.SIDECAR ? resolvedStepParameters : null}
        pickableFaces={hasTopology ? pickableFaces : []}
        pickableEdges={hasTopology ? pickableEdges : []}
        pickableVertices={hasTopology ? pickableVertices : []}
        focusedPartId={hasParts ? focusedPartIds : ""}
        boundsAnimationActive={cadViewerBoundsAnimationActive}
        drawingEnabled={drawEnabled && drawToolActive}
        drawingTool={drawingTool}
        drawingStrokes={drawEnabled ? drawingStrokes : []}
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
          onResetZoom={onViewerContextMenuResetZoom}
          onZoomToFit={onViewerContextMenuZoomToFit}
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
            className="cad-glass-popover pointer-events-auto w-full max-w-xl min-w-0 p-4 text-center shadow-lg"
          >
            <p className="col-start-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-destructive">
              {missingFileOutsideRoot ? "Outside this viewer's root" : "File does not exist"}
            </p>
            <AlertTitle className="col-start-1 mt-1 line-clamp-none text-lg text-foreground">
              {missingFileOutsideRoot ? "Outside this viewer's root" : "File does not exist"}
            </AlertTitle>
            <AlertDescription className="col-start-1 mt-1 text-sm leading-6 text-muted-foreground">
              <code className="rounded-md bg-muted px-2 py-1 text-xs text-foreground">{missingFileLabel}</code>
              {missingFileOutsideRoot ? (
                <span className="mt-2 block text-xs leading-5">
                  This viewer serves{" "}
                  <code className="rounded bg-muted px-1 py-0.5 text-foreground">{servedRoot}</code>.
                  The path above is outside it — most likely a viewer from another
                  checkout is holding this port. Start one for this workspace on a
                  free port instead.
                </span>
              ) : null}
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
          <TutorialTip
            tipId={TUTORIAL_TIP_IDS.COPY_REFERENCE}
            active={ctaMode !== "screenshot" && copyReferenceTipActive}
            side="top"
            align="center"
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
          </TutorialTip>
        </div>
      ) : null}
    </div>
  );
}

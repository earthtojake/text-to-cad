import { useHostReference } from "../../file-view/hostReference.js";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import CadViewer from "../CadViewer.js";
import { CircleAlert, X } from "lucide-react";
import MissingFileAlert from "./MissingFileAlert.js";
import { Alert } from "@hardcore/ui/primitives/alert";
import { Button } from "@hardcore/ui/primitives/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from "@hardcore/ui/primitives/dropdown-menu";
import AssemblyContextMenuItems from "./AssemblyContextMenuItems.js";
import TutorialTip from "./TutorialTip.jsx";
import { cn } from "@hardcore/ui/utils";
import { RENDER_FORMAT } from "../../workbench/constants.js";
import { TUTORIAL_TIP_IDS } from "../../workbench/tutorialTips.js";
import {
  PARAMETER_SOURCE,
  renderCapabilities,
  supportsTool
} from "@hardcore/core/lib/renderCapabilities.js";
import {
  CAMERA_PROJECTION,
  normalizeCameraProjection
} from "@hardcore/core/lib/displaySettings.js";
import { VIEWER_SCENE_SCALE } from "@hardcore/core/lib/viewer/sceneScale.js";
import { VIEWER_PICK_MODE } from "@hardcore/core/lib/viewer/constants.js";
import { useAnimationClock } from "../../workbench/animationClockStore.js";
import { viewerPickModeForRenderPane } from "../../workbench/viewerPickMode.js";

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

function viewportIssueMetaForAlert(alert) {
  return alert?.severity === "warning"
    ? VIEWPORT_ISSUE_META.warning
    : VIEWPORT_ISSUE_META.error;
}

// The menu anchors at the pointer, in window coordinates, kept a margin in
// from the window's edges so the menu has somewhere to open.
function viewerContextMenuAnchorStyle(menu) {
  if (!menu) {
    return null;
  }
  const margin = 8;
  const viewportWidth = typeof window !== "undefined" ? window.innerWidth : 0;
  const viewportHeight = typeof window !== "undefined" ? window.innerHeight : 0;
  const minX = margin;
  const minY = margin;
  const maxX = viewportWidth > 0
    ? Math.max(minX, viewportWidth - margin)
    : Number(menu.x) || minX;
  const maxY = viewportHeight > 0
    ? Math.max(minY, viewportHeight - margin)
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
  const hostReference = useHostReference();
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
            onAddToPrompt={hostReference ? () => handleAction((item) => hostReference.addReference(item.copyText)) : undefined}
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

// Width and typography shared by the copy button and the hidden ruler that decides whether
// its label fits. One constant so the two cannot drift apart.
const CTA_METRICS_CLASS = "h-9 w-fit min-w-0 max-w-full sm:max-w-[min(28rem,calc(100%-16rem))] shrink overflow-hidden px-4 text-xs max-sm:w-full max-sm:pr-32";

export default function CadRenderPane({
  viewerRef,
  renderFormat,
  renderPartsIndividually = false,
  selectedMeshData,
  selectedKey,
  missingFileRef = "",
  viewerServerInfo = null,
  viewerPerspective,
  viewerPerspectiveRef,
  themeSettings,
  previewMode,
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
  drawingIsDocument = false,
  drawingThicknessMm = 0,
  onCameraZoomPercentChange = null,
  viewerMode,
  assemblyPickingActive = false,
  assemblyParts,
  hiddenPartIds,
  selectedPartIds,
  hoveredPartId,
  hoveredReferenceId,
  selectedReferenceIds,
  selectorRuntime,
  displayEdgeRuntime,
  stepParameters = null,
  stepAnimation = null,
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
  onMeasurePick,
  onMeasureHoverPoint,
  activeMeasurementId = "",
  measureState = null,
  measureModeActive = false,
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
  copyButtonCountLabel = "",
  copyReferenceTipActive = false,
  selectionFilter = "all",
  panToolActive = false,
  handleCopySelection,
  handleAddSelection = null,
  handleScreenshotCopy,
}) {
  // The clock is the ONE thing that changes per frame during playback, and this
  // is the only component that re-renders for it: subscribing here (rather than
  // in the workspace) keeps a playing clip off the workspace's render path.
  const liveAnimationElapsedSec = useAnimationClock();
  const resolvedStepAnimation = useMemo(() => {
    if (!stepAnimation?.playing) {
      return stepAnimation;
    }
    return { ...stepAnimation, elapsedSec: liveAnimationElapsedSec };
  }, [stepAnimation, liveAnimationElapsedSec]);
  const viewerAlertIconLabel = "Viewer error. See the Issues section for details.";
  // One capability lookup replaces the per-format mode booleans. Every gate below asks
  // what this format CAN do; none of them ask what it IS.
  const capabilities = renderCapabilities(renderFormat);
  const drawEnabled = supportsTool(renderFormat, "draw");
  // Formats with no per-part topology to select, annotate or explode: a plain mesh has
  // no parts, so it gets the stripped-down prop set.
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
  const cadViewerBoundsAnimationActive = Boolean(
    boundsAnimationActive || resolvedStepAnimation?.playing
  );
  const topologySelectionPending = Boolean(referenceSelectionPending && hasTopology);
  const topologySelectionUnavailable = Boolean(referenceSelectionUnavailable && hasTopology);
  const topologySelectionDeferred = Boolean(referenceSelectionDeferred && selectedMeshData && hasTopology);
  // Is there anything on screen? For every mesh-backed format that means mesh data -- DXF
  // included, since it lost its 2D fallback in phase 3a and now renders its baked preview,
  // so a failed build must read as "nothing renderable" and let the viewer alert block.
  const viewportHasRenderableContent = !!selectedMeshData;
  const ctaMode = drawEnabled && drawToolActive
    ? "screenshot"
    : (hasParts || hasTopology) && selectionCount > 0
      ? "selection"
      : "";
  // A ref cut off mid-token reads like a broken ref rather than a long one, so when it does
  // not fit we show the count instead. Whether it fits depends on the viewport, not the
  // string, so it is measured rather than guessed from a length threshold.
  //
  // The measurement reads a hidden copy holding the FULL label. Measuring the visible span
  // would oscillate: swapping in the shorter count label makes it fit again, which would swap
  // the ref back in, and so on.
  const ctaFullLabelRef = useRef(null);
  const [ctaLabelFits, setCtaLabelFits] = useState(true);
  const ctaMetricsClass = handleAddSelection ? "h-9 w-fit min-w-0 max-w-full shrink overflow-hidden px-4 text-xs" : CTA_METRICS_CLASS;
  const ctaRefLabel = ctaMode === "screenshot" ? "Copy Screenshot" : handleAddSelection ? "Add to prompt" : copyButtonLabel;
  useLayoutEffect(() => {
    const ruler = ctaFullLabelRef.current;
    if (!ruler) {
      return undefined;
    }
    const measure = () => {
      // +1 so sub-pixel rounding does not read as an overflow.
      setCtaLabelFits(ruler.scrollWidth <= ruler.clientWidth + 1);
    };
    measure();
    // Belt and braces. ResizeObserver is the precise signal, but it is not always delivered
    // promptly when the document is not being painted, and a window resize is the case that
    // actually changes the answer.
    window.addEventListener("resize", measure);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(ruler);
    return () => {
      window.removeEventListener("resize", measure);
      observer?.disconnect();
    };
  }, [ctaRefLabel]);
  const ctaLabel = handleAddSelection || ctaLabelFits || !copyButtonCountLabel || ctaMode === "screenshot"
    ? ctaRefLabel
    : copyButtonCountLabel;
  // The title always carries the full ref, so the truncated case is still discoverable.
  const ctaTitle = ctaMode === "screenshot" ? "Copy screenshot to clipboard" : ctaRefLabel;
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
    () => viewerContextMenuAnchorStyle(viewerContextMenu),
    [viewerContextMenu]
  );


  return (
    <div className="absolute inset-0">
      <CadViewer
        ref={viewerRef}
        meshData={selectedMeshData}
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
        drawingIsDocument={drawingIsDocument}
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
        viewPlaneOffsetBottom="1rem"
        compactViewPlane={false}
        isLoading={viewerLoading}
        pickMode={!hasTopology && !hasParts && !measureModeActive
          ? VIEWER_PICK_MODE.NONE
          : viewerPickModeForRenderPane({
            selectionFilter,
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
            focusedPartIds,
            measureMode: measureModeActive
          })}
        panToolActive={panToolActive}
        renderPartsIndividually={capabilities.sceneScale === "urdf"
          ? true
          : (renderPartsIndividually
            || Boolean(stepParameters?.definition)
            || Boolean(resolvedStepAnimation?.clip))}
        pickableParts={hasParts ? assemblyParts : EMPTY_LIST}
        hiddenPartIds={hasParts ? hiddenPartIds : []}
        selectedPartIds={hasParts ? selectedPartIds : []}
        hoveredPartId={hasParts ? hoveredPartId : ""}
        hoveredReferenceId={hasTopology ? hoveredReferenceId : ""}
        selectedReferenceIds={hasTopology ? selectedReferenceIds : []}
        selectorRuntime={hasTopology ? selectorRuntime : null}
        displayEdgeRuntime={hasTopology ? displayEdgeRuntime : null}
        stepParameters={capabilities.params === PARAMETER_SOURCE.SIDECAR ? stepParameters : null}
        stepAnimation={capabilities.params === PARAMETER_SOURCE.SIDECAR ? resolvedStepAnimation : null}
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
        onMeasurePick={onMeasurePick}
        onMeasureHoverPoint={onMeasureHoverPoint}
        activeMeasurementId={activeMeasurementId}
        measureState={measureState}
        measureModeActive={measureModeActive}
        allowMeshVertexSnap={!hasTopology}
        onViewerAlertChange={handleViewerAlertChange}
        onStepModuleTransformDetectedChange={handleStepModuleTransformDetectedChange}
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
      <MissingFileAlert missingFileRef={missingFileRef} rootPath={viewerServerInfo?.rootPath} previewMode={previewMode} />
      {!previewMode && blockingViewerAlert ? (
        <div className="pointer-events-none absolute inset-0 z-30 flex min-w-0 items-center justify-center px-3 py-3 sm:px-4">
          <div
            role="alert"
            aria-label={viewerAlertIconLabel}
            title={viewerAlertIconLabel}
            className={cn(
              "bg-popover pointer-events-auto flex w-full max-w-sm min-w-0 flex-col items-center gap-2 rounded-md border px-4 py-3 text-center shadow-md",
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
                "text-micro uppercase tracking-[0.08em]",
                viewportIssueMeta.labelClassName
              )}>
                {viewportIssueMeta.label}
              </span>
              <div className="mt-1 line-clamp-2 min-w-0 max-w-full break-words text-sm leading-5 text-foreground">
                {viewerAlert.title || viewerAlert.summary || "Viewer issue"}
              </div>
              {viewerAlert.message ? (
                <p className="mt-1 line-clamp-3 min-w-0 max-w-full break-words text-xs leading-5 text-muted-foreground">
                  {viewerAlert.message}
                </p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
      {!previewMode && stepUpdateInProgress ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-4 z-20 flex justify-center px-4">
          <Alert
            role="status"
            className="bg-popover w-auto px-3 py-1.5 text-tiny text-popover-foreground shadow-sm"
          >
            STEP changed. Updating/regenerating references...
          </Alert>
        </div>
      ) : null}
      {!previewMode && !stepUpdateInProgress && topologySelectionPending ? (
        <div className="pointer-events-none absolute inset-x-0 bottom-4 z-20 flex justify-center px-4">
          <Alert
            role="status"
            className="bg-popover w-auto px-3 py-1.5 text-tiny text-popover-foreground shadow-sm"
          >
            Preparing selectable topology...
          </Alert>
        </div>
      ) : null}
      {!previewMode && ctaMode && !stepUpdateInProgress && !topologySelectionPending && !topologySelectionUnavailable && !topologySelectionDeferred ? (
        <div className={cn("pointer-events-none absolute inset-x-4 z-20 flex min-w-0 justify-center", handleAddSelection ? "bottom-36" : "bottom-4")}>
          {/* A hidden ruler carrying the FULL ref label under the same width constraints as
              the button. Measured to decide whether the button can show the ref at all.
              Deliberately independent of what the button currently displays: measuring the
              visible label instead would latch, because swapping in the shorter count label
              shrinks the box and makes the ref look permanently too wide. Kept outside the
              button so the button's textContent stays exactly its label. */}
          <span aria-hidden="true" className={cn("pointer-events-none invisible absolute left-0 top-0", ctaMetricsClass)}>
            <span ref={ctaFullLabelRef} className="block min-w-0 max-w-full truncate">{ctaRefLabel}</span>
          </span>
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
              className={cn(
                "pointer-events-auto border border-primary/20 bg-primary/85 text-primary-foreground shadow-lg shadow-black/20 hover:bg-primary/75 focus-visible:ring-primary/35",
                ctaMetricsClass
              )}
              disabled={ctaDisabled}
              onClick={() => {
                if (ctaMode === "screenshot") {
                  void handleScreenshotCopy?.();
                  return;
                }
                if (handleAddSelection) handleAddSelection();
                else void handleCopySelection();
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

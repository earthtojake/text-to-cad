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
import { PromptContextAction } from "../../../../host/PromptContextAction.js";
import ViewerAlertBody from "./ViewerAlertBody.js";
import { cn } from "@hardcore/ui/utils";
import { RENDER_FORMAT } from "../../workbench/constants.js";
import {
  PARAMETER_SOURCE,
  VIEWPORT_CONTENT,
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
import { useEmbeddedGlbAnimationClock } from "../../workbench/embeddedGlbAnimationClockStore.js";
import { viewerHiddenPartIdsForRenderPane, viewerPickModeForRenderPane, viewerSelectedPartIdsForRenderPane, viewerSelectorRuntimeForRenderPane } from "../../workbench/viewerPickMode.js";
import { viewerBendGuidesForRenderPane } from "../../workbench/renderPaneDrawing.js";

const EMPTY_LIST = Object.freeze([]);
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
            onAddToPrompt={hostReference?.canAddToPrompt ? () => handleAction((item) => hostReference.addReference(item.copyText)) : undefined}
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
  onReload,
  viewerRef,
  renderFormat,
  renderPartsIndividually = false,
  selectedMeshData,
  selectedKey,
  missingFileRef = "",
  viewerServerInfo = null,
  viewerPerspective,
  viewerPerspectiveRef,
  projection = CAMERA_PROJECTION.ORTHOGRAPHIC,
  focalLength = null,
  themeSettings,
  materialOverrides = null,
  receiveShadows = false,
  renderMode = false,
  appearance = "light",
  renderConfiguration = null,
  quality = null,
  previewMode,
  viewerLoading,
  retainingPreviousStepMesh = false,
  viewerAlert,
  presentationKey,
  onPresentationChange,
  loadingPresentation,
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
  onLodCameraChange = null,
  onMeshSourceAdoption = null,
  viewerMode,
  assemblyPickingActive = false,
  robotComponentPicking = false,
  assemblyParts,
  hiddenPartIds,
  selectedPartIds,
  materialPickingEnabled = false,
  onMaterialPartActivate,
  hoveredPartId,
  hoveredReferenceId,
  selectedReferenceIds,
  selectorRuntime,
  displayEdgeRuntime,
  stepParameters = null,
  stepAnimation = null,
  glbDocument = null,
  embeddedGlbAnimation = null,
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
  selectionFilter = "all",
  panToolActive = false,
  handleCopySelection,
  createPromptContext,
  onPromptResult,
  composerDestination = false,
  selectionExtras = null,
  handleScreenshotCopy,
}) {
  // The clock is the ONE thing that changes per frame during playback, and this
  // is the only component that re-renders for it: subscribing here (rather than
  // in the workspace) keeps a playing clip off the workspace's render path.
  const liveAnimationElapsedSec = useAnimationClock();
  const liveEmbeddedGlbElapsedSec = useEmbeddedGlbAnimationClock();
  const resolvedStepAnimation = useMemo(() => {
    if (!stepAnimation?.playing) {
      return stepAnimation;
    }
    return { ...stepAnimation, elapsedSec: liveAnimationElapsedSec };
  }, [stepAnimation, liveAnimationElapsedSec]);
  const resolvedEmbeddedGlbAnimation = useMemo(() => {
    if (!embeddedGlbAnimation?.playing) return embeddedGlbAnimation;
    return { ...embeddedGlbAnimation, elapsedSec: liveEmbeddedGlbElapsedSec };
  }, [embeddedGlbAnimation, liveEmbeddedGlbElapsedSec]);
  // One capability lookup replaces the per-format mode booleans. Every gate below asks
  // what this format CAN do; none of them ask what it IS.
  const capabilities = renderCapabilities(renderFormat);
  const drawEnabled = supportsTool(renderFormat, "draw");
  // Formats with no per-part topology to select, annotate or explode: a plain mesh has
  // no parts, so it gets the stripped-down prop set.
  const hasParts = capabilities.parts || (capabilities.content === VIEWPORT_CONTENT.ROBOT && robotComponentPicking);
  const hasTopology = capabilities.topology;
  const inspectionEnabled = !renderMode;
  const drawingGuides = viewerBendGuidesForRenderPane({ renderMode, bendAxisX, drawingBendLines });
  const effectivePlanMode = inspectionEnabled && planMode;
  // Render supplies one clean presentation display state to every format,
  // including plain meshes whose Inspect mode has no display-mode panel.
  const displaySettingsActive = (renderMode || capabilities.displayModes) && !!displaySettings;
  // A plan view additionally forces orthographic: a top-down lock still
  // foreshortens off-centre under perspective, which is exactly what a plan view must
  // not do. Every other format receives projection from the resolved scene camera.
  const cadProjection = effectivePlanMode
    ? CAMERA_PROJECTION.ORTHOGRAPHIC
    : normalizeCameraProjection(projection, CAMERA_PROJECTION.ORTHOGRAPHIC);
  const cadViewerBoundsAnimationActive = Boolean(
    boundsAnimationActive || resolvedStepAnimation?.playing || resolvedEmbeddedGlbAnimation?.playing
  );
  const topologySelectionPending = Boolean(referenceSelectionPending && hasTopology);
  const topologySelectionUnavailable = Boolean(referenceSelectionUnavailable && hasTopology);
  const topologySelectionDeferred = Boolean(referenceSelectionDeferred && selectedMeshData && hasTopology);
  // Is there anything on screen? For every mesh-backed format that means mesh data -- DXF
  // included, since it lost its 2D fallback in phase 3a and now renders its baked preview,
  // so a failed build must read as "nothing renderable" and let the viewer alert block.
  const viewportHasRenderableContent = !!selectedMeshData;
  const ctaMode = inspectionEnabled && drawEnabled && drawToolActive
    ? "screenshot"
    : inspectionEnabled && (hasParts || hasTopology) && selectionCount > 0
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
  const ctaMetricsClass = composerDestination ? "h-9 w-fit min-w-0 max-w-full shrink overflow-hidden px-4 text-xs" : CTA_METRICS_CLASS;
  const ctaRefLabel = ctaMode === "screenshot" ? "Copy Screenshot" : composerDestination ? "Add to prompt" : copyButtonLabel;
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
  const ctaLabel = composerDestination || ctaLabelFits || !copyButtonCountLabel || ctaMode === "screenshot"
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
        presentationKey={presentationKey}
        onPresentationChange={onPresentationChange}
        loadingPresentation={loadingPresentation}
        renderFormat={renderFormat}
        drawingThicknessScale={drawingThicknessScale}
        planMode={effectivePlanMode}
        bendAxisX={drawingGuides.bendAxisX}
        drawingBendLines={drawingGuides.drawingBendLines}
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
        onLodCameraChange={onLodCameraChange}
        onMeshSourceAdoption={onMeshSourceAdoption}
        perspective={viewerPerspective}
        projection={cadProjection}
        focalLength={focalLength}
        perspectiveRef={viewerPerspectiveRef}
        showEdges
        recomputeNormals={false}
        themeSettings={themeSettings}
        appearance={appearance}
        materialOverrides={materialOverrides}
        receiveShadows={receiveShadows}
        renderMode={renderMode}
        renderConfiguration={renderConfiguration}
        quality={quality}
        displaySettings={displaySettingsActive ? displaySettings : null}
        previewMode={previewMode}
        showViewPlane={!previewMode}
        scale={capabilities.sceneScale === "urdf" ? VIEWER_SCENE_SCALE.URDF : VIEWER_SCENE_SCALE.CAD}
        viewPlaneOffsetBottom="1rem"
        compactViewPlane={false}
        isLoading={viewerLoading && !retainingPreviousStepMesh}
        materialPickingEnabled={materialPickingEnabled}
        pickMode={materialPickingEnabled ? VIEWER_PICK_MODE.PARTS : !inspectionEnabled || retainingPreviousStepMesh || (!hasTopology && !hasParts && !measureModeActive)
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
        panToolActive={inspectionEnabled && panToolActive}
        renderPartsIndividually={capabilities.sceneScale === "urdf"
          ? true
          : ((renderPartsIndividually || Boolean(stepParameters?.definition))
            || Boolean(resolvedStepAnimation?.clip))}
        pickableParts={materialPickingEnabled ? selectedMeshData?.parts || EMPTY_LIST : inspectionEnabled && hasParts && !retainingPreviousStepMesh ? assemblyParts : EMPTY_LIST}
        hiddenPartIds={viewerHiddenPartIdsForRenderPane({ inspectionEnabled, hasParts, hiddenPartIds })}
        selectedPartIds={viewerSelectedPartIdsForRenderPane({ renderMode, hasParts, selectedPartIds })}
        hoveredPartId={inspectionEnabled && hasParts ? hoveredPartId : ""}
        hoveredReferenceId={inspectionEnabled && hasTopology && !retainingPreviousStepMesh ? hoveredReferenceId : ""}
        selectedReferenceIds={inspectionEnabled && hasTopology && !retainingPreviousStepMesh ? selectedReferenceIds : []}
        selectorRuntime={viewerSelectorRuntimeForRenderPane({ renderMode, hasTopology, retainingPreviousStepMesh, selectorRuntime })}
        displayEdgeRuntime={inspectionEnabled && hasTopology && !retainingPreviousStepMesh ? displayEdgeRuntime : null}
        stepParameters={capabilities.params === PARAMETER_SOURCE.SIDECAR ? stepParameters : null}
        stepAnimation={capabilities.params === PARAMETER_SOURCE.SIDECAR ? resolvedStepAnimation : null}
        glbDocument={glbDocument}
        embeddedGlbAnimation={resolvedEmbeddedGlbAnimation}
        pickableFaces={inspectionEnabled && hasTopology && !retainingPreviousStepMesh ? pickableFaces : []}
        pickableEdges={inspectionEnabled && hasTopology && !retainingPreviousStepMesh ? pickableEdges : []}
        pickableVertices={inspectionEnabled && hasTopology && !retainingPreviousStepMesh ? pickableVertices : []}
        focusedPartId={inspectionEnabled && hasParts ? focusedPartIds : ""}
        boundsAnimationActive={cadViewerBoundsAnimationActive}
        drawingEnabled={inspectionEnabled && drawEnabled && drawToolActive}
        drawingTool={drawingTool}
        drawingStrokes={inspectionEnabled && drawEnabled ? drawingStrokes : []}
        onDrawingStrokesChange={inspectionEnabled ? handleDrawingStrokesChange : null}
        onPerspectiveChange={handlePerspectiveChange}
        onHoverReferenceChange={inspectionEnabled ? handleModelHoverChange : null}
        onActivateReference={materialPickingEnabled ? onMaterialPartActivate : inspectionEnabled ? handleModelReferenceActivate : null}
        onDoubleActivateReference={inspectionEnabled ? handleModelReferenceDoubleActivate : null}
        onContextReference={inspectionEnabled ? handleModelReferenceContext : null}
        onMeasurePick={inspectionEnabled ? onMeasurePick : null}
        onMeasureHoverPoint={inspectionEnabled ? onMeasureHoverPoint : null}
        activeMeasurementId={activeMeasurementId}
        measureState={inspectionEnabled ? measureState : null}
        measureModeActive={inspectionEnabled && measureModeActive}
        allowMeshVertexSnap={inspectionEnabled && !hasTopology}
        onViewerAlertChange={handleViewerAlertChange}
        onStepModuleTransformDetectedChange={handleStepModuleTransformDetectedChange}
      />
      {!previewMode && inspectionEnabled ? (
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
            className="bg-popover pointer-events-auto w-full max-w-lg min-w-0 max-h-full overflow-y-auto rounded-lg border p-5 text-left shadow-md"
          >
            <h2 className="mb-3 flex items-start gap-2 text-base font-semibold leading-6 text-foreground">
              <CircleAlert className={cn("mt-0.5 size-5 shrink-0", blockingViewerAlert.severity === "warning" ? "text-amber-500" : "text-destructive")} aria-hidden="true" />
              {blockingViewerAlert.title || blockingViewerAlert.summary || "Couldn’t display the model"}
            </h2>
            <ViewerAlertBody alert={blockingViewerAlert} onReload={onReload} />
          </div>
        </div>
      ) : null}
      {!previewMode && ctaMode && !stepUpdateInProgress && !topologySelectionPending && !topologySelectionUnavailable && !topologySelectionDeferred ? (
        <div className={cn("pointer-events-none absolute inset-x-4 z-20 flex min-w-0 justify-center", composerDestination ? "bottom-36" : "bottom-4")}>
          {/* A hidden ruler carrying the FULL ref label under the same width constraints as
              the button. Measured to decide whether the button can show the ref at all.
              Deliberately independent of what the button currently displays: measuring the
              visible label instead would latch, because swapping in the shorter count label
              shrinks the box and makes the ref look permanently too wide. Kept outside the
              button so the button's textContent stays exactly its label. */}
          <span aria-hidden="true" className={cn("pointer-events-none invisible absolute left-0 top-0", ctaMetricsClass)}>
            <span ref={ctaFullLabelRef} className="block min-w-0 max-w-full truncate">{ctaRefLabel}</span>
          </span>
          {ctaMode === "screenshot" ? <Button
            type="button" variant="default" size="sm"
            className={cn("pointer-events-auto border border-primary/20 bg-primary/85 text-primary-foreground shadow-lg shadow-black/20 hover:bg-primary/75 focus-visible:ring-primary/35", ctaMetricsClass)}
            disabled={ctaDisabled} onClick={() => void handleScreenshotCopy?.()} title={ctaTitle}
          ><span className="block min-w-0 max-w-full truncate">{ctaLabel}</span></Button> : <PromptContextAction
            type="button" variant="default" size="sm"
            className={cn("pointer-events-auto border border-primary/20 bg-primary/85 text-primary-foreground shadow-lg shadow-black/20 hover:bg-primary/75 focus-visible:ring-primary/35", ctaMetricsClass)}
            disabled={ctaDisabled} createContext={createPromptContext} onResult={onPromptResult} title={ctaTitle}
          ><span className="block min-w-0 max-w-full truncate">{ctaLabel}</span></PromptContextAction>}
          {selectionExtras ? <div className="pointer-events-auto ml-2">{selectionExtras}</div> : null}
        </div>
      ) : null}
    </div>
  );
}

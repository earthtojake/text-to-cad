import { useHostReference } from "../../file-view/hostReference.js";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import CadViewer from "../CadViewer.js";
import MissingFileAlert from "../../../kit/status/MissingFileAlert.js";
import { Button } from "@hardcore/ui/primitives/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from "@hardcore/ui/primitives/dropdown-menu";
import { AssemblyPartMenuItems } from "./AssemblyContextMenuItems.js";
import { PromptContextAction } from "../../../../host/PromptContextAction.js";
import BlockingViewerAlert, { blockingViewerAlert } from "../../../kit/status/BlockingViewerAlert.jsx";
import { cn } from "@hardcore/ui/utils";
import { RENDER_FORMAT } from "../../workbench/constants.js";
import {
  PARAMETER_SOURCE,
  renderCapabilities,
  supportsTool
} from "@hardcore/core/lib/renderCapabilities.js";
import {
  CAMERA_PROJECTION,
  normalizeCameraProjection
} from "@hardcore/core/lib/displaySettings.js";
import { VIEWER_PICK_MODE } from "@hardcore/core/lib/viewer/constants.js";
import { viewerHiddenPartIdsForRenderPane, viewerPickModeForRenderPane, viewerSelectedPartIdsForRenderPane, viewerSelectorRuntimeForRenderPane } from "../../workbench/viewerPickMode.js";

const EMPTY_LIST = Object.freeze([]);
const EMPTY_ACTIONS = Object.freeze({});
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

/**
 * The viewport's own menu, which exists ONLY while Select is the active tool: a
 * secondary tap under Measure, Draw, Pose or Animate opens nothing, because no
 * item of this menu means anything under those tools. (The native menu stays
 * suppressed and a secondary drag still pans, whatever tool is in hand.)
 *
 * Over a part it is the part menu (`AssemblyPartMenuItems`), the same list the
 * model tree's rows carry. Over empty space it is what can be done to the model
 * as a whole, and the workspace only opens it when that is something.
 */
function ViewerContextMenu({ menu, positionStyle, onClose, actions }) {
  const hostReference = useHostReference();
  if (!menu || !positionStyle) {
    return null;
  }

  const itemClassName = "text-xs";
  const close = (action) => (item) => { action?.(item); onClose?.(); };
  const handleAction = (action) => { action?.(menu); onClose?.(); };

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
                onSelect={() => handleAction(actions.onHideAll)}
              >
                Show all
              </DropdownMenuItem>
            ) : null}
            {menu.showShowAll === true && menu.showExpandCollapse === true ? (
              <DropdownMenuSeparator />
            ) : null}
            {menu.showExpandCollapse === true ? (
              <>
                <DropdownMenuItem
                  className={itemClassName}
                  disabled={menu.expandAllDisabled === true}
                  onSelect={() => handleAction(actions.onExpandAll)}
                >
                  Expand all
                </DropdownMenuItem>
                <DropdownMenuItem
                  className={itemClassName}
                  disabled={menu.collapseAllDisabled === true}
                  onSelect={() => handleAction(actions.onCollapseAll)}
                >
                  Collapse all
                </DropdownMenuItem>
              </>
            ) : null}
          </>
        ) : (
          <AssemblyPartMenuItems
            menu={menu}
            Item={DropdownMenuItem}
            Separator={DropdownMenuSeparator}
            itemClassName={itemClassName}
            actions={{
              ...Object.fromEntries(Object.entries(actions).map(([name, action]) => [name, close(action)])),
              // Offered only where the host has somewhere to put it.
              onAddToPrompt: hostReference?.canAddToPrompt ? close(actions.onAddToPrompt) : undefined
            }}
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
  previewOrbitSpeed = 1,
  viewerLoading,
  retainingPreviousStepMesh = false,
  viewerAlert,
  presentationKey,
  onPresentationChange,
  viewUpdate,
  loadingPresentation,
  stepUpdateInProgress,
  referenceSelectionPending = false,
  referenceSelectionUnavailable = false,
  referenceSelectionDeferred = false,
  onCameraZoomPercentChange = null,
  onLodCameraChange = null,
  onMeshSourceAdoption = null,
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
  drawToolActive,
  drawing,
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
  // The one set of part/model actions, shared with the model tree's row menu.
  viewerContextMenuActions = EMPTY_ACTIONS,
  handleViewerAlertChange,
  handleStepModuleTransformDetectedChange,
  selectionCount,
  copyButtonLabel,
  copyButtonCountLabel = "",
  selectionFilter = "all",
  animateToolActive = false,
  // The Pose tool's handles, or null while another tool is active.
  jointHandles = null,
  handleCopySelection,
  createPromptContext,
  onPromptResult,
  composerDestination = false,
  selectionExtras = null,
  handleScreenshotCopy,
}) {
  // No component re-renders for a playing frame: the viewer poses the model straight
  // from the animation clock (`usePlaybackFrames`). These props change on play, pause,
  // scrub and clip changes only; the scrubber is the clock's one React subscriber.
  // One capability lookup replaces the per-format mode booleans. Every gate below asks
  // what this format CAN do; none of them ask what it IS.
  const capabilities = renderCapabilities(renderFormat);
  const drawEnabled = supportsTool(renderFormat, "draw");
  // Formats with no per-part topology to select, annotate or explode: a plain mesh has
  // no parts, so it gets the stripped-down prop set.
  const hasParts = capabilities.parts;
  const hasTopology = capabilities.topology;
  const inspectionEnabled = true;
  // Render supplies one clean presentation display state to every format,
  // including plain meshes whose Inspect mode has no display-mode panel.
  const displaySettingsActive = !!displaySettings;
  const cadProjection = normalizeCameraProjection(projection, CAMERA_PROJECTION.ORTHOGRAPHIC);
  const cadViewerBoundsAnimationActive = Boolean(stepAnimation?.playing);
  const topologySelectionPending = Boolean(referenceSelectionPending && hasTopology);
  const topologySelectionUnavailable = Boolean(referenceSelectionUnavailable && hasTopology);
  const topologySelectionDeferred = Boolean(referenceSelectionDeferred && selectedMeshData && hasTopology);
  // Is there anything on screen? For a mesh-backed format that means mesh data, so a failed
  // build reads as "nothing renderable" and lets the viewer alert block.
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
  const ctaRefLabel = ctaMode === "screenshot" ? (composerDestination ? "Add to Prompt" : "Copy Drawing") : composerDestination ? "Add to prompt" : copyButtonLabel;
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
  const ctaTitle = ctaMode === "screenshot" ? (composerDestination ? "Add the view and its drawing to the prompt" : "Copy the view and its drawing to the clipboard") : ctaRefLabel;
  const ctaDisabled = ctaMode === "screenshot"
    ? viewerLoading || !viewportHasRenderableContent
    : false;
  const blockingAlert = blockingViewerAlert(viewerAlert, viewportHasRenderableContent);
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
        viewUpdate={viewUpdate}
        loadingPresentation={loadingPresentation}
        renderFormat={renderFormat}
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
        previewOrbitSpeed={previewOrbitSpeed}
        showViewPlane={!previewMode}
        viewPlaneOffsetBottom="1rem"
        compactViewPlane={false}
        isLoading={viewerLoading && !retainingPreviousStepMesh}
        // Animate, like fullscreen, is watching, and Pose offers its knobs alone: nothing of the model is pickable.
        pickMode={previewMode || animateToolActive || jointHandles || !inspectionEnabled || retainingPreviousStepMesh || (!hasTopology && !hasParts && !measureModeActive)
          ? VIEWER_PICK_MODE.NONE
          : viewerPickModeForRenderPane({
            selectionFilter,
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
        renderPartsIndividually={(renderPartsIndividually || Boolean(stepParameters?.definition))
          || Boolean(stepAnimation?.clip)}
        pickableParts={inspectionEnabled && hasParts && !retainingPreviousStepMesh ? assemblyParts : EMPTY_LIST}
        hiddenPartIds={viewerHiddenPartIdsForRenderPane({ inspectionEnabled, hasParts, hiddenPartIds })}
        selectedPartIds={previewMode ? EMPTY_LIST : viewerSelectedPartIdsForRenderPane({ renderMode, hasParts, selectedPartIds })}
        hoveredPartId={!previewMode && inspectionEnabled && hasParts ? hoveredPartId : ""}
        hoveredReferenceId={!previewMode && inspectionEnabled && hasTopology && !retainingPreviousStepMesh ? hoveredReferenceId : ""}
        selectedReferenceIds={!previewMode && inspectionEnabled && hasTopology && !retainingPreviousStepMesh ? selectedReferenceIds : EMPTY_LIST}
        selectorRuntime={viewerSelectorRuntimeForRenderPane({ renderMode, hasTopology, retainingPreviousStepMesh, selectorRuntime })}
        displayEdgeRuntime={inspectionEnabled && hasTopology && !retainingPreviousStepMesh ? displayEdgeRuntime : null}
        stepParameters={capabilities.params === PARAMETER_SOURCE.SIDECAR ? stepParameters : null}
        stepAnimation={capabilities.params === PARAMETER_SOURCE.SIDECAR ? stepAnimation : null}
        animateMode={previewMode || animateToolActive}
        jointHandles={previewMode ? null : jointHandles}
        // One shared empty list: a fresh [] per render — per animation frame — invalidated the
        // viewer's pickable memos and reference map. Animate, Pose and fullscreen pick nothing at all.
        pickableFaces={inspectionEnabled && hasTopology && !retainingPreviousStepMesh && !previewMode && !animateToolActive && !jointHandles ? pickableFaces : EMPTY_LIST}
        pickableEdges={inspectionEnabled && hasTopology && !retainingPreviousStepMesh && !previewMode && !animateToolActive && !jointHandles ? pickableEdges : EMPTY_LIST}
        pickableVertices={inspectionEnabled && hasTopology && !retainingPreviousStepMesh && !previewMode && !animateToolActive && !jointHandles ? pickableVertices : EMPTY_LIST}
        focusedPartId={inspectionEnabled && hasParts ? focusedPartIds : ""}
        boundsAnimationActive={cadViewerBoundsAnimationActive}
        drawingEnabled={!previewMode && inspectionEnabled && drawEnabled && drawToolActive}
        drawing={drawing}
        onPerspectiveChange={handlePerspectiveChange}
        onHoverReferenceChange={!previewMode && inspectionEnabled ? handleModelHoverChange : null}
        onActivateReference={!previewMode && inspectionEnabled ? handleModelReferenceActivate : null}
        onDoubleActivateReference={!previewMode && inspectionEnabled ? handleModelReferenceDoubleActivate : null}
        onContextReference={!previewMode && inspectionEnabled ? handleModelReferenceContext : null}
        onMeasurePick={!previewMode && inspectionEnabled ? onMeasurePick : null}
        onMeasureHoverPoint={!previewMode && inspectionEnabled ? onMeasureHoverPoint : null}
        activeMeasurementId={activeMeasurementId}
        measureState={inspectionEnabled ? measureState : null}
        measureModeActive={!previewMode && inspectionEnabled && measureModeActive}
        allowMeshVertexSnap={inspectionEnabled && !hasTopology}
        onViewerAlertChange={handleViewerAlertChange}
        onStepModuleTransformDetectedChange={handleStepModuleTransformDetectedChange}
      />
      {!previewMode && inspectionEnabled ? (
        <ViewerContextMenu
          menu={viewerContextMenu}
          positionStyle={viewerContextMenuStyle}
          onClose={onViewerContextMenuClose}
          actions={viewerContextMenuActions}
        />
      ) : null}
      <MissingFileAlert missingFileRef={missingFileRef} rootPath={viewerServerInfo?.rootPath} previewMode={previewMode} />
      {!previewMode ? <BlockingViewerAlert alert={blockingAlert} onReload={onReload} /> : null}
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

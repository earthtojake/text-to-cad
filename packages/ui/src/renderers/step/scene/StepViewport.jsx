import { forwardRef, useCallback, useImperativeHandle, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { hasAuthoredMaterials } from "@hardcore/core/common/inspectEnvironment.js";
import { CAMERA_PROJECTION, normalizeCameraProjection } from "@hardcore/core/lib/displaySettings.js";
import { hasMeshGeometry } from "@hardcore/core/lib/render/meshCost.js";
import { displayRecordsBounds, mergeBoundsList } from "@hardcore/core/lib/viewer/autoZoom.js";
import { VIEWER_PICK_MODE } from "@hardcore/core/lib/viewer/constants.js";
import { runtimeModelKeyMatches, toNumber } from "@hardcore/core/lib/viewer/modelRuntime.js";
import { normalizePartIdList } from "@hardcore/core/lib/viewer/partVisualState.js";
import { PromptContextAction } from "../../../host/PromptContextAction.js";
import ShellViewport from "../../kit/shell/ShellViewport.jsx";
import ViewportBottomAction, { drawingCaptureAction } from "../../kit/shell/ViewportBottomAction.jsx";
import ViewportContextMenu from "../../kit/shell/ViewportContextMenu.jsx";
import BlockingViewerAlert, { blockingViewerAlert } from "../../kit/status/BlockingViewerAlert.jsx";
import MissingFileAlert from "../../kit/status/MissingFileAlert.js";
import { sampleLodCamera } from "../render/lodCameraSample.js";
import {
  viewerHiddenPartIdsForRenderPane, viewerPickModeForRenderPane, viewerSelectedPartIdsForRenderPane,
  viewerSelectorRuntimeForRenderPane
} from "../workbench/viewerPickMode.js";
import StepSceneLayers, { releaseStepRuntime } from "./StepSceneLayers.jsx";
import { createStepScene, stepSceneView } from "./stepScene.js";
import { useStepViewPolicy } from "./useStepViewPolicy.js";

const EMPTY_LIST = Object.freeze([]);

// --- zoom to selection -------------------------------------------------------
// What a selection occupies NOW: the boxes of its references, from the selector runtime as
// posed, merged with the boxes of its parts, from the records on screen (explosion included).
function pointBounds(center) {
  if (!Array.isArray(center) && !ArrayBuffer.isView(center)) return null;
  const point = [toNumber(center[0]), toNumber(center[1]), toNumber(center[2])];
  return { min: point, max: [...point] };
}

function selectorReferenceForId(selectorRuntime, referenceId) {
  const id = String(referenceId || "").trim();
  if (!id || !selectorRuntime) return null;
  return selectorRuntime.referenceMap?.get?.(id) ||
    selectorRuntime.faceReferenceMap?.get?.(id) ||
    selectorRuntime.edgeReferenceMap?.get?.(id) ||
    selectorRuntime.referenceByDisplaySelector?.get?.(id) ||
    selectorRuntime.referenceByNormalizedSelector?.get?.(id) ||
    null;
}

function selectorReferenceBounds(selectorRuntime, referenceIds = []) {
  const boundsList = [];
  for (const referenceId of normalizePartIdList(referenceIds)) {
    const reference = selectorReferenceForId(selectorRuntime, referenceId);
    const bbox = reference?.pickData?.bbox || reference?.bbox || null;
    const bounds = mergeBoundsList([bbox]) || pointBounds(reference?.pickData?.center || reference?.center);
    if (bounds) boundsList.push(bounds);
  }
  return mergeBoundsList(boundsList);
}

function displayRecordBoundsForPartIds(runtime, partIds = []) {
  const normalizedPartIds = normalizePartIdList(partIds);
  if (!normalizedPartIds.length || !Array.isArray(runtime?.displayRecords)) return null;
  const translationByRecord = new Map();
  for (const record of runtime.displayRecords) {
    const elements = record?.explodedViewMatrix?.elements;
    if (!elements || elements.length < 16) continue;
    const translation = new THREE.Vector3(toNumber(elements[12]), toNumber(elements[13]), toNumber(elements[14]));
    if (translation.lengthSq() > 1e-12) translationByRecord.set(record, translation);
  }
  return displayRecordsBounds(runtime.displayRecords, { partIds: new Set(normalizedPartIds), translationByRecord });
}

/**
 * The STEP renderer's viewport: the kit's `ShellViewport` around the ONE STEP scene
 * (`stepScene.js`), with everything of a STEP that lives in the viewport mounted through its
 * overlay slot (`StepSceneLayers.jsx`), the viewport menu and the bottom action from the
 * shell's own pieces, and the two alerts that cover the canvas.
 *
 * It is a props adapter and nothing else: it turns the workspace's state into what the
 * viewport is ALLOWED to show and pick just now (nothing under Pose, Animate or fullscreen;
 * no topology while a previous mesh is being held over an update), and adds to the kit
 * viewport's handle the two things only a STEP can answer -- the LOD camera sample and the
 * bounds of a selection.
 */
const StepViewport = forwardRef(function StepViewport({
  onReload,
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
  // The viewport menu: `(press, referenceIdUnderThePress) => entries | null`, or null outside Select.
  contextMenuItems = null,
  onContextMenuOpenChange = null,
  onMeasurePick,
  onMeasureHoverPoint,
  activeMeasurementId = "",
  measureState = null,
  measureModeActive = false,
  handleViewerAlertChange,
  handleStepModuleTransformDetectedChange,
  selectionCount,
  copyButtonLabel,
  copyButtonCountLabel = "",
  selectionFilter = "all",
  animateToolActive = false,
  // The Pose tool's handles, or null while another tool is active.
  jointHandles = null,
  createPromptContext,
  onPromptResult,
  composerDestination = false,
  selectionExtras = null,
  handleScreenshotCopy
}, ref) {
  // No component re-renders for a playing frame: the pose pass runs straight from the
  // animation clock (`usePlaybackFrames`). These props change on play, pause, scrub and clip
  // changes only; the scrubber is the clock's one React subscriber.
  const topologySelectionPending = Boolean(referenceSelectionPending);
  const topologySelectionUnavailable = Boolean(referenceSelectionUnavailable);
  const topologySelectionDeferred = Boolean(referenceSelectionDeferred && selectedMeshData);
  const holdingPreviousMesh = retainingPreviousStepMesh;
  // Animate, like fullscreen, is watching, and Pose offers its knobs alone: nothing of the model is pickable.
  const watching = previewMode || animateToolActive || Boolean(jointHandles);
  const isLoading = viewerLoading && !holdingPreviousMesh;
  const pickMode = watching || holdingPreviousMesh
    ? VIEWER_PICK_MODE.NONE
    : viewerPickModeForRenderPane({
      selectionFilter,
      topologySelectionPending,
      topologySelectionUnavailable,
      topologySelectionDeferred,
      topologyPickingActive: Boolean(pickableFaces?.length || pickableEdges?.length || pickableVertices?.length),
      viewerMode,
      assemblyPickingActive,
      focusedPartIds,
      measureMode: measureModeActive
    });
  // One shared empty list: a fresh [] per render -- per animation frame -- invalidated the
  // layers' pickable memos and reference map.
  const pickable = list => (!holdingPreviousMesh && !watching ? list : EMPTY_LIST);
  // Part-state lists pass through by IDENTITY, both here and in the helpers below
  // (`workbench/viewerPickMode.js` hands back the list it was given, or the one shared empty
  // one). What reaches this component is already stable for as long as its contents hold —
  // the workspace derives each of these through a memo — so there is nothing to hold back
  // here. A comparison in this component used to do it, and while it was here the churn
  // upstream was invisible: the SAME ids in a fresh array re-ran every layer keyed on the
  // list, part visual state over every record among them, on renders that changed no part.
  const stableHiddenPartIds = viewerHiddenPartIdsForRenderPane({ inspectionEnabled: true, hasParts: true, hiddenPartIds });
  const stableSelectedPartIds = previewMode ? EMPTY_LIST : viewerSelectedPartIdsForRenderPane({ renderMode, hasParts: true, selectedPartIds });
  const stableHoveredPartId = !previewMode ? hoveredPartId : "";
  const stableFocusedPartIds = focusedPartIds;
  const layerProps = {
    meshData: selectedMeshData,
    modelKey: selectedKey,
    isLoading,
    renderMode,
    renderConfiguration,
    appearance,
    materialOverrides,
    receiveShadows,
    previewMode,
    pickMode,
    pickableParts: !holdingPreviousMesh ? assemblyParts : EMPTY_LIST,
    hiddenPartIds: stableHiddenPartIds,
    selectedPartIds: stableSelectedPartIds,
    hoveredPartId: stableHoveredPartId,
    hoveredReferenceId: !previewMode && !holdingPreviousMesh ? hoveredReferenceId : "",
    selectedReferenceIds: !previewMode && !holdingPreviousMesh ? selectedReferenceIds : EMPTY_LIST,
    selectorRuntime: viewerSelectorRuntimeForRenderPane({ renderMode, hasTopology: true, retainingPreviousStepMesh: holdingPreviousMesh, selectorRuntime }),
    displayEdgeRuntime: !holdingPreviousMesh ? displayEdgeRuntime : null,
    stepParameterRuntime: stepParameters,
    // {clip, elapsedSec, playing} or null. Null means no clip is selected, and the evaluator never runs.
    stepAnimationRuntime: stepAnimation,
    animateMode: previewMode || animateToolActive,
    jointHandles: previewMode ? null : jointHandles,
    measureState,
    activeMeasurementId,
    measureModeActive: !previewMode && measureModeActive,
    allowMeshVertexSnap: false,
    onLodCameraChange,
    onMeshSourceAdoption,
    onViewerAlertChange: handleViewerAlertChange,
    onStepModuleTransformDetectedChange: handleStepModuleTransformDetectedChange,
    onHoverReferenceChange: !previewMode ? handleModelHoverChange : null,
    onActivateReference: !previewMode ? handleModelReferenceActivate : null,
    onDoubleActivateReference: !previewMode ? handleModelReferenceDoubleActivate : null,
    onMeasurePick: !previewMode ? onMeasurePick : null,
    onMeasureHoverPoint: !previewMode ? onMeasureHoverPoint : null
  };
  const policy = useStepViewPolicy({
    meshData: selectedMeshData, themeSettings, displaySettings: displaySettings || null, renderMode, renderConfiguration,
    renderPartsIndividually: renderPartsIndividually || Boolean(stepParameters?.definition) || Boolean(stepAnimation?.clip),
    pickMode, pickableParts: layerProps.pickableParts, pickableFaces: pickable(pickableFaces), pickableEdges: pickable(pickableEdges),
    pickableVertices: pickable(pickableVertices), hiddenPartIds: layerProps.hiddenPartIds, selectedPartIds: layerProps.selectedPartIds,
    focusedPartId: stableFocusedPartIds
  });

  // ONE scene for as long as this viewport is mounted; what is inside it changes in place.
  const [stepScene] = useState(() => createStepScene(THREE));
  const keepsAuthoredFinish = useMemo(() => hasAuthoredMaterials(selectedMeshData), [selectedMeshData]);
  const sceneView = useMemo(() => stepSceneView(stepScene, keepsAuthoredFinish), [stepScene, keepsAuthoredFinish]);
  const scene = !isLoading && hasMeshGeometry(selectedMeshData) ? sceneView : null;

  const shellRef = useRef(null);
  const runtimeRefRef = useRef(null);
  const layersApiRef = useRef(null);
  const pickAtRef = useRef(null);
  layerProps.pickAtRef = pickAtRef;
  const lodSelectedPartIdsRef = useRef(layerProps.selectedPartIds);
  lodSelectedPartIdsRef.current = layerProps.selectedPartIds;
  const modelKeyRef = useRef(selectedKey);
  modelKeyRef.current = selectedKey;
  const meshSourceAdoptionRef = useRef(onMeshSourceAdoption);
  meshSourceAdoptionRef.current = onMeshSourceAdoption;

  // The WebGL runtime under the scene. A scene owns GPU-backed work the LOD publisher is
  // counting on, so every way a runtime can go away is named to it exactly once — and this
  // is that one place. There is deliberately no unmount effect here releasing the scene as
  // well: unmounting this component unmounts the viewport under it, which releases its
  // runtime, which calls `onRelease`.
  const runtimeLifecycle = useMemo(() => ({
    onRelease(runtime, { handoff }) {
      const source = releaseStepRuntime(runtime, stepScene);
      meshSourceAdoptionRef.current?.(source, false, { disposed: true, terminal: !handoff, handoff });
    },
    onContextLost() { meshSourceAdoptionRef.current?.(null, false); },
    // A replacement runtime that cannot initialize has no future scene that can finish an
    // in-flight LOD handoff.
    onInitializationError() { meshSourceAdoptionRef.current?.(null, false, { disposed: true, terminal: true }); }
  }), [stepScene]);

  useImperativeHandle(ref, () => {
    const shell = () => shellRef.current;
    return {
      prepareViewSettings: (...args) => shell()?.prepareViewSettings(...args),
      presentViewSettings: () => shell()?.presentViewSettings(),
      captureScreenshotBlob: () => {
        if (!shell()) throw new Error("CAD Viewer not ready");
        return shell().captureScreenshotBlob();
      },
      activateViewPlaneFace: faceId => shell()?.activateViewPlaneFace(faceId),
      activateDefaultViewPlane: () => shell()?.activateDefaultViewPlane(),
      focusViewPreset: faceId => shell()?.activateViewPlaneFace(faceId),
      requestRender: () => shell()?.requestRender(),
      getPerspective: () => shell()?.getPerspective(),
      setPerspective: (perspective, options) => shell()?.setPerspective(perspective, options),
      // Frame the whole model again. "Zoom to fit" in the context menu and the live
      // resetCamera command are the same act.
      resetZoom: () => shell()?.resetZoom(),
      // Viewport LOD sampler: projection parameters + nearest eligible occurrence distances.
      // Whole live bounds include floor/group placement; numeric samples retain no scene objects.
      sampleLodCamera(options) {
        const runtime = runtimeRefRef.current?.current;
        if (!runtimeModelKeyMatches(runtime, modelKeyRef.current)) return null;
        return sampleLodCamera(THREE, runtime, { ...options, selectedPartIds: lodSelectedPartIdsRef.current });
      },
      // Frame what is selected: the context menu's "Zoom to selection". Framing the
      // whole model is resetZoom above, not a fallback here.
      zoomToFitSelection({ partIds = [], referenceIds = [], animate = true } = {}) {
        const runtime = runtimeRefRef.current?.current;
        const bounds = mergeBoundsList([
          selectorReferenceBounds(layersApiRef.current?.activeSelectorRuntime, referenceIds),
          displayRecordBoundsForPartIds(runtime, partIds)
        ]);
        return bounds ? Boolean(shell()?.zoomToBounds(bounds, { animate })) : false;
      }
    };
  }, [stepScene]);

  const menuItems = useCallback(press => contextMenuItems?.(press, pickAtRef.current?.(press.clientX, press.clientY) || "") || null,
    [contextMenuItems]);

  const selectionActionVisible = selectionCount > 0 && !stepUpdateInProgress && !topologySelectionPending
    && !topologySelectionUnavailable && !topologySelectionDeferred;
  const hasContent = Boolean(selectedMeshData);
  const bottomAction = previewMode ? null : drawToolActive
    ? (stepUpdateInProgress || topologySelectionPending || topologySelectionUnavailable || topologySelectionDeferred ? null
      : drawingCaptureAction({ composer: composerDestination, disabled: viewerLoading || !hasContent, onInvoke: handleScreenshotCopy }))
    : selectionActionVisible ? {
      // A reference cut off mid-token reads like a broken reference, so a long one becomes a count.
      label: composerDestination ? "Add to prompt" : copyButtonLabel,
      shortLabel: composerDestination ? "" : copyButtonCountLabel,
      render: ({ className, disabled, title, children }) => (
        <PromptContextAction type="button" variant="default" size="sm" className={className} disabled={disabled}
          createContext={createPromptContext} onResult={onPromptResult} title={title}>{children}</PromptContextAction>
      ),
      children: selectionExtras
    } : null;

  return (
    <div className="absolute inset-0">
      <ShellViewport
        ref={shellRef}
        scene={scene}
        modelKey={selectedKey}
        presentationKey={presentationKey}
        perspective={viewerPerspective}
        perspectiveRef={viewerPerspectiveRef}
        projection={normalizeCameraProjection(projection, CAMERA_PROJECTION.ORTHOGRAPHIC)}
        focalLength={focalLength}
        themeSettings={themeSettings}
        displaySettings={displaySettings || null}
        appearance={appearance}
        receiveShadows={receiveShadows}
        renderMode={renderMode}
        renderConfiguration={renderConfiguration}
        quality={quality}
        previewMode={previewMode}
        previewOrbitSpeed={previewOrbitSpeed}
        isLoading={isLoading}
        viewUpdate={viewUpdate}
        loadingPresentation={loadingPresentation}
        drawingEnabled={!previewMode && drawToolActive}
        drawing={drawing}
        onPerspectiveChange={handlePerspectiveChange}
        onPresentationChange={onPresentationChange}
        onViewerAlertChange={handleViewerAlertChange}
        onCameraSettled={onLodCameraChange}
        preserveInteractionPixelRatio={policy.wireframeMode || policy.edgesVisible}
        runtimeLifecycle={runtimeLifecycle}
      >{viewport => {
        runtimeRefRef.current = viewport.runtimeRef;
        return <>
          {previewMode || !contextMenuItems ? null
            : <ViewportContextMenu viewport={viewport} items={menuItems} onOpenChange={onContextMenuOpenChange} />}
          <StepSceneLayers viewport={viewport} stepScene={stepScene} policy={policy} props={layerProps} api={layersApiRef} />
        </>;
      }}</ShellViewport>
      <MissingFileAlert missingFileRef={missingFileRef} rootPath={viewerServerInfo?.rootPath} previewMode={previewMode} />
      {!previewMode ? <BlockingViewerAlert alert={blockingViewerAlert(viewerAlert, hasContent)} onReload={onReload} /> : null}
      {bottomAction ? <ViewportBottomAction composer={composerDestination} {...bottomAction} /> : null}
    </div>
  );
});

export default StepViewport;

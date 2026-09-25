import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { normalizeStepClipSettings } from "@hardcore/core/lib/viewer/clipPlane.js";
import { syncRuntimeStepClipPlane } from "@hardcore/core/lib/viewer/modelRuntime.js";
import JointHandleOverlay from "../../kit/tools/pose/JointHandleOverlay.jsx";
import { createStaticSceneReset, staticSceneResetEligible } from "../render/staticSceneReset.js";
import { renderMemoryAccounting } from "../render/renderMemoryAccounting.js";
import { useStepPartVisualState, useStepLinework } from "./useStepDisplay.js";
import { useStepExplode } from "./useStepExplode.js";
import { useStepHighlights } from "./useStepHighlights.js";
import { useStepMeasureOverlay } from "./useStepMeasureOverlay.js";
import { useStepPicking } from "./useStepPicking.js";
import { useStepPose } from "./useStepPose.js";
import { releaseStepRuntime, useStepSceneSync } from "./useStepSceneSync.js";
import ViewportError from "../../kit/status/ViewportError.jsx";

/**
 * Everything of a STEP that lives IN the viewport, mounted through the kit viewport's overlay
 * slot with `{ runtimeRef, hostRef, mountRef, viewerReadyTick, commitScene }`.
 *
 * It is the shared state the layers meet in and the order they run in; each layer is its own
 * module. The order is the contract: the scene sync makes the records, part state dresses
 * them, the pose pass moves them, the exploded view offsets them, and only then are the pick
 * proxies, the linework and the highlights laid over where they ended up. A child's effects
 * run before its parent's, so all of it runs before the viewport's own adoption effect --
 * which is why the sync commits the scene itself (`viewport.commitScene`).
 *
 * | layer | module |
 * | --- | --- |
 * | section clip | here (one effect) |
 * | scene sync, reuse or rebuild, LOD ownership | `useStepSceneSync.js` |
 * | hidden / isolated / hovered / selected parts | `useStepDisplay.js` (`useStepPartVisualState`) |
 * | sidecar module, pose and animation, the frame | `useStepPose.js` |
 * | exploded view | `useStepExplode.js` |
 * | pick proxies, B-rep linework, part highlight | `useStepDisplay.js` (`useStepLinework`) |
 * | reference highlight | `useStepHighlights.js` |
 * | measure rulers and the snap indicator | `useStepMeasureOverlay.js` |
 * | pointer: hover, tap, double-click, measure picks | `useStepPicking.js` |
 * | Pose knobs | the kit's `JointHandleOverlay` |
 */
export default function StepSceneLayers({ viewport, stepScene, policy, props, api }) {
  const { runtimeRef, hostRef, mountRef, viewerReadyTick } = viewport;
  const {
    meshData, modelKey, isLoading, renderMode, previewMode, pickMode, hiddenPartIds, selectedPartIds,
    hoveredPartId, selectorRuntime, stepParameterRuntime, stepAnimationRuntime, animateMode,
    jointHandles, measureState, activeMeasurementId, measureModeActive,
    onLodCameraChange, onMeshSourceAdoption, onViewerAlertChange,
    onHoverReferenceChange, onActivateReference, onDoubleActivateReference, onMeasurePick, onMeasureHoverPoint
  } = props;
  const stepAnimationPlaying = Boolean(stepAnimationRuntime?.playing);

  // Fresh even when every prop is unchanged: a receipt can skip only the duplicate reset in
  // this render, never work triggered by a later render.
  const staticResetRenderToken = {};
  const staticSceneResetRef = useRef(null);
  if (!staticSceneResetRef.current) staticSceneResetRef.current = createStaticSceneReset();
  useEffect(() => () => staticSceneResetRef.current.reset(), []);

  const measureCanvasRef = useRef(null);
  const jointHandleLayoutRef = useRef(null);
  // The snap indicator needs the live hover point every frame; the workspace only needs to
  // know which entity is under the cursor. A ref tracks it without a render per move.
  const measureHoverRef = useRef(null);
  const lodCameraChangeRef = useRef(onLodCameraChange);
  lodCameraChangeRef.current = onLodCameraChange;
  const meshSourceAdoptionRef = useRef(onMeshSourceAdoption);
  meshSourceAdoptionRef.current = onMeshSourceAdoption;
  const viewerAlertChangeRef = useRef(onViewerAlertChange);
  const sceneUpdateAlertRef = useRef(null);
  // The last { title, message } the pose pass raised, so it is deduplicated across frames and
  // cleared when a pass runs clean.
  const sceneEffectsAlertRef = useRef(null);
  const explosionRef = useRef({ rafId: 0, progress: 0, modelKey: "", enabled: false, layout: null });
  const clipSettingsRef = useRef(normalizeStepClipSettings(null));
  const selectorRuntimeRef = useRef(selectorRuntime);
  const stepModuleCleanupRef = useRef([]);
  const [transformedSelectorRuntime, setTransformedSelectorRuntime] = useState(null);
  const [error, setError] = useState("");
  // Bumped whenever the exploded view reaches a POSE it will hold: overlays that bake a
  // record's matrix at build time (the reference highlight) re-read it here.
  const [explodedViewPoseTick, setExplodedViewPoseTick] = useState(0);
  // Bumped every time the scene sync leaves a fresh set of records: state baked ONTO records
  // rather than into React is lost by a rebuild and has to be re-applied.
  const [displayRecordsToken, setDisplayRecordsToken] = useState(0);

  const activeSelectorRuntime = transformedSelectorRuntime?.base === selectorRuntime
    ? transformedSelectorRuntime.runtime
    : selectorRuntime;
  const edges = policy.edgeVisibility({ selectorRuntime: activeSelectorRuntime });
  const {
    viewerTheme, visualEdgeSettings, hiddenAwareVisualEdgeSettings, focusedPartIds, normalizedDisplayMode,
    normalizedClipSettings, partVisualStateEnabled, explodedViewActive, filteredPickableFaces, filteredPickableEdges,
    visibleReferenceFilter, normalizedThemeSettings
  } = policy;

  useLayoutEffect(() => {
    const explosion = explosionRef.current;
    staticSceneResetRef.current.beginRender(staticResetRenderToken, staticSceneResetEligible({
      source: meshData,
      renderFormat: "step",
      parameters: stepParameterRuntime,
      animation: stepAnimationRuntime,
      exploded: explodedViewActive || explosion.enabled || explosion.rafId || Number(explosion.progress) !== 0,
      loading: isLoading,
      records: runtimeRef.current?.displayRecords || [],
    }));
  });

  const partVisualState = () => ({
    viewerTheme,
    edgeSettings: visualEdgeSettings,
    hiddenPartIds: partVisualStateEnabled ? hiddenPartIds : [],
    hoveredPartId: partVisualStateEnabled ? hoveredPartId : "",
    focusedPartId: partVisualStateEnabled ? focusedPartIds : [],
    selectedPartIds: partVisualStateEnabled ? selectedPartIds : [],
    showEdges: edges.recordEdgesVisible,
    displayMode: normalizedDisplayMode
  });
  const partVisualStateRef = useRef(null);
  if (!partVisualStateRef.current) partVisualStateRef.current = partVisualState();
  useLayoutEffect(() => {
    partVisualStateRef.current = partVisualState();
  }, [
    normalizedDisplayMode,
    edges.recordEdgesVisible,
    focusedPartIds,
    hiddenPartIds,
    hiddenAwareVisualEdgeSettings,
    hoveredPartId,
    partVisualStateEnabled,
    selectedPartIds,
    viewerTheme,
    visualEdgeSettings
  ]);

  const pickableReferenceMap = useMemo(() => {
    if (activeSelectorRuntime?.referenceMap instanceof Map) {
      const map = new Map();
      for (const [referenceId, reference] of activeSelectorRuntime.referenceMap.entries()) {
        if (visibleReferenceFilter(reference)) {
          map.set(referenceId, reference);
        }
      }
      return map;
    }
    const map = new Map();
    for (const reference of [...filteredPickableFaces, ...filteredPickableEdges]) {
      const referenceId = String(reference?.id || "").trim();
      if (!referenceId) {
        continue;
      }
      map.set(referenceId, reference);
    }
    return map;
  }, [activeSelectorRuntime, filteredPickableEdges, filteredPickableFaces, visibleReferenceFilter]);

  useEffect(() => {
    viewerAlertChangeRef.current = onViewerAlertChange;
  }, [onViewerAlertChange]);
  useEffect(() => {
    setTransformedSelectorRuntime(null);
  }, [modelKey, selectorRuntime]);
  useEffect(() => {
    selectorRuntimeRef.current = activeSelectorRuntime;
  }, [activeSelectorRuntime]);

  // The section clip: one plane, from the resolved view, over everything the scene drew.
  useEffect(() => {
    clipSettingsRef.current = normalizedClipSettings;
    const runtime = runtimeRef.current;
    if (!runtime?.THREE) {
      return;
    }
    syncRuntimeStepClipPlane(runtime, normalizedClipSettings);
    runtime.requestRender?.();
  }, [
    viewerReadyTick,
    meshData?.bounds,
    normalizedClipSettings.axis,
    normalizedClipSettings.enabled,
    normalizedClipSettings.invert,
    normalizedClipSettings.offset
  ]);

  const refs = {
    partVisualStateRef, clipSettingsRef, selectorRuntimeRef, staticSceneResetRef,
    meshSourceAdoptionRef, viewerAlertChangeRef, sceneUpdateAlertRef, sceneEffectsAlertRef, lodCameraChangeRef,
    stepModuleCleanupRef
  };
  const layers = {
    viewport, stepScene, props, policy, refs, edges, staticResetRenderToken, explosionRef,
    activeSelectorRuntime, pickableReferenceMap, setTransformedSelectorRuntime,
    displayRecordsToken, setDisplayRecordsToken, explodedViewPoseTick, setExplodedViewPoseTick, setError
  };
  useStepSceneSync(layers);
  useStepPartVisualState(layers);
  useStepPose(layers);
  useStepExplode(layers);
  useStepLinework(layers);
  useStepHighlights(layers);

  // What the renderer's handle needs from inside the viewport: the selector runtime as posed
  // (zoom to selection) and the records on screen.
  api.current = { activeSelectorRuntime };

  // Click is followed by OrbitControls clearing hover before React commits draft.anchor, so
  // the locked first point lives in a ref.
  const measureLockedAnchorRef = useRef(null);
  const handleMeasureHoverPoint = useCallback((pick) => {
    measureHoverRef.current = pick || measureLockedAnchorRef.current || null;
    onMeasureHoverPoint?.(pick);
  }, [onMeasureHoverPoint]);
  const handleMeasurePick = useCallback((pick) => {
    if (pick && !measureLockedAnchorRef.current) {
      measureLockedAnchorRef.current = pick;
      measureHoverRef.current = pick;
    } else if (pick && measureLockedAnchorRef.current) {
      measureLockedAnchorRef.current = null;
    }
    onMeasurePick?.(pick);
  }, [onMeasurePick]);
  // Disarming the tool has to drop the indicator; the pointer may never move again.
  useEffect(() => {
    if (!measureModeActive) {
      measureHoverRef.current = null;
      measureLockedAnchorRef.current = null;
    }
  }, [measureModeActive]);
  useEffect(() => {
    if (!measureState?.draft?.anchor) {
      measureLockedAnchorRef.current = null;
    }
  }, [measureState]);

  useStepMeasureOverlay({
    measureCanvasRef, measureState, activeMeasurementId, measureHoverRef, measureModeActive,
    runtimeRef, mountRef, previewMode, viewerReadyTick
  });

  useStepPicking({
    runtimeRef,
    mountRef: hostRef,
    sceneMountRef: mountRef,
    previewMode,
    pickMode,
    selectorRuntime: activeSelectorRuntime,
    pickableFaces: filteredPickableFaces,
    pickableEdges: filteredPickableEdges,
    hiddenPartIds,
    focusedPartId: focusedPartIds,
    onHoverReferenceChange,
    onActivateReference,
    onDoubleActivateReference,
    pickAtRef: props.pickAtRef,
    onMeasurePick: handleMeasurePick,
    onMeasureHoverPoint: handleMeasureHoverPoint,
    viewerReadyTick,
    suppressTopologyPicking: animateMode || Array.isArray(jointHandles) || stepAnimationPlaying
  });

  // Read-only debug/test seams. `__cadCamera` and `__cadStage` are the viewport's.
  const placementRef = useRef(null);
  placementRef.current = { modelKey, renderMode, floor: normalizedThemeSettings.floor || {}, renderConfiguration: props.renderConfiguration };
  useEffect(() => {
    // Byte attribution for the headless memory harness (read, never polled here).
    const memoryProbe = () => renderMemoryAccounting(runtimeRef.current);
    // The LIVE record transforms, so a browser test can assert where a posed occurrence
    // actually renders rather than what the data upstream of it said.
    const displayRecords = () => (runtimeRef.current?.displayRecords || []).map((record) => ({
      partId: String(record?.partId || ""),
      linkName: String(record?.sourcePart?.linkName || ""),
      matrix: record?.mesh?.matrix?.toArray?.() || null
    }));
    // Where the Position tool's knobs are, in CSS pixels of the viewport, with each joint's
    // value; empty outside the tool.
    const jointHandleLayout = () => jointHandleLayoutRef.current?.() || [];
    // The true-pose contract -- model at authored coordinates, ground per the floor coupling
    // -- read LIVE, so a render setting that moves the ground shows without a scene sync.
    const placement = () => {
      const runtime = runtimeRef.current;
      const current = placementRef.current;
      if (!runtime?.hasVisibleModel || !stepScene.cadScene) return undefined;
      const bounds = stepScene.bounds;
      const configuration = current.renderConfiguration;
      return {
        modelKey: current.modelKey || "",
        position: runtime.modelGroup.position.toArray(),
        boundsMin: [...(Array.isArray(bounds?.min) ? bounds.min : [0, 0, 0])],
        boundsMax: [...(Array.isArray(bounds?.max) ? bounds.max : [0, 0, 0])],
        gridFloorZ: Number.isFinite(Number(runtime.gridFloorZ)) ? Number(runtime.gridFloorZ) : null,
        groundZ: current.renderMode && Number.isFinite(Number(runtime.photographicGroundZ)) ? Number(runtime.photographicGroundZ) : null,
        floorFollowsModel: current.renderMode
          ? configuration?.backdrop?.ground === true && configuration.backdrop.groundPlacement !== "origin"
          : current.floor.enabled === true && current.floor.followModel !== false
      };
    };
    Object.assign(window, { __cadRenderMemoryProbe: memoryProbe, __cadDisplayRecords: displayRecords, __cadJointHandles: jointHandleLayout });
    Object.defineProperty(window, "__cadModelPlacement", { configurable: true, get: placement });
    return () => {
      if (window.__cadRenderMemoryProbe === memoryProbe) delete window.__cadRenderMemoryProbe;
      if (window.__cadDisplayRecords === displayRecords) delete window.__cadDisplayRecords;
      if (window.__cadJointHandles === jointHandleLayout) delete window.__cadJointHandles;
      if (Object.getOwnPropertyDescriptor(window, "__cadModelPlacement")?.get === placement) delete window.__cadModelPlacement;
    };
  }, [runtimeRef, stepScene]);

  return (
    <>
      <canvas
        ref={measureCanvasRef}
        className="absolute inset-0 z-10 h-full w-full touch-none"
        style={{ pointerEvents: "none" }}
        aria-hidden="true"
      />
      {jointHandles ? <JointHandleOverlay handles={jointHandles} runtimeRef={runtimeRef} hostRef={hostRef} layoutSeamRef={jointHandleLayoutRef} viewerReadyTick={viewerReadyTick} /> : null}
      <ViewportError message={error} />
    </>
  );
}

export { releaseStepRuntime };

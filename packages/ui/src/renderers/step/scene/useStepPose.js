import { useEffect, useRef } from "react";
import * as THREE from "three";
import { resolveStepModuleFeatures } from "@hardcore/core/common/stepModule.js";
import {
  buildStepModuleContext, createStepModuleEffectsApi, resetStepModuleRecordEffects
} from "@hardcore/core/common/stepModuleEffects.js";
import { applySceneState } from "@hardcore/core/common/applySceneState.js";
import {
  resolveTopologyDisplayEdgeRuntimes, shouldRenderTopologyDisplayEdges, shouldUseRecordTopologyEdgeTransforms
} from "@hardcore/core/common/topologyDisplayEdgeRuntime.js";
import { applyDisplayRecordTransform, syncRuntimeStepClipPlane } from "@hardcore/core/lib/viewer/modelRuntime.js";
import { applyPartVisualState, FOCUSED_DIMMED_SURFACE_OPACITY } from "@hardcore/core/lib/viewer/partVisualState.js";
import { syncDisplayMeshFaceIds, syncSelectorPickGroups } from "@hardcore/core/lib/viewer/selectorPickGroups.js";
import { syncTopologyDisplayEdgeLine } from "@hardcore/core/lib/viewer/topologyDisplayEdgeLine.js";
import { usePlaybackFrames } from "../../kit/tools/playbar/usePlaybackFrames.js";
import { useAnimationClockStore } from "../workbench/animationClockStore.js";
import { clearSceneGroup, updateTransformedRuntimeState } from "./useStepSceneSync.js";

const MODEL_OFFSET = new THREE.Vector3(0, 0, 0);

/**
 * Pose and animation: the sidecar module's setup, and the ONE effects pass that puts the
 * model where its kinematics and its playing routine say it is.
 *
 * The pass is one function with two callers. React runs it when anything it reads changes (a
 * scrub, a pose, a display setting, a new mesh); while a routine plays, the animation clock
 * runs the same function once per tick (`usePlaybackFrames`), so a playing frame renders no
 * component at all.
 *
 * THE FRAME. A pose or animation write is drawn because this pass asks for a frame, once, as
 * its last act -- and nothing else on that path does. The topology line it re-syncs is told
 * not to ask (`requestRender: false`), and no other layer re-runs for a pose. One owner, so
 * "the model moved but the picture did not" has exactly one place to be wrong.
 */
export function useStepPose(layers) {
  const {
    viewport, props, policy, refs, staticResetRenderToken,
    setTransformedSelectorRuntime, setTransformedDisplayEdgeRuntime, displayRecordsToken
  } = layers;
  const { runtimeRef, viewerReadyTick } = viewport;
  const {
    meshData, modelKey, isLoading, pickMode, pickableParts, hiddenPartIds, selectedPartIds, hoveredPartId,
    selectorRuntime, displayEdgeRuntime, stepParameterRuntime, stepAnimationRuntime, animateMode
  } = props;
  const stepAnimationPlaying = Boolean(stepAnimationRuntime?.playing);
  const {
    viewerTheme, visualEdgeSettings, hiddenAwareVisualEdgeSettings, focusedPartIds, explodedViewActive,
    wireframeMode, edgesVisible, partVisualStateEnabled
  } = policy;
  const { topologyDisplayEdgesVisible, recordEdgesVisible } = layers.edges;
  const {
    partVisualStateRef, clipSettingsRef, selectorRuntimeRef, staticSceneResetRef, viewerAlertChangeRef,
    sceneEffectsAlertRef, lodCameraChangeRef, stepModuleTransformDetectedChangeRef, stepModuleCleanupRef
  } = refs;
  // A STEP's linework comes from its B-rep topology.
  const shouldUseCadEdgeSource = true;

  useEffect(() => {
    const runtime = runtimeRef.current;
    const definition = stepParameterRuntime?.definition || null;
    const module = definition?.module || null;
    const cleanups = [];
    stepModuleCleanupRef.current = cleanups;
    const runCleanups = () => {
      while (cleanups.length) {
        const cleanup = cleanups.pop();
        try {
          cleanup?.();
        } catch (error) {
          console.error("STEP parameter cleanup failed", error);
        }
      }
    };

    if (!runtime?.THREE || !definition || isLoading || !meshData) {
      return runCleanups;
    }

    const features = resolveStepModuleFeatures(definition, {
      meshData,
      selectorRuntime: selectorRuntimeRef.current
    });
    const ctx = buildStepModuleContext({
      runtime,
      stepModuleRuntime: stepParameterRuntime,
      features,
      effects: createStepModuleEffectsApi(runtime.THREE, {
        meshData,
        features,
        runtime,
        effectsByPartId: new Map()
      }),
      cleanup: (cleanup) => {
        if (typeof cleanup === "function") {
          cleanups.push(cleanup);
        }
      }
    });

    try {
      module?.setup?.(ctx);
    } catch (error) {
      viewerAlertChangeRef.current?.({
        severity: "warning",
        compact: true,
        title: "STEP parameter setup failed",
        message: error instanceof Error ? error.message : String(error)
      });
      console.error("STEP parameter setup failed", error);
    }

    return () => {
      runCleanups();
      try {
        module?.dispose?.(ctx);
      } catch (error) {
        console.error("STEP parameter dispose failed", error);
      }
    };
  }, [
    viewerReadyTick,
    isLoading,
    meshData,
    modelKey,
    selectorRuntime,
    stepParameterRuntime?.definition,
    stepParameterRuntime?.sourceUrl
  ]);

  // The frame function playback runs per clock tick, published by the pass below.
  const stepPoseFrameRef = useRef(null);
  usePlaybackFrames(useAnimationClockStore(), stepAnimationPlaying, stepPoseFrameRef);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !Array.isArray(runtime.displayRecords) || !runtime.displayRecords.length) {
      return;
    }

    const definition = stepParameterRuntime?.definition || null;
    const module = definition?.module || null;
    const animationClip = stepAnimationRuntime?.clip || null;
    // Either system can be the only one present: a model may declare mates
    // without shipping clips, or ship clips without declaring a single mate.
    // Only when NEITHER has anything to say does the pass fall back to rest.
    // An alert this pass raised earlier (e.g. a clip label the composition did
    // not carry) is cleared the moment a pass runs clean, or the module goes
    // away; a pass that fails the same way again does not re-raise it every
    // frame — one clean error per failing state.
    const clearSceneEffectsAlert = () => {
      if (sceneEffectsAlertRef.current) {
        sceneEffectsAlertRef.current = null;
        viewerAlertChangeRef.current?.(null);
      }
    };
    if ((!definition && !animationClip) || isLoading || !meshData) {
      clearSceneEffectsAlert();
      stepModuleTransformDetectedChangeRef.current?.(false);
      updateTransformedRuntimeState(setTransformedSelectorRuntime, null);
      updateTransformedRuntimeState(setTransformedDisplayEdgeRuntime, null);
      runtime.topologyDisplayEdgeTransformByRecord = explodedViewActive;
      if (staticSceneResetRef.current.consume(staticResetRenderToken, {
        source: meshData, runtime, visualState: partVisualStateRef.current, clipState: clipSettingsRef.current,
      })) {
        runtime.requestRender?.();
        return;
      }
      resetStepModuleRecordEffects(runtime.displayRecords, THREE);
      for (const record of runtime.displayRecords) {
        applyDisplayRecordTransform(runtime.THREE, record, runtime.modelRadius || 1);
      }
      applyPartVisualState(runtime.THREE, runtime.displayRecords, partVisualStateRef.current);
      runtime.cadScene?.syncSurfaceInstances();
      const baseTopologyDisplayEdgesVisible = shouldRenderTopologyDisplayEdges({
        edgesVisible,
        wireframeMode,
        cadEdgeSource: shouldUseCadEdgeSource,
        displayEdgeRuntime,
        selectorRuntime,
        edgeSettings: visualEdgeSettings
      });
      syncTopologyDisplayEdgeLine(runtime, displayEdgeRuntime || selectorRuntime, {
        visible: baseTopologyDisplayEdgesVisible,
        edgeSettings: hiddenAwareVisualEdgeSettings,
        focusedPartIds,
        viewerTheme,
        dimmedOpacity: FOCUSED_DIMMED_SURFACE_OPACITY,
        transformByRecord: explodedViewActive,
        displayRecords: runtime.displayRecords,
        syncClip: (activeRuntime) => syncRuntimeStepClipPlane(activeRuntime, clipSettingsRef.current),
        requestRender: false
      });
      runtime.invalidateShadows?.();
      lodCameraChangeRef.current?.();
      runtime.requestRender?.();
      return;
    }

    // ONE effects pass, shared with the headless twin (applySceneState):
    // kinematics update, then the clip merged OVER it — the two systems meet
    // in the effect records and nowhere else.
    //
    // It is one function with two callers. React runs it when anything it reads
    // changes (a scrub, a pose, a display setting, a new mesh); while a routine
    // plays, the animation clock runs the same function once per tick
    // (`usePlaybackFrames`), so a playing frame renders no component at all.
    const poseFrame = (elapsedSec) => {
      let transformDetected = false;
      let passError = null;
      const sceneState = applySceneState(runtime.THREE, {
        runtime,
        meshData,
        stepParameterRuntime,
        animation: animationClip
          ? { clip: animationClip, elapsedSec }
          : null,
        selectorRuntime: selectorRuntimeRef.current,
        onTransformEffect: () => {
          transformDetected = true;
        },
        onError: ({ phase, error }) => {
          const title = phase === "animation" ? "Animation update failed" : "Pose update failed";
          const message = error instanceof Error ? error.message : String(error);
          passError = { title, message };
          const previous = sceneEffectsAlertRef.current;
          if (previous && previous.title === title && previous.message === message) {
            return;
          }
          sceneEffectsAlertRef.current = passError;
          viewerAlertChangeRef.current?.({
            severity: "warning",
            compact: true,
            title,
            message
          });
          console.error(title, error);
        },
        cleanup: (cleanup) => {
          if (typeof cleanup === "function") {
            stepModuleCleanupRef.current.push(cleanup);
          }
        }
      });
      if (!passError) {
        clearSceneEffectsAlert();
      }
      const useRecordTopologyEdgeTransforms = explodedViewActive || shouldUseRecordTopologyEdgeTransforms({
        transformDetected,
        topologyDisplayEdgesVisible,
        displayEdgeRuntime,
        displayRecords: runtime.displayRecords
      });
      // The transformed selector runtime is pick-only output, and the costliest thing a
      // posed frame makes: every face and edge proxy de-indexed and re-transformed into
      // fresh arrays, behind a cache no moving frame can hit, and as React state it then
      // rebuilt pick groups, their BVH, the picking listeners and the highlight overlays —
      // every frame. In Animate mode none of it has a reader. The display edges keep their
      // own runtime; only a model whose edges come from the selector runtime still needs it.
      const posedSelectorRuntime = animateMode && displayEdgeRuntime ? null : selectorRuntime;
      const nextEdgeRuntimes = resolveTopologyDisplayEdgeRuntimes({
        selectorRuntime: posedSelectorRuntime,
        displayEdgeRuntime,
        displayRecords: transformDetected ? runtime.displayRecords : [],
        transformDisplayEdges: !useRecordTopologyEdgeTransforms
      });
      const nextTopologyDisplayEdgesVisible = shouldRenderTopologyDisplayEdges({
        edgesVisible,
        wireframeMode,
        cadEdgeSource: shouldUseCadEdgeSource,
        displayEdgeRuntime: useRecordTopologyEdgeTransforms ? displayEdgeRuntime : nextEdgeRuntimes.displayEdgeRuntime,
        selectorRuntime: nextEdgeRuntimes.selectorRuntime,
        edgeSettings: visualEdgeSettings
      });
      stepModuleTransformDetectedChangeRef.current?.(nextEdgeRuntimes.transformCount > 0);
      const nextSelectorRuntime = nextEdgeRuntimes.transformedSelectorRuntime;
      const nextDisplayEdgeRuntime = useRecordTopologyEdgeTransforms
        ? null
        : nextEdgeRuntimes.transformedDisplayEdgeRuntime;
      updateTransformedRuntimeState(setTransformedSelectorRuntime, nextSelectorRuntime && posedSelectorRuntime ? {
        base: selectorRuntime,
        runtime: nextSelectorRuntime
      } : null);
      updateTransformedRuntimeState(setTransformedDisplayEdgeRuntime, nextDisplayEdgeRuntime ? {
        base: displayEdgeRuntime,
        runtime: nextDisplayEdgeRuntime
      } : null);
      for (const record of runtime.displayRecords) {
        applyDisplayRecordTransform(runtime.THREE, record, runtime.modelRadius || 1);
      }
      // A playing frame that only moved parts has already synced each moved instance's
      // matrix (`applyDisplayRecordTransform`). Visual state and instance membership are
      // reconciled when a frame changed a style, a visibility or a highlight, and by
      // the passes React runs around playback.
      if (!stepAnimationPlaying || sceneState.appearanceChanged) {
        applyPartVisualState(runtime.THREE, runtime.displayRecords, partVisualStateRef.current);
        runtime.cadScene?.syncSurfaceInstances();
      }
      runtime.topologyDisplayEdgeTransformByRecord = useRecordTopologyEdgeTransforms;
      syncTopologyDisplayEdgeLine(
        runtime,
        useRecordTopologyEdgeTransforms ? displayEdgeRuntime : nextEdgeRuntimes.topologyRuntime,
        {
          visible: nextTopologyDisplayEdgesVisible,
          edgeSettings: hiddenAwareVisualEdgeSettings,
          focusedPartIds,
          viewerTheme,
          dimmedOpacity: FOCUSED_DIMMED_SURFACE_OPACITY,
          transformByRecord: useRecordTopologyEdgeTransforms,
          displayRecords: runtime.displayRecords,
          syncClip: (activeRuntime) => syncRuntimeStepClipPlane(activeRuntime, clipSettingsRef.current),
          requestRender: false
        }
      );
      runtime.modelGroup?.updateMatrixWorld?.(true);
      runtime.edgesGroup?.updateMatrixWorld?.(true);
      const effectiveRuntime = nextEdgeRuntimes.selectorRuntime;
      // Picking is suspended during STEP animation playback, so skip rebuilding
      // pick-only state per frame; the playing->stopped rerun syncs the final pose.
      if (!stepAnimationPlaying && !animateMode) {
        syncDisplayMeshFaceIds(runtime, meshData, effectiveRuntime);
        syncSelectorPickGroups(runtime, effectiveRuntime, MODEL_OFFSET, { clearSceneGroup });
        // A kinematic edit (or a stopped scrub) is a one-shot model-bounds
        // change for LOD and shadows. Playback stays on its existing bounded
        // frame loop; an idle posed model schedules no recurring work.
        runtime.invalidateShadows?.();
        lodCameraChangeRef.current?.();
      }
      runtime.requestRender?.();
    };
    poseFrame(Number(stepAnimationRuntime?.elapsedSec) || 0);
    stepPoseFrameRef.current = animationClip ? poseFrame : null;
    return () => {
      if (stepPoseFrameRef.current === poseFrame) stepPoseFrameRef.current = null;
    };
  }, [
    visualEdgeSettings,
    edgesVisible,
    wireframeMode,
    shouldUseCadEdgeSource,
    focusedPartIds,
    recordEdgesVisible,
    viewerReadyTick,
    viewerTheme,
    hiddenPartIds,
    hiddenAwareVisualEdgeSettings,
    hoveredPartId,
    explodedViewActive,
    isLoading,
    meshData,
    modelKey,
    partVisualStateEnabled,
    pickMode,
    pickableParts,
    selectedPartIds,
    selectorRuntime,
    displayEdgeRuntime,
    stepParameterRuntime,
    stepAnimationRuntime,
    // Leaving the mode must re-run this pass once: it is what rebuilds the pick state.
    animateMode
  ]);
}

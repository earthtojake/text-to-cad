import { useEffect } from "react";
import * as THREE from "three";
import { hasMeshGeometry } from "@hardcore/core/lib/render/meshCost.js";
import { resolveScenePartRendering } from "@hardcore/core/lib/viewer/partRendering.js";
import { VIEWER_SCENE_SCALE } from "@hardcore/core/lib/viewer/sceneScale.js";
import { applyPartVisualState, FOCUSED_DIMMED_SURFACE_OPACITY } from "@hardcore/core/lib/viewer/partVisualState.js";
import { syncTopologyDisplayEdgeLine } from "@hardcore/core/lib/viewer/topologyDisplayEdgeLine.js";
import { syncRuntimeStepClipPlane } from "@hardcore/core/lib/viewer/modelRuntime.js";
import { buildGlbFaceIdsForMesh, buildGlbFaceIdsForPart, syncSelectorPickGroups } from "@hardcore/core/lib/viewer/selectorPickGroups.js";
import { scheduleRuntimeRaycastBvh } from "@hardcore/core/lib/viewer/raycastBvh.js";
import { disposeSectionCaps } from "@hardcore/core/lib/viewer/sectionCaps.js";
import {
  resolveTopologyDisplayEdgeRuntimes, shouldUseRecordTopologyEdgeTransforms
} from "@hardcore/core/common/topologyDisplayEdgeRuntime.js";
import { cancelCameraTransition } from "../../kit/camera/runtimeCamera.js";
import { disposeSceneObject } from "../../kit/viewport/sceneObjects.js";
import { disposeViewerCadScene } from "../render/lodSceneCleanup.js";
import { renderMemoryAccounting } from "../render/renderMemoryAccounting.js";
import { sceneBuildStructuralKey } from "../render/sceneBuildSettings.js";
import { viewerMemoryPolicy } from "../render/viewerMemoryPolicy.js";
import { renderableMeshParts } from "./useStepViewPolicy.js";

// The model renders at its AUTHORED world coordinates: geometry is never re-centred on its
// bounds, and framing moves the camera to the model. The offset the pick groups and the clip
// plane take is plumbing that is always zero.
const MODEL_OFFSET = new THREE.Vector3(0, 0, 0);

export function clearSceneGroup(group) {
  for (const child of [...group.children]) disposeSceneObject(child);
}

function meshNeedsPartRenderingForSourceColors(meshData) {
  const parts = renderableMeshParts(meshData);
  const partColors = parts
    .map((part) => String(part?.color || "").trim().toLowerCase())
    .filter(Boolean);
  if (!partColors.length) {
    return false;
  }
  return partColors.length !== parts.length || new Set(partColors).size > 1;
}

export function transformedRuntimeStateEqual(current, next) {
  return (
    (current?.base || null) === (next?.base || null) &&
    (current?.runtime || null) === (next?.runtime || null)
  );
}

export function updateTransformedRuntimeState(setState, next) {
  setState((current) => (
    transformedRuntimeStateEqual(current, next) ? current : next
  ));
}

// Read-only debug/test seam (like __cadModelPlacement): how long each scene
// sync — the effect that turns a published mesh state into display records —
// held the main thread, and whether it rebuilt the scene or reused its records.
// Read by the headless timing harness; never React state.
//
// A long session syncs the scene thousands of times, and a benchmark reads the
// recent ones (usually the last), so the log is a window while count and
// totalMs stay the totals for the whole session.
const SCENE_SYNC_LOG_LIMIT = 200;

function recordSceneSyncTiming(startedAt, { mode, records, reason = "" }) {
  if (typeof window === "undefined") {
    return;
  }
  const ms = performance.now() - startedAt;
  const stats = window.__cadSceneSync || (window.__cadSceneSync = { count: 0, totalMs: 0, entries: [] });
  stats.count += 1;
  stats.totalMs += ms;
  stats.entries.push({ atMs: Math.round(performance.now()), ms: Math.round(ms * 10) / 10, mode, records, reason });
  if (stats.entries.length > SCENE_SYNC_LOG_LIMIT) {
    stats.entries.splice(0, stats.entries.length - SCENE_SYNC_LOG_LIMIT);
  }
}

/**
 * The scene sync: a published mesh state becomes display records inside the ONE STEP scene
 * (`stepScene.js`), and the viewport is told the scene changed in place.
 *
 * It decides reuse or rebuild (`stepScene.plan`): while the build settings hold for the same
 * model, a progressive publish or a detail swap is handed to the live build, which reconciles
 * its records -- occurrences on screen keep their meshes, materials, visual and deformation
 * state and BVHs. It answers the LOD publisher's ownership protocol (`onMeshSourceAdoption`):
 * every source this scene shows, releases or fails to show is named exactly once. And it
 * rebuilds what hangs off the records: the topology line, the pick groups, the raycast BVH
 * schedule and the section clip.
 *
 * What it does NOT do is the viewport's: the stage, the depth range and the camera's framing
 * all follow from `viewport.commitScene()`.
 */
export function useStepSceneSync(layers) {
  const {
    viewport, stepScene, props, policy, refs, staticResetRenderToken,
    setTransformedSelectorRuntime, setTransformedDisplayEdgeRuntime, setDisplayRecordsToken, setError, edges
  } = layers;
  const { runtimeRef, viewerReadyTick } = viewport;
  const {
    meshData, modelKey, isLoading, appearance, materialOverrides, receiveShadows, pickMode, pickableParts,
    selectorRuntime, displayEdgeRuntime, stepParameterRuntime
  } = props;
  const {
    viewerTheme, normalizedThemeSettings, normalizedDisplayMode, surfaceSettings, explicitViewPolicy,
    normalizedMaterialSettings, materialPartPolicyKey, effectiveRenderPartsIndividually, explodedViewActive,
    displayEdgeSettings, wireframeMode, wireframeEdgeColor, visualEdgeSettings, hiddenAwareVisualEdgeSettings, focusedPartIds
  } = policy;
  const { topologyDisplayEdgesVisible, surfaceStepEdgesVisible } = edges;
  const {
    partVisualStateRef, clipSettingsRef, staticSceneResetRef, meshSourceAdoptionRef, viewerAlertChangeRef,
    sceneUpdateAlertRef, lodCameraChangeRef, stepModuleTransformDetectedChangeRef
  } = refs;
  const meshGeometrySource = meshData?.geometrySource && typeof meshData.geometrySource === "object"
    ? meshData.geometrySource
    : meshData;

  // STEP's half of the look (`stepScene.setLookContext`): the build is dressed before the sync
  // below hands it a publish, which is the order the two have always run in.
  useEffect(() => {
    if (!runtimeRef.current) return;
    if (stepScene.setLookContext({
      theme: normalizedThemeSettings, appearance, materialSettings: normalizedMaterialSettings,
      materialOverrides, receiveShadows, surfaceSettings
    })) {
      runtimeRef.current.displayRecords = stepScene.displayRecords;
      runtimeRef.current.requestRender?.();
    }
  }, [appearance, materialOverrides, normalizedMaterialSettings, normalizedThemeSettings, receiveShadows, surfaceSettings,
    stepScene, viewerReadyTick]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }
    const { edgesGroup, facePickGroup, edgePickGroup, vertexPickGroup } = runtime;

    const clearDisplayedModel = ({ preserveModelIdentity = false, releaseGpu = true } = {}) => {
      staticSceneResetRef.current.invalidate();
      cancelCameraTransition(runtime);
      // Runtime-level teardown first: it certifies disposal (or throws and keeps the build
      // reachable for a retry); only then does the scene forget the build it released.
      const disposedSource = disposeViewerCadScene(runtime, { clearSceneGroup, preserveModelIdentity, releaseGpu });
      stepScene.release({ releaseGpu, preserveModelIdentity });
      runtime.requestRender();
      return disposedSource;
    };

    if (isLoading) {
      const disposedSource = clearDisplayedModel();
      meshSourceAdoptionRef.current?.(disposedSource, false, { disposed: true });
      setError("");
      return;
    }

    if (!hasMeshGeometry(meshData)) {
      const disposedSource = clearDisplayedModel();
      meshSourceAdoptionRef.current?.(disposedSource, false, { disposed: true });
      return;
    }

    try {
    const sceneSyncStartedAt = performance.now();
        const hasFillRotation = normalizedMaterialSettings.cycleColors === true &&
      Array.isArray(normalizedMaterialSettings.fillColors) &&
      normalizedMaterialSettings.fillColors.length > 1;
    const shouldRenderFillParts = hasFillRotation &&
      Array.isArray(meshData?.parts) &&
      meshData.parts.length > 0;
    const shouldRenderSourceColorParts =
      !wireframeMode &&
      normalizedMaterialSettings.overrideSourceColors !== true &&
      meshNeedsPartRenderingForSourceColors(meshData);
    const { renderParts: shouldRenderParts, parts: renderedParts } = resolveScenePartRendering({
      meshData,
      renderPartsIndividually: effectiveRenderPartsIndividually,
      fillRotationParts: shouldRenderFillParts,
      sourceColorParts: shouldRenderSourceColorParts,
      pickableParts,
      pickMode
    });
    const materialSettings = { ...normalizedMaterialSettings };
    const modelStepParameters = stepParameterRuntime?.definition
      ? {
          ...stepParameterRuntime,
          selectorRuntime
        }
      : null;

    const sceneTheme = wireframeMode && !explicitViewPolicy
      ? {
          ...normalizedThemeSettings,
          edges: {
            ...visualEdgeSettings,
            enabled: true
          }
        }
      : surfaceStepEdgesVisible
        ? {
            ...normalizedThemeSettings,
            edges: {
              ...visualEdgeSettings
            }
          }
        : {
          ...normalizedThemeSettings,
          edges: {
            enabled: false
          }
        };
    // Everything that decides how the scene's records are BUILT. While it holds
    // for the same model, a new mesh state (a progressive publish, a LOD swap)
    // is handed to the existing scene, which reconciles its records instead of
    // rebuilding them: occurrences already on screen keep their meshes,
    // materials, visual and deformation state and BVHs.
    const sceneBuildKey = sceneBuildStructuralKey({
      displayMode: normalizedDisplayMode,
      applyDisplayModeEdgePolicy: !explicitViewPolicy && !topologyDisplayEdgesVisible,
      sceneScaleMode: VIEWER_SCENE_SCALE.CAD,
      edgeSettings: sceneTheme.edges,
      recomputeNormals: false,
      silhouette: topologyDisplayEdgesVisible && displayEdgeSettings.silhouette === true
    });
    const sceneModelSettings = {
      appearance,
      surfaceSettings,
      parts: shouldRenderParts ? renderedParts : [],
      renderPartsIndividually: effectiveRenderPartsIndividually,
      stepParameters: modelStepParameters,
      selection: shouldRenderParts
        ? partVisualStateRef.current
        : {
            ...partVisualStateRef.current,
            hiddenPartIds: [],
            hoveredPartId: "",
            focusedPartId: [],
            selectedPartIds: []
      },
      clip: clipSettingsRef.current,
      callbacks: {
        faceIdsForPart: (part) => buildGlbFaceIdsForPart(part, selectorRuntime),
        faceIdsForMesh: () => buildGlbFaceIdsForMesh(meshData, selectorRuntime),
        onWarning: (warning) => {
          viewerAlertChangeRef.current?.({
            severity: "warning",
            compact: true,
            title: warning?.title || "CAD scene warning",
            message: warning?.message || "The CAD scene renderer reported a warning."
          });
        }
      },
      receiveShadows
    };
    const plan = stepScene.plan({ modelKey, buildKey: sceneBuildKey, viewerTheme });
    const reuseScene = plan.reuse;
    const rebuildReason = plan.reason;
    let cadScene;
    if (reuseScene) {
      cadScene = stepScene.update(meshData, {
        theme: sceneTheme,
        materialSettings,
        materialOverrides,
        ...sceneModelSettings
      });
    } else {
      // A rebuild of the SAME model (a display mode, a theme) keeps its components' GPU
      // buffers and BVHs; a model going away frees them.
      clearDisplayedModel({ releaseGpu: !plan.sameModel, preserveModelIdentity: plan.sameModel });
      cadScene = stepScene.build(meshData, { modelKey, buildKey: sceneBuildKey, viewerTheme }, {
        theme: sceneTheme,
        displayMode: normalizedDisplayMode,
        applyDisplayModeEdgePolicy: !explicitViewPolicy && !topologyDisplayEdgesVisible,
        scale: VIEWER_SCENE_SCALE.CAD,
        baseTheme: viewerTheme,
        materialSettings,
        materialOverrides,
        edgeSettings: visualEdgeSettings,
        recomputeNormals: false,
        silhouette: topologyDisplayEdgesVisible && displayEdgeSettings.silhouette === true,
        parameterSetup: false,
        edgeRendering: {
          mode: "screen-space",
          Line2: runtime.Line2,
          LineGeometry: runtime.LineGeometry,
          LineSegments2: runtime.LineSegments2,
          LineSegmentsGeometry: runtime.LineSegmentsGeometry,
          LineMaterial: runtime.LineMaterial,
          wireframeEdgeColor
        },
        ...sceneModelSettings
      });
    }
    // The viewport adopted the scene's root; its linework goes in the viewport's edge layer.
    if (stepScene.edgesObject3D.parent !== edgesGroup) edgesGroup.add(stepScene.edgesObject3D);
    runtime.cadScene = cadScene;
    runtime.displayRecords = cadScene.displayRecords;
    runtime.syncScreenSpaceLineMaterials?.();
    setDisplayRecordsToken((token) => token + 1);
    // The scene changed in place: the viewport re-reads what it placed, fits the stage and the
    // depth range to it, and applies the framing rules -- NOW, so the clip plane, the pick
    // groups and the passes after this one see the fitted stage.
    viewport.commitScene();
    const initialEdgeRuntimes = resolveTopologyDisplayEdgeRuntimes({
      selectorRuntime,
      displayEdgeRuntime,
      displayRecords: modelStepParameters ? runtime.displayRecords : [],
      transformDisplayEdges: false
    });
    const initialRecordTopologyEdgeTransforms = explodedViewActive || shouldUseRecordTopologyEdgeTransforms({
      transformDetected: initialEdgeRuntimes.transformCount > 0,
      topologyDisplayEdgesVisible,
      displayEdgeRuntime,
      displayRecords: runtime.displayRecords
    });
    const initialDisplayEdgeRuntime = initialRecordTopologyEdgeTransforms
      ? null
      : resolveTopologyDisplayEdgeRuntimes({
          selectorRuntime: null,
          displayEdgeRuntime,
          displayRecords: modelStepParameters ? runtime.displayRecords : []
        }).transformedDisplayEdgeRuntime;
    const initialSelectorRuntime = initialEdgeRuntimes.transformedSelectorRuntime;
    updateTransformedRuntimeState(setTransformedSelectorRuntime, initialSelectorRuntime ? {
      base: selectorRuntime,
      runtime: initialSelectorRuntime
    } : null);
    updateTransformedRuntimeState(setTransformedDisplayEdgeRuntime, initialDisplayEdgeRuntime ? {
      base: displayEdgeRuntime,
      runtime: initialDisplayEdgeRuntime
    } : null);
    stepModuleTransformDetectedChangeRef.current?.(initialEdgeRuntimes.transformCount > 0);
    const displaySelectorRuntime = initialEdgeRuntimes.selectorRuntime;
    const displayEdgesRuntime = initialRecordTopologyEdgeTransforms
      ? displayEdgeRuntime
      : (initialDisplayEdgeRuntime || initialEdgeRuntimes.topologyRuntime);
    runtime.topologyDisplayEdgeTransformByRecord = initialRecordTopologyEdgeTransforms;

    syncTopologyDisplayEdgeLine(runtime, displayEdgesRuntime, {
      visible: topologyDisplayEdgesVisible,
      edgeSettings: hiddenAwareVisualEdgeSettings,
      focusedPartIds,
      viewerTheme,
      dimmedOpacity: FOCUSED_DIMMED_SURFACE_OPACITY,
      transformByRecord: initialRecordTopologyEdgeTransforms,
      displayRecords: runtime.displayRecords,
      syncClip: (activeRuntime) => syncRuntimeStepClipPlane(activeRuntime, clipSettingsRef.current)
    });


    const modelOffset = MODEL_OFFSET;
    const radius = Number(runtime.modelRadius) || 1;
    facePickGroup.updateMatrixWorld(true);
    edgePickGroup.updateMatrixWorld(true);
    vertexPickGroup.updateMatrixWorld(true);
    // Refresh retained scene/GPU estimates before admitting idle BVH work.
    // A denied accelerator keeps stock raycasting and therefore cannot make
    // selection incorrect or blank the current model.
    const initialRenderMemory = renderMemoryAccounting(runtime);
    if (import.meta.env?.DEV && typeof document !== "undefined") {
      // Main-world diagnostic that browser automation can read even when its
      // JavaScript executes in an isolated extension world.
      document.documentElement.dataset.cadRenderMemory = JSON.stringify({
        displayCpuBytes: initialRenderMemory.displayCpuBytes,
        gpuEstimatedBytes: initialRenderMemory.gpuEstimatedBytes,
        bvhBytes: initialRenderMemory.bvhBytes,
        policy: initialRenderMemory.memoryPolicy
      });
    }
    const raycastBvhOptions = {
      deferUntilRaycast: true,
      reserveBuild: ({ estimatedBytes }) => viewerMemoryPolicy.reserve({
        category: "bvhBuild",
        bytes: estimatedBytes,
        label: "display raycast BVH",
        kind: "accelerator"
      }),
      finishBuild: (token, { builtBytes }) => {
        viewerMemoryPolicy.release(token);
        const current = viewerMemoryPolicy.snapshot().retainedByCategory.bvh || 0;
        viewerMemoryPolicy.setRetained("bvh", current + builtBytes);
      },
      onBuildDenied: (detail) => {
        if (typeof window !== "undefined") {
          window.__cadViewerMemoryLimitation = detail;
          window.dispatchEvent(new CustomEvent("cad:memory-limitation", { detail }));
        }
      }
    };
    runtime.raycastBvhOptions = raycastBvhOptions;
    syncSelectorPickGroups(runtime, displaySelectorRuntime, modelOffset, { clearSceneGroup });
    scheduleRuntimeRaycastBvh(runtime, raycastBvhOptions);
    syncRuntimeStepClipPlane(runtime, clipSettingsRef.current);

    const currentPartVisualState = partVisualStateRef.current;
    applyPartVisualState(THREE, runtime.displayRecords, shouldRenderParts
      ? currentPartVisualState
      : {
        ...currentPartVisualState,
        hiddenPartIds: [],
        hoveredPartId: "",
        focusedPartId: [],
        selectedPartIds: []
      });
    runtime.cadScene?.syncSurfaceInstances();
    runtime.modelGroup.updateMatrixWorld(true);
    edgesGroup.updateMatrixWorld(true);
    runtime.edgePickThreshold = Math.max(radius / 320, 0.65);

    recordSceneSyncTiming(sceneSyncStartedAt, { mode: reuseScene ? "reuse" : "rebuild", records: runtime.displayRecords.length, reason: rebuildReason });
    // A mode switch replaces the build. The parent's quality-change sample can arrive before
    // this scene is ready, so resample its framed camera on construction too; otherwise the
    // old quality remains until the next orbit.
    // (The sample itself is collected a beat later by the LOD scheduler, by which time the
    // viewport has framed the scene; asking again after the framing only restarts that beat.)
    if (!reuseScene) lodCameraChangeRef.current?.();
    setError("");
    runtime.requestRender();
    if (shouldRenderParts) {
      staticSceneResetRef.current.complete(staticResetRenderToken, {
        source: meshData, runtime, visualState: currentPartVisualState, clipState: clipSettingsRef.current,
      });
    }
    const adopted = runtime.cadScene === cadScene && stepScene.cadScene === cadScene && cadScene.source === meshData;
    if (meshSourceAdoptionRef.current?.(meshData, adopted) === false) {
      throw new Error("The displayed detail does not match its requested component occurrences.");
    }
    if (adopted && sceneUpdateAlertRef.current) {
      const recoveredAlert = sceneUpdateAlertRef.current;
      sceneUpdateAlertRef.current = null;
      // Clear this failure only after real adoption, preserving any newer
      // environment or animation alert that replaced it during recovery.
      viewerAlertChangeRef.current?.(current => current === recoveredAlert ? null : current);
    }
    } catch (error) {
      staticSceneResetRef.current.invalidate();
      if (error?.failedCadScene) {
        // Initial construction can fail before buildModel returns. Its typed
        // cleanup failure transfers the still-owned scene to this host.
        stepScene.holdFailedBuild(error.failedCadScene);
        runtime.cadScene = error.failedCadScene;
        runtime.displayRecords = error.failedCadScene.displayRecords;
      }
      // Reconciliation is in-place: a failure may have disposed old records
      // and attached new orphans. Full teardown precedes any recovery/release.
      let recovery;
      try {
        clearDisplayedModel();
        recovery = meshSourceAdoptionRef.current?.(meshData, false, { disposed: true, recover: true });
      } catch (cleanupError) {
        meshSourceAdoptionRef.current?.(meshData, false, { cleanupFailed: true });
        sceneUpdateAlertRef.current = { severity: "error", title: "Scene cleanup failed",
          message: "Detail work has stopped because scene ownership could not be released. Reload the viewer." };
        viewerAlertChangeRef.current?.(sceneUpdateAlertRef.current);
        setError(cleanupError instanceof Error ? cleanupError.message : String(cleanupError));
        return;
      }
      sceneUpdateAlertRef.current = { severity: "error", title: "Detail update failed",
        message: recovery?.recovering
          ? "The partial scene was cleared. The previous view is being restored; reload if restoration fails."
          : "The scene was cleared after the display failed. Reload the model to continue." };
      viewerAlertChangeRef.current?.(sceneUpdateAlertRef.current);
      setError(error instanceof Error ? error.message : String(error));
    }
  }, [
    meshGeometrySource,
    modelKey,
    surfaceStepEdgesVisible,
    topologyDisplayEdgesVisible,
    isLoading,
    viewerReadyTick,
    pickMode,
    effectiveRenderPartsIndividually,
    explodedViewActive,
    pickableParts,
    selectorRuntime,
    displayEdgeRuntime,
    normalizedDisplayMode,
    materialPartPolicyKey,
    surfaceSettings,
    explicitViewPolicy,
    receiveShadows,
    viewerTheme,
    displayEdgeSettings,
    hiddenAwareVisualEdgeSettings,
    visualEdgeSettings,
    wireframeEdgeColor,
    stepScene
  ]);
}

/**
 * The runtime under the scene is going away: release what STEP hung on it, and say so.
 *
 * This is the ONE owner of that release. The viewport tells its renderer exactly once, from
 * one place (`runtimeLifecycle.onRelease`), on a context loss, a runtime handoff and an
 * unmount alike — so `StepViewport` does not also release the scene from an unmount effect
 * of its own. Two owners firing parent-first only ever worked because `dispose()` happens to
 * be idempotent, which is a property to rely on in recovery, not a teardown design.
 *
 * `dispose()` (rather than `release()`) because the scene is leaving this runtime entirely:
 * it drops the build AND takes its roots out of the viewport's groups. It is not terminal —
 * React's development remount runs this cleanup and then the effects again over the same
 * scene, which simply builds into it once more.
 */
export function releaseStepRuntime(runtime, stepScene) {
  if (!runtime) {
    const source = stepScene.source;
    stepScene.dispose();
    return source;
  }
  disposeSectionCaps(runtime);
  const source = disposeViewerCadScene(runtime, { clearSceneGroup });
  stepScene.dispose();
  return source;
}

import { createStudioEnvironmentCache } from "../../kit/look/studioEnvironmentCache.js";
import { createViewUpdateGate } from "../../kit/view-settings/viewUpdateGate.js";
import { createInspectEnvironmentResource, hasAuthoredMaterials, INSPECT_ENVIRONMENT_ID } from "@hardcore/core/common/inspectEnvironment.js";
"use client";

import LoadingIndicator from "../../kit/status/LoadingIndicator.js";
import { disposeViewerCadScene } from "../render/lodSceneCleanup.js";
import { disposeSectionCaps } from "@hardcore/core/lib/viewer/sectionCaps.js";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { viewerTransitionBackdrop } from "../../kit/viewport/framePresentation.js";
import { STEP_TREE_TOPOLOGY_NODE_PREFIX } from "@hardcore/core/lib/step/stepTree.js";
import {
  CAMERA_PROJECTION,
  normalizeCameraProjection,
  perspectiveSnapshotEqual,
  perspectiveSnapshotMatchesScene,
  resolvePerspectiveSnapshot
} from "@hardcore/core/lib/perspective.js";
import { VIEWER_PICK_MODE } from "@hardcore/core/lib/viewer/constants.js";
import { resolveScenePartRendering } from "@hardcore/core/lib/viewer/partRendering.js";
import { hasMeshGeometry } from "@hardcore/core/lib/render/meshCost.js";
import { normalizeStepClipSettings } from "@hardcore/core/lib/viewer/clipPlane.js";
import {
  shouldBuildDerivedDisplayEdges,
  shouldShowRecordDisplayEdges
} from "@hardcore/core/lib/viewer/displayEdgePolicy.js";
import {
  displayModeForcesEdges,
  displayModeIsWireframe,
  displayModeShowsEdges,
  displayModeShowsThroughEdges
} from "@hardcore/core/lib/displaySettings.js";
import { resolveCadGridSettings } from "@hardcore/core/common/cadInk.js";
import { resolveDisplayMaterialSettings } from "@hardcore/core/common/sceneSettings.js";
// The photographic rig and its environment are Render's lazy chunk: this file
// reaches them through the boundary's synchronous accessor, never by a static
// import. `studioScene()` answering null means the chunk is still arriving, and
// the render-mode effects below leave `environmentReady` false while it is —
// framePresentation then keeps the canvas covered with the destination
// backdrop, so a half-configured photographic scene is never presented. The
// rig's material constants are plain data and stay in the initial chunk.
import { loadStudioScene, studioScene } from "../../kit/look/renderStudioChunk.js";
import { PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS } from "@hardcore/core/common/photographicStudioRig.js";
import {
  defaultSceneGridRadius,
  getSceneScaleSettings,
  normalizeSceneScaleMode,
  VIEWER_SCENE_SCALE
} from "@hardcore/core/lib/viewer/sceneScale.js";
import {
  applySceneBackground,
  BASE_VIEWER_THEME,
  disposeTexture,
  getViewerThemeValue,
  normalizeFloorMode,
  updateSpotLightTarget
} from "@hardcore/core/lib/viewer/stageTheme.js";
import {
  displayRecordsBounds,
  mergeBoundsList
} from "@hardcore/core/lib/viewer/autoZoom.js";
import { applyMaterialSettingsToRecord } from "@hardcore/core/lib/viewer/surfaceMaterials.js";
import {
  applyPartVisualState,
  FOCUSED_DIMMED_SURFACE_OPACITY,
  normalizePartIdList,
  referenceMatchesFocusedPart
} from "@hardcore/core/lib/viewer/partVisualState.js";
import {
  createRecordTopologyDisplayEdgeGroup,
  syncRecordTopologyDisplayEdgeTransforms,
  syncTopologyDisplayEdgeLine
} from "@hardcore/core/lib/viewer/topologyDisplayEdgeLine.js";
import {
  applyExplodedViewProgress,
  clearExplodedViewRecords,
  computeExplodedViewLayout,
  easeExplodedViewProgress
} from "@hardcore/core/lib/viewer/explodedView.js";
import {
  applyDisplayRecordTransform,
  applyRuntimeModelBounds,
  sceneRadiusForBounds,
  readBoundsCenter,
  resolveRuntimeModelFloorZ,
  runtimeModelKeyMatches,
  syncRuntimeStepClipPlane,
  toNumber
} from "@hardcore/core/lib/viewer/modelRuntime.js";
import {
  buildGlbFaceIdsForMesh,
  buildGlbFaceIdsForPart,
  syncDisplayMeshFaceIds,
  syncSelectorPickGroups
} from "@hardcore/core/lib/viewer/selectorPickGroups.js";
import { scheduleRuntimeRaycastBvh } from "@hardcore/core/lib/viewer/raycastBvh.js";
import { renderMemoryAccounting } from "../render/renderMemoryAccounting.js";
import { viewerMemoryPolicy } from "../render/viewerMemoryPolicy.js";
import { inactiveExplodedViewNeedsReset } from "../render/explodedViewLifecycle.js";
import {
  createStaticSceneReset,
  sceneSourceAlreadyPlaced,
  staticSceneResetEligible
} from "../render/staticSceneReset.js";
import { sampleLodCamera, resampleLodAfterViewportResize } from "../render/lodCameraSample.js";
import { sceneBuildStructuralKey } from "../render/sceneBuildSettings.js";
import {
  buildCompositeScreenshotBlob,
  resolveElementBackgroundColor
} from "@hardcore/core/lib/viewer/screenshotCapture.js";
import {
  buildEdgeLinePositionsFromProxy,
  buildFaceBoundaryLinePositions,
  buildFaceFillGeometryFromDisplayMeshes,
  buildFaceFillGeometryFromProxy,
  buildVertexMarkerMesh,
  referenceExplodedViewMatrix,
  REFERENCE_CORNER_COLOR,
  REFERENCE_HIGHLIGHT_WIDTH_MULTIPLIER,
  REFERENCE_SELECTED_COLOR
} from "@hardcore/core/lib/viewer/referenceGeometry.js";
import { buildRuntimeInitializationAlert } from "@hardcore/core/lib/viewer/webglSupport.js";
import { hasCapability } from "@hardcore/core/lib/renderCapabilities.js";
import {
  THEME_FLOOR_MODES
} from "@hardcore/core/lib/themeSettings.js";
import ViewPlaneControl from "../../kit/camera/ViewPlaneControl.js";
import DrawingOverlay from "../../kit/tools/draw/DrawingOverlay.jsx";
import JointHandleOverlay from "../../kit/tools/pose/JointHandleOverlay.jsx";
import { usePlaybackFrames } from "../../kit/tools/playbar/usePlaybackFrames.js";
import { useDrawingViewLock } from "../../kit/tools/draw/useDrawingViewLock.js";
import { useAnimationClockStore } from "../workbench/animationClockStore.js";
import { useViewerMeasureOverlay } from "./viewer/hooks/useViewerMeasureOverlay.js";
import { useViewerPicking } from "./viewer/hooks/useViewerPicking.js";
import { useViewerRuntime } from "../../kit/viewport/useViewerRuntime.js";
import { PREVIEW_AUTO_ROTATE_SPEED } from "../../kit/camera/orbitControls.js";
import {
  CAD_DEFAULT_VERTICAL_FOV_DEGREES,
  explicitViewerFocalLength,
  perspectiveDistanceScale
} from "../../kit/camera/cameraLens.js";
import {
  applyOrbitDelta,
  cameraMatchesViewPreset,
  clamp,
  clearKeyboardOrbitState,
  DEFAULT_VIEW_DIRECTION,
  DEFAULT_VIEW_PLANE_ORIENTATION,
  getActiveViewPlaneFaceId,
  getKeyboardOrbitAxes,
  getKeyboardOrbitCommand,
  isPinchWheelEvent,
  isTrackpadLikeWheelEvent,
  KEYBOARD_ORBIT_NUDGE_RAD,
  readViewPlaneOrientation,
  reframeReason,
  runtimeFramingBounds,
  stepKeyboardOrbit,
  WHEEL_PINCH_DELTA_BOOST,
  VIEWING_MODE,
  VIEW_PLANE_DEFAULT_PRESET,
  VIEW_PLANE_FACE_BY_ID,
  VIEW_PLANE_FACES,
  viewPlaneOrientationEqual,
  WORLD_UP
} from "../../kit/camera/viewportCameraKit.js";
import { createViewerRenderStateResolver } from "../../kit/view-settings/renderState.js";
import { buildModel } from "@hardcore/core/common/cadScene.js";
import {
  resolveTopologyDisplayEdgeRuntimes,
  shouldRenderTopologyDisplayEdges,
  shouldUseRecordTopologyEdgeTransforms
} from "@hardcore/core/common/topologyDisplayEdgeRuntime.js";
import {
  createScreenSpaceLineSegments,
  createTopologyDisplayEdgeObject as createSharedTopologyDisplayEdgeObject,
  topologyLineDepthBiasForWidth
} from "@hardcore/core/common/renderEdges.js";
import {
  resolveStepModuleFeatures
} from "@hardcore/core/common/stepModule.js";
import {
  buildStepModuleContext,
  createStepModuleEffectsApi,
  displayTransformForPart,
  resetStepModuleRecordEffects
} from "@hardcore/core/common/stepModuleEffects.js";
import { applySceneState } from "@hardcore/core/common/applySceneState.js";
import {
  DEFAULT_DAMPING_FACTOR,
  readOrthographicHalfHeight,
  boundsModelRadius,
  resetRuntimeZoomBaseline,
  readRuntimeZoomPercent,
  setRuntimeZoomPercent,
  syncRuntimeCameraClipPlanes,
  captureRuntimeViewportFitScale,
  syncRuntimeViewportFraming,
  syncRuntimeCameraProjection,
  readPerspectiveSnapshot,
  setRuntimePerspectiveFocalLength,
  cancelCameraTransition,
  applyPerspectiveSnapshot,
  transitionCameraToPerspectiveSnapshot,
  recenterRuntimeTarget,
  zoomRuntimeToBounds,
  stepCameraTransition,
  transitionCameraToViewPreset,
  readScopedPerspectiveSnapshot
} from "../../kit/camera/runtimeCamera.js";
import {
  IDLE_PIXEL_RATIO_CAP,
  INTERACTION_PIXEL_RATIO_CAP,
  INTERACTION_IDLE_DELAY_MS,
  getPixelRatioCap
} from "../../kit/viewport/pixelRatio.js";
import {
  disposeSceneObject
} from "../../kit/viewport/sceneObjects.js";
import {
  DEFAULT_ZOOM_SPEED,
  COARSE_POINTER_ZOOM_SPEED,
  ACCELERATED_WHEEL_ZOOM_SPEED,
  TRACKPAD_PINCH_ZOOM_SPEED,
  COARSE_POINTER_PINCH_ZOOM_SPEED
} from "../../kit/camera/zoomSpeeds.js";
import {
  DEFAULT_LIGHTING,
  syncRuntimeScaledLightingAndShadow,
  updateStageEffects,
  updateGridHelper
} from "../../kit/look/stageEffects.js";
import { useViewportCamera } from "../../kit/camera/useViewportCamera.js";

const EXPLODED_VIEW_ANIMATION_DURATION_MS = 1000;
const CAD_COORDINATE_SYSTEM = "cad-z-up-v1";
const VIEW_PLANE_CONTROL_SIZE = "6rem";
const CAD_EDGE_OPACITY = 0.84;

function referenceSelectorType(reference) {
  return String(reference?.selectorType || "").trim();
}

function referenceOccurrenceSelector(reference) {
  const selectorType = referenceSelectorType(reference);
  if (selectorType === "occurrence") {
    return String(reference?.normalizedSelector || reference?.displaySelector || "").trim();
  }
  return String(reference?.occurrenceId || "").trim();
}

function referenceMatchesOccurrenceSubtree(reference, occurrenceSelector) {
  const candidate = referenceOccurrenceSelector(reference);
  const selector = String(occurrenceSelector || "").trim();
  return Boolean(candidate && selector && (candidate === selector || candidate.startsWith(`${selector}.`)));
}

function referenceShapeSelector(reference) {
  const selectorType = referenceSelectorType(reference);
  if (selectorType === "shape") {
    return String(reference?.normalizedSelector || reference?.displaySelector || "").trim();
  }
  return String(reference?.shapeId || "").trim();
}

function referenceMatchesShape(reference, shapeSelector, occurrenceSelector = "") {
  const candidate = referenceShapeSelector(reference);
  const selector = String(shapeSelector || "").trim();
  if (!candidate || !selector || candidate !== selector) {
    return false;
  }
  const occurrence = String(occurrenceSelector || "").trim();
  return !occurrence || referenceMatchesOccurrenceSubtree(reference, occurrence);
}

function syntheticOccurrenceSelectorFromReferenceId(referenceId) {
  const normalizedReferenceId = String(referenceId || "").trim();
  if (!normalizedReferenceId.startsWith(STEP_TREE_TOPOLOGY_NODE_PREFIX)) {
    return "";
  }
  const body = normalizedReferenceId.slice(STEP_TREE_TOPOLOGY_NODE_PREFIX.length);
  const marker = ":occurrence:";
  const markerIndex = body.lastIndexOf(marker);
  return markerIndex >= 0 ? body.slice(markerIndex + marker.length).trim() : "";
}

function isNumericArray(value, stride = 1) {
  return (
    (Array.isArray(value) || ArrayBuffer.isView(value)) &&
    value.length >= stride &&
    value.length % stride === 0
  );
}

function renderableMeshParts(meshData) {
  return Array.isArray(meshData?.parts)
    ? meshData.parts.filter((part) => toNumber(part?.vertexCount) > 0 && toNumber(part?.triangleCount) > 0)
    : [];
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

function transformedRuntimeStateEqual(current, next) {
  return (
    (current?.base || null) === (next?.base || null) &&
    (current?.runtime || null) === (next?.runtime || null)
  );
}

function updateTransformedRuntimeState(setState, next) {
  setState((current) => (
    transformedRuntimeStateEqual(current, next) ? current : next
  ));
}

function cancelExplodedViewAnimation(animationRef) {
  const animation = animationRef?.current;
  if (!animation?.rafId || typeof window === "undefined") {
    return;
  }
  window.cancelAnimationFrame(animation.rafId);
  animation.rafId = 0;
}

function displayRecordExplodedViewTranslation(THREE, record) {
  const elements = record?.explodedViewMatrix?.elements;
  if (!THREE?.Vector3 || !elements || elements.length < 16) {
    return THREE?.Vector3 ? new THREE.Vector3() : null;
  }
  return new THREE.Vector3(
    toNumber(elements[12]),
    toNumber(elements[13]),
    toNumber(elements[14])
  );
}

function applyExplodedViewRuntimeProgress(runtime, layout, progress) {
  if (!runtime?.THREE || !Array.isArray(runtime.displayRecords)) {
    return;
  }
  applyExplodedViewProgress(runtime.THREE, layout, progress);
  for (const record of runtime.displayRecords) {
    applyDisplayRecordTransform(runtime.THREE, record);
  }
  runtime.modelGroup?.updateMatrixWorld?.(true);
  runtime.edgesGroup?.updateMatrixWorld?.(true);
  if (runtime.topologyDisplayEdgeTransformByRecord === true) {
    syncRecordTopologyDisplayEdgeTransforms(runtime, runtime.displayRecords);
  }
  runtime.requestRender?.();
}

function coordinateSystemForSceneScale() {
  return CAD_COORDINATE_SYSTEM;
}

// Which coordinate system a stored camera belongs to is this renderer's knowledge;
// the kit's camera hook is handed the rule.
const coordinateSystemFor = coordinateSystemForSceneScale;

function pointBounds(center) {
  if (!Array.isArray(center) && !ArrayBuffer.isView(center)) {
    return null;
  }
  const x = toNumber(center[0]);
  const y = toNumber(center[1]);
  const z = toNumber(center[2]);
  return {
    min: [x, y, z],
    max: [x, y, z]
  };
}

function selectorReferenceForId(selectorRuntime, referenceId) {
  const id = String(referenceId || "").trim();
  if (!id || !selectorRuntime) {
    return null;
  }
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
    const bounds = mergeBoundsList([bbox]) ||
      pointBounds(reference?.pickData?.center || reference?.center);
    if (bounds) {
      boundsList.push(bounds);
    }
  }
  return mergeBoundsList(boundsList);
}

function currentDisplayRecordTranslationByRecord(THREE, records = []) {
  const translations = new Map();
  if (!THREE?.Vector3) {
    return translations;
  }
  for (const record of Array.isArray(records) ? records : []) {
    const translation = displayRecordExplodedViewTranslation(THREE, record);
    if (translation?.isVector3 && translation.lengthSq() > 1e-12) {
      translations.set(record, translation);
    }
  }
  return translations;
}

function displayRecordBoundsForPartIds(runtime, partIds = []) {
  const normalizedPartIds = normalizePartIdList(partIds);
  if (!normalizedPartIds.length || !Array.isArray(runtime?.displayRecords)) {
    return null;
  }
  return displayRecordsBounds(runtime.displayRecords, {
    partIds: new Set(normalizedPartIds),
    translationByRecord: currentDisplayRecordTranslationByRecord(runtime?.THREE, runtime.displayRecords)
  });
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

// Why a live scene was rebuilt rather than reused: the build-key fields that
// changed (for the timing seam above).
function sceneBuildKeyDifference(previous, next, runtime, modelKey) {
  const reasons = [];
  if (!runtime.hasVisibleModel) {
    reasons.push("no visible model");
  }
  if (runtime.activeModelKey !== (modelKey || "")) {
    reasons.push("model key");
  }
  if (previous.viewerTheme !== next.viewerTheme) {
    reasons.push("viewer theme");
  }
  if (previous.key !== next.key) {
    try {
      const before = JSON.parse(previous.key || "{}");
      const after = JSON.parse(next.key || "{}");
      for (const field of new Set([...Object.keys(before), ...Object.keys(after)])) {
        if (JSON.stringify(before[field]) !== JSON.stringify(after[field])) {
          reasons.push(field);
        }
      }
    } catch {
      reasons.push("build key");
    }
  }
  return reasons.join(",");
}

function clearSceneGroup(group) {
  for (const child of [...group.children]) disposeSceneObject(child);
}

function getEdgeThickness(edgeSettings = null, viewerTheme = null) {
  const fallbackThickness = Number.isFinite(Number(viewerTheme?.edgeThickness))
    ? Number(viewerTheme.edgeThickness)
    : BASE_VIEWER_THEME.edgeThickness;
  return Number.isFinite(Number(edgeSettings?.thickness))
    ? clamp(Number(edgeSettings.thickness), 0.5, 6)
    : fallbackThickness;
}

function getHighlightEdgeThickness(edgeSettings = null, viewerTheme = null) {
  return Number.isFinite(Number(edgeSettings?.highlightThickness))
    ? clamp(Number(edgeSettings.highlightThickness), 0.5, 6)
    : Math.max(getEdgeThickness(edgeSettings, viewerTheme) * REFERENCE_HIGHLIGHT_WIDTH_MULTIPLIER, 2);
}

function getHighlightEdgeOpacity(edgeSettings = null) {
  return Number.isFinite(Number(edgeSettings?.highlightOpacity))
    ? clamp(Number(edgeSettings.highlightOpacity), 0, 1)
    : 1;
}

function getHighlightEdgeColor(edgeSettings = null) {
  return String(edgeSettings?.highlightColor || REFERENCE_SELECTED_COLOR).trim() || REFERENCE_SELECTED_COLOR;
}

function disposeOverlayChild(runtime, child) {
  if (!child) {
    return;
  }
  while (child.children?.length) {
    const nested = child.children[0];
    child.remove(nested);
    disposeOverlayChild(runtime, nested);
  }
  if (typeof child.userData?.beforeDispose === "function") {
    child.userData.beforeDispose(child);
    delete child.userData.beforeDispose;
  }
  const materials = Array.isArray(child.material) ? child.material : [child.material];
  if (child.userData?.disposeGeometry !== false) {
    child.geometry?.dispose?.();
  }
  if (child.userData?.disposeMaterial !== false) {
    for (const material of materials) {
      material?.dispose?.();
    }
  }
}

function clearOverlayGroup(runtime, group) {
  while (group?.children?.length) {
    const child = group.children[group.children.length - 1];
    if (!child) {
      continue;
    }
    group.remove(child);
    disposeOverlayChild(runtime, child);
  }
  if (group) {
    group.visible = false;
  }
}


// What the viewport releases at teardown is this renderer's: its section caps and
// its scene (naming the released source), then the studio. The studio lives in
// Render's lazy chunk. A runtime can only be holding studio resources if that chunk
// loaded, so teardown asks the boundary rather than importing it. Inspect's small
// reflection fill owns its own disposable texture.
function disposeRuntimeCadScene(runtime) {
  disposeSectionCaps(runtime);
  return disposeViewerCadScene(runtime, { clearSceneGroup });
}

function disposeRuntimeStudio(runtime) {
  studioScene()?.disposePhotographicStudio(runtime);
}

const CadViewer = forwardRef(function CadViewer({
  meshData,
  modelKey,
  renderFormat = "",
  onCameraZoomPercentChange = null,
  perspective = null,
  perspectiveRef = null,
  projection = CAMERA_PROJECTION.PERSPECTIVE,
  focalLength = null,
  showEdges,
  recomputeNormals,
  theme = BASE_VIEWER_THEME,
  themeSettings = null,
  materialOverrides = null,
  receiveShadows = false,
  renderMode = false,
  appearance = "light",
  renderConfiguration = null,
  quality = null,
  floorModeOverride = "",
  previewMode = false,
  // Watching, not inspecting: the Animate tool, or fullscreen. Nothing under the pointer is
  // pickable for the whole mode, and leaving it returns the model to rest, so every piece
  // of pick-only state can stand still at rest pose while the mode lasts.
  animateMode = false,
  // The Pose tool: the joints that can be dragged, in model space, for the pose
  // on screen (`workbench/jointHandles.js`); `null` while the tool is off. The
  // knobs are the only thing under the pointer, so the model itself picks nothing.
  jointHandles = null,
  previewOrbitSpeed = 1,
  showViewPlane = true,
  viewPlaneOffsetRight = 16,
  viewPlaneOffsetBottom = 16,
  viewPlaneHeader = null,
  compactViewPlane = false,
  isLoading = false,
  presentationKey = "",
  onPresentationChange = null,
  viewUpdate = null,
  loadingPresentation = null,
  pickMode = VIEWER_PICK_MODE.AUTO,
  renderPartsIndividually = false,
  scale = "",
  sceneScaleMode = VIEWER_SCENE_SCALE.CAD,
  pickableParts = [],
  hiddenPartIds = [],
  selectedPartIds = [],
  hoveredPartId = "",
  hoveredReferenceId = "",
  selectedReferenceIds = [],
  selectorRuntime = null,
  displayEdgeRuntime = null,
  stepParameters = null,
  stepAnimation = null,
  pickableFaces = [],
  pickableEdges = [],
  pickableVertices = [],
  focusedPartId = "",
  displaySettings = null,
  drawingEnabled = false,
  drawing = null,
  onPerspectiveChange,
  onLodCameraChange,
  onMeshSourceAdoption,
  onHoverReferenceChange,
  onActivateReference,
  onDoubleActivateReference,
  onContextReference,
  onMeasurePick,
  onMeasureHoverPoint,
  activeMeasurementId = "",
  measureState = null,
  measureModeActive = false,
  allowMeshVertexSnap = false,
  onViewerAlertChange,
  onStepModuleTransformDetectedChange,
}, ref) {
  const stepParameterRuntime = stepParameters;
  // The animation runtime is {clip, elapsedSec, playing} or null. Null means the
  // model has no clip selected, and the evaluator never runs.
  const stepAnimationRuntime = stepAnimation;
  const stepAnimationPlaying = Boolean(stepAnimationRuntime?.playing);
  // Fresh even when every prop is unchanged: a receipt can skip only the
  // duplicate reset in this render, never work triggered by a later render.
  const staticResetRenderToken = {};
  const staticSceneResetRef = useRef(null);
  if (!staticSceneResetRef.current) staticSceneResetRef.current = createStaticSceneReset();
  useEffect(() => () => staticSceneResetRef.current.reset(), []);
  // What counts as "something is on screen" for overlays and the view cube.
  const viewportContent = meshData;
  const hasViewportContent = !!viewportContent;
  const normalizedSceneScaleMode = normalizeSceneScaleMode(scale || sceneScaleMode);
  const normalizedProjection = normalizeCameraProjection(projection);
  const meshGeometrySource = meshData?.geometrySource && typeof meshData.geometrySource === "object"
    ? meshData.geometrySource
    : meshData;
  const defaultGridRadius = defaultSceneGridRadius(normalizedSceneScaleMode);
  const interactionHostRef = useRef(null);
  const mountRef = useRef(null);
  const measureCanvasRef = useRef(null);
  const jointHandleLayoutRef = useRef(null);
  // The snap indicator needs the live hover point every frame; the workspace
  // only needs to know which entity is under the cursor. Keeping the point in a
  // ref lets the overlay track smoothly without re-rendering on every move.
  const measureHoverRef = useRef(null);
  const perspectiveChangeRef = useRef(onPerspectiveChange);
  const lodCameraChangeRef = useRef(onLodCameraChange);
  lodCameraChangeRef.current = onLodCameraChange;
  const lodSelectedPartIdsRef = useRef(selectedPartIds);
  lodSelectedPartIdsRef.current = selectedPartIds;
  const lodSelectionKey = normalizePartIdList(selectedPartIds).join("\u0000");
  const meshSourceAdoptionRef = useRef(onMeshSourceAdoption);
  meshSourceAdoptionRef.current = onMeshSourceAdoption;

  const viewerAlertChangeRef = useRef(onViewerAlertChange);
  const sceneUpdateAlertRef = useRef(null);
  // The last { title, message } the scene-effects pass raised, so it can be
  // deduplicated across frames and cleared when a pass runs clean.
  const sceneEffectsAlertRef = useRef(null);
  const stepModuleTransformDetectedChangeRef = useRef(onStepModuleTransformDetectedChange);
  const lastEmittedPerspectiveRef = useRef(null);
  const lastProjectionRef = useRef(normalizedProjection);
  const suppressPerspectiveEventsRef = useRef(0);
  const runtimeRef = useRef(null);
  const viewUpdateBindingRef = useRef(null);
  viewUpdateBindingRef.current = viewUpdate?.binding;
  useLayoutEffect(() => {
    const runtime = runtimeRef.current;
    if (runtime && viewUpdate?.revision) {
      runtime.viewUpdateGate ??= createViewUpdateGate(runtime);
      runtime.viewUpdateGate.hold();
    }
  }, [viewUpdate?.revision]);
  const explodedViewAnimationRef = useRef({
    rafId: 0,
    progress: 0,
    modelKey: "",
    enabled: false,
    layout: null
  });
  const framedModelKeyRef = useRef("");
  const framedZeroPoseBoundsRef = useRef(null);
  // The viewing mode this view was framed in. Inspect's orthographic CAD
  // frustum and Render's photographic lens are two cameras, so each one fits
  // the zero pose itself rather than inheriting the other's pose and zoom.
  const framedViewingModeRef = useRef("");
  // The model key this view was framed against once every component had
  // arrived. A progressive load frames on the first publish so something is on
  // screen immediately, and that first batch is a fraction of the model.
  const framedCompleteModelKeyRef = useRef("");
  const modelTransformRef = useRef({
    modelKey: "",
    sceneScaleMode: "",
    offset: null,
    floorZ: null
  });
  const clipSettingsRef = useRef(normalizeStepClipSettings(null));
  const selectorRuntimeRef = useRef(selectorRuntime);
  const displayEdgeRuntimeRef = useRef(displayEdgeRuntime);
  const stepModuleCleanupRef = useRef([]);
  const [transformedSelectorRuntime, setTransformedSelectorRuntime] = useState(null);
  const [transformedDisplayEdgeRuntime, setTransformedDisplayEdgeRuntime] = useState(null);
  const [defaultPerspectiveDetached, setDefaultPerspectiveDetached] = useState(false);
  const [error, setError] = useState("");
  const [viewerReadyTick, setViewerReadyTick] = useState(0);
  const [runtimeResetToken, setRuntimeResetToken] = useState(0);
  const presentationEpoch = useMemo(() => ({}), [runtimeResetToken]);
  const [presentedEpoch, setPresentedEpoch] = useState(null);
  const [presentedKey, setPresentedKey] = useState("");
  const resolvedPresentationKey = String(presentationKey || modelKey || "");
  const presentationRequestRef = useRef({ key: "", ready: false });
  const handleFramePresented = useCallback((key) => {
    setPresentedEpoch(presentationEpoch);
    setPresentedKey(String(key || ""));
  }, [presentationEpoch]);
  useLayoutEffect(() => {
    // Cover only an actual context recovery. View edits reuse the live canvas.
    const canvas = runtimeRef.current?.renderer?.domElement;
    if (canvas) canvas.style.visibility = "hidden";
  }, [presentationEpoch]);
  useLayoutEffect(() => {
    presentationRequestRef.current = { key: resolvedPresentationKey, ready: false };
  }, [presentationEpoch, resolvedPresentationKey]);
  const markPresentationReady = useCallback((runtime) => {
    if (!runtime || !resolvedPresentationKey) return;
    presentationRequestRef.current = { key: resolvedPresentationKey, ready: true };
    runtime.requestRender?.();
  }, [resolvedPresentationKey]);
  const [activeViewPlaneFace, setActiveViewPlaneFace] = useState("");
  const [viewPlaneOrientation, setViewPlaneOrientation] = useState(DEFAULT_VIEW_PLANE_ORIENTATION);
  const [cameraZoomPercent, setCameraZoomPercent] = useState(100);
  // Bumped whenever the exploded view reaches a POSE it will hold: the end of the
  // explode/collapse animation, a slider scrub, or a collapse back to rest. Overlays that bake
  // a record's matrix at build time -- the reference highlight's edge lines and its face fill --
  // re-read it here. Without it the highlight keeps the pose it was built against and only
  // corrects itself when the pointer next moves, which reads as the highlight being wrong.
  const [explodedViewPoseTick, setExplodedViewPoseTick] = useState(0);
  // Bumped every time the scene is rebuilt and `runtime.displayRecords` becomes a fresh set of
  // objects. State baked ONTO records rather than into React -- the exploded view's per-record
  // matrix -- is lost by that rebuild and has to be re-applied. The scene rebuilds for reasons
  // the exploded view knows nothing about (a topology load, an edge setting, part pickability),
  // so this is a signal rather than a longer dependency list: the last attempt at a dependency
  // list is why isolating a part while exploded collapsed the model.
  const [displayRecordsToken, setDisplayRecordsToken] = useState(0);
  // The build settings the live cadScene was built with (see the scene sync effect).
  const sceneBuildRef = useRef({ key: "", viewerTheme: null });
  const activeViewPlaneFaceRef = useRef("");
  const defaultPerspectiveResettingRef = useRef(false);
  const previewModeRef = useRef(previewMode);
  // The presentation camera never becomes the file's persisted camera. Retain
  // its original framing as well as its pose, so fullscreen resize/orbit cannot
  // change the zoom ruler or the regular viewport's resize behavior.
  const fullscreenCameraRef = useRef(null);
  const perspectivePropRef = useRef(perspective);
  const modelKeyRef = useRef(modelKey);
  const sceneScaleModeRef = useRef(normalizedSceneScaleMode);
  const activeSelectorRuntime = transformedSelectorRuntime?.base === selectorRuntime
    ? transformedSelectorRuntime.runtime
    : selectorRuntime;
  const activeDisplayEdgeRuntime = transformedDisplayEdgeRuntime?.base === displayEdgeRuntime
    ? transformedDisplayEdgeRuntime.runtime
    : displayEdgeRuntime;
  const viewerTheme = theme || BASE_VIEWER_THEME;
  const resolveViewerRenderState = useMemo(() => createViewerRenderStateResolver(), []);
  const normalizedViewerRenderState = useMemo(() => resolveViewerRenderState({
    themeSettings,
    displaySettings
  }), [resolveViewerRenderState, themeSettings, displaySettings]);
  const normalizedThemeSettings = normalizedViewerRenderState.themeSettings;
  const normalizedDisplaySettings = normalizedViewerRenderState.displaySettings;
  const normalizedDisplayMode = normalizedViewerRenderState.displayMode;
  const surfaceSettings = normalizedDisplaySettings.surfaces;
  const explicitViewPolicy = Boolean(surfaceSettings);
  const photographicLighting = renderMode && renderConfiguration?.lighting?.enabled !== false;
  const normalizedMaterialSettings = useMemo(
    () => resolveDisplayMaterialSettings(
      photographicLighting ? PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS : normalizedThemeSettings.materials,
      normalizedDisplaySettings.partColor
    ),
    [normalizedDisplaySettings.partColor, normalizedThemeSettings.materials, photographicLighting]
  );
  const materialPartPolicyKey = `${
    normalizedMaterialSettings.cycleColors === true &&
    Array.isArray(normalizedMaterialSettings.fillColors) &&
    normalizedMaterialSettings.fillColors.length > 1
  }:${normalizedMaterialSettings.overrideSourceColors === true}`;
  const normalizedExplodedSettings = normalizedDisplaySettings.exploded;
  const explodeAmount = clamp(toNumber(normalizedExplodedSettings.amount, 1), 0, 1);
  const explodablePartCount = useMemo(() => renderableMeshParts(meshData).length, [meshData]);
  const explodedViewActive = normalizedExplodedSettings.enabled && explodablePartCount > 1;
  const effectiveRenderPartsIndividually = renderPartsIndividually ||
    explodedViewActive;
  useLayoutEffect(() => {
    const explosion = explodedViewAnimationRef.current;
    staticSceneResetRef.current.beginRender(staticResetRenderToken, staticSceneResetEligible({
      source: meshData,
      renderFormat,
      parameters: stepParameterRuntime,
      animation: stepAnimationRuntime,
      exploded: explodedViewActive || explosion.enabled || explosion.rafId || Number(explosion.progress) !== 0,
      loading: isLoading,
      records: runtimeRef.current?.displayRecords || [],
    }));
  });
  // CAD edges come from the topology package, so this is the `topology` capability, not
  // "is this STEP". A second format that ships topology inherits the edge rendering.
  const shouldUseCadEdgeSource = hasCapability(renderFormat, "topology");
  const displayEdgeSettings = normalizedViewerRenderState.edgeSettings;
  const wireframeMode = displayModeIsWireframe(normalizedDisplayMode);
  const displayModeForceEdges = !explicitViewPolicy && displayModeForcesEdges(normalizedDisplayMode);
  const displayModeThroughEdges = !explicitViewPolicy && displayModeShowsThroughEdges(normalizedDisplayMode);
  const wireframeEdgeColor = displayEdgeSettings.color;
  const wireframeEdgeOpacity = useMemo(() => {
    const baseOpacity = Number.isFinite(Number(displayEdgeSettings?.opacity))
      ? clamp(Number(displayEdgeSettings.opacity), 0, 1)
      : (viewerTheme?.edgeOpacity ?? BASE_VIEWER_THEME.edgeOpacity ?? CAD_EDGE_OPACITY);
    return Math.max(baseOpacity, 0.9);
  }, [displayEdgeSettings, viewerTheme]);
  const visualEdgeSettings = useMemo(() => {
    const forcedSettings = {
      ...displayEdgeSettings,
      enabled: displayModeForceEdges ? true : displayEdgeSettings.enabled,
      depthTest: displayModeThroughEdges ? false : displayEdgeSettings.depthTest
    };
    return wireframeMode
      ? {
          ...forcedSettings,
          color: wireframeEdgeColor,
          opacity: wireframeEdgeOpacity
        }
      : forcedSettings;
  }, [
    displayEdgeSettings,
    displayModeForceEdges,
    displayModeThroughEdges,
    wireframeEdgeColor,
    wireframeEdgeOpacity,
    wireframeMode
  ]);
  const focusedPartIds = useMemo(() => normalizePartIdList(focusedPartId), [focusedPartId]);
  const focusedPartIdSet = useMemo(() => new Set(focusedPartIds), [focusedPartIds]);
  const hiddenPartIdSet = useMemo(() => new Set(normalizePartIdList(hiddenPartIds)), [hiddenPartIds]);
  const hiddenAwareVisualEdgeSettings = useMemo(() => {
    const hiddenIds = normalizePartIdList(hiddenPartIds);
    if (!hiddenIds.length) {
      return visualEdgeSettings;
    }
    const excludePartIds = [
      ...new Set([
        ...normalizePartIdList(visualEdgeSettings?.excludePartIds),
        ...hiddenIds
      ])
    ];
    return {
      ...visualEdgeSettings,
      excludePartIds
    };
  }, [hiddenPartIds, visualEdgeSettings]);
  const normalizedClipSettings = normalizedViewerRenderState.clipSettings;
  const floorSettings = normalizedThemeSettings.floor || {};
  const guideFloorSettings = useMemo(() => ({
    ...floorSettings,
    grid: resolveCadGridSettings(normalizedDisplaySettings.guides.grid, { colorMode: appearance }),
    axis: normalizedDisplaySettings.guides.axis
  }), [floorSettings, normalizedDisplaySettings.guides, appearance]);
  const defaultFloorMode = floorSettings.enabled === true
    ? THEME_FLOOR_MODES.STAGE
    : THEME_FLOOR_MODES.NONE;
  const resolvedFloorMode = floorModeOverride
    ? normalizeFloorMode(floorModeOverride, defaultFloorMode)
    : defaultFloorMode;
  // Floor-dependent placement is inert without a floor: followModel may only
  // act when the stage floor is enabled. Grid/axis-only canvases (workbench,
  // terminal) stay pinned to the true z=0 plane so the model reads against its
  // authored coordinates. Normalization enforces the same rule; this guard
  // keeps the invariant local for raw settings.
  const floorFollowsModel = floorSettings.enabled === true && floorSettings.followModel !== false;
  const inspectHasMaterials = useMemo(() => hasAuthoredMaterials(meshData), [meshData]);
  const renderEnvironmentMapSize = Number(quality?.environmentMapSize) > 0
    ? Number(quality.environmentMapSize)
    : 256;
  const renderShadowMapSize = receiveShadows && Number(quality?.shadowMapSize) > 0
    ? Number(quality.shadowMapSize)
    : 2048;
  const renderShadowMapSizeRef = useRef(renderShadowMapSize);
  renderShadowMapSizeRef.current = renderShadowMapSize;
  // Fetch Render's chunk the first time this viewer is asked for Render, and
  // re-run the studio effects once it lands. The workspace normally warms it
  // first — the Viewing mode button's hover and focus, and the switch itself —
  // so this is the backstop for a cold cache and for a session restored
  // straight into Render.
  const [studioSceneTick, setStudioSceneTick] = useState(() => (studioScene() ? 1 : 0));
  useEffect(() => {
    if (!renderMode || studioScene()) {
      return undefined;
    }
    let cancelled = false;
    loadStudioScene().then(
      () => {
        if (!cancelled) {
          setStudioSceneTick((tick) => tick + 1);
        }
      },
      (error) => {
        if (cancelled) {
          return;
        }
        viewerAlertChangeRef.current?.({
          severity: "error",
          summary: "Render unavailable",
          title: "Couldn't load the Render studio",
          message: "The photographic studio is fetched the first time Render is opened, and that request did not complete.",
          recovery: "Check the connection to the viewer and reload the page, then switch to Render again.",
          details: String(error?.message || error)
        });
        console.error("Failed to load the Render studio chunk", error);
      }
    );
    return () => {
      cancelled = true;
    };
  }, [renderMode]);

  const renderConfigurationRef = useRef(renderConfiguration);
  renderConfigurationRef.current = renderConfiguration;
  const applyActivePhotographicStudio = useCallback((runtime, bounds = runtime?.modelBounds) => {
    const configuration = renderConfigurationRef.current;
    const studio = studioScene();
    if (!renderMode || !configuration || !runtime?.THREE || !studio) {
      return;
    }
    const studioState = studio.applyPhotographicStudio(runtime.THREE, runtime, configuration, {
      bounds,
      sceneScale: normalizedSceneScaleMode,
      shadowMapSize: renderShadowMapSizeRef.current
    });
    // Where the photographic floor actually ended up, so a browser test can
    // assert that a model reaching below its own origin stands ON the plane
    // rather than behind it. The scene sync republishes the placement seam, so
    // the live value lives on the runtime and both writers read it from there.
    runtime.photographicGroundZ = Number.isFinite(Number(studioState?.ground?.position?.z))
      ? Number(studioState.ground.position.z)
      : null;
    if (typeof window !== "undefined" && window.__cadModelPlacement) {
      window.__cadModelPlacement = {
        ...window.__cadModelPlacement,
        floorFollowsModel: configuration.backdrop?.ground === true
          && configuration.backdrop.groundPlacement !== "origin",
        groundZ: runtime.photographicGroundZ
      };
    }
  }, [normalizedSceneScaleMode, renderMode, studioSceneTick]);

  useEffect(() => {
    applyActivePhotographicStudio(runtimeRef.current);
  }, [applyActivePhotographicStudio, renderConfiguration, viewerReadyTick]);
  const updateActiveGridHelper = useCallback((
    runtime,
    activeViewerTheme,
    radius,
    floorZ = 0,
    sceneScaleMode = VIEWER_SCENE_SCALE.CAD,
    floorMode = THEME_FLOOR_MODES.STAGE
  ) => {
    return updateGridHelper(
      runtime,
      activeViewerTheme,
      radius,
      floorZ,
      sceneScaleMode,
      floorMode,
      guideFloorSettings
    );
  }, [guideFloorSettings]);
  const applyActiveSceneBackground = applySceneBackground;
  const edgesVisible = showEdges && (explicitViewPolicy ? displayEdgeSettings.enabled : shouldUseCadEdgeSource && displayModeShowsEdges(normalizedDisplayMode));
  const topologyDisplayEdgesVisible = shouldRenderTopologyDisplayEdges({
    edgesVisible,
    wireframeMode,
    cadEdgeSource: shouldUseCadEdgeSource,
    displayEdgeRuntime: activeDisplayEdgeRuntime,
    selectorRuntime: activeSelectorRuntime,
    edgeSettings: visualEdgeSettings
  });
  const displayEdgesVisible =
    edgesVisible &&
    !topologyDisplayEdgesVisible &&
    !shouldUseCadEdgeSource &&
    shouldBuildDerivedDisplayEdges(meshData);
  const surfaceStepEdgesVisible =
    edgesVisible &&
    !topologyDisplayEdgesVisible &&
    shouldUseCadEdgeSource;
  const recordEdgesVisible = shouldShowRecordDisplayEdges({
    edgesVisible,
    topologyDisplayEdgesVisible,
    displayEdgesVisible,
    cadEdgesVisible: surfaceStepEdgesVisible,
    wireframeMode
  });
  const preserveInteractionPixelRatio = Boolean(
    wireframeMode ||
    edgesVisible ||
    topologyDisplayEdgesVisible ||
    displayEdgesVisible ||
    surfaceStepEdgesVisible ||
    recordEdgesVisible
  );
  const partVisualStateEnabled =
    (Array.isArray(selectedPartIds) && selectedPartIds.length > 0) ||
    pickMode === VIEWER_PICK_MODE.PARTS ||
    pickMode === VIEWER_PICK_MODE.ASSEMBLY ||
    (
      pickMode === VIEWER_PICK_MODE.AUTO &&
      Array.isArray(pickableParts) &&
      pickableParts.length > 0
    ) ||
    (Array.isArray(hiddenPartIds) && hiddenPartIds.length > 0) ||
    focusedPartIds.length > 0;
  const partVisualStateRef = useRef({
    viewerTheme,
    edgeSettings: visualEdgeSettings,
    hiddenPartIds: partVisualStateEnabled ? hiddenPartIds : [],
    hoveredPartId: partVisualStateEnabled ? hoveredPartId : "",
    focusedPartId: partVisualStateEnabled ? focusedPartIds : [],
    selectedPartIds: partVisualStateEnabled ? selectedPartIds : [],
    showEdges: recordEdgesVisible,
    displayMode: normalizedDisplayMode
  });

  useLayoutEffect(() => {
    partVisualStateRef.current = {
      viewerTheme,
      edgeSettings: visualEdgeSettings,
      hiddenPartIds: partVisualStateEnabled ? hiddenPartIds : [],
      hoveredPartId: partVisualStateEnabled ? hoveredPartId : "",
      focusedPartId: partVisualStateEnabled ? focusedPartIds : [],
      selectedPartIds: partVisualStateEnabled ? selectedPartIds : [],
      showEdges: recordEdgesVisible,
      displayMode: normalizedDisplayMode
    };
  }, [
    normalizedDisplayMode,
    recordEdgesVisible,
    focusedPartIds,
    hiddenPartIds,
    hiddenAwareVisualEdgeSettings,
    hoveredPartId,
    partVisualStateEnabled,
    selectedPartIds,
    viewerTheme,
    visualEdgeSettings
  ]);
  const visibleReferenceFilter = useCallback((reference) => {
    const partId = String(reference?.partId || "").trim();
    if (partId && hiddenPartIdSet.has(partId)) {
      return false;
    }
    if (!partId && hiddenPartIdSet.has("__model__")) {
      return false;
    }
    return referenceMatchesFocusedPart(reference, focusedPartIdSet);
  }, [focusedPartIdSet, hiddenPartIdSet]);
  const filteredPickableFaces = useMemo(
    () => (Array.isArray(pickableFaces) ? pickableFaces : []).filter(visibleReferenceFilter),
    [pickableFaces, visibleReferenceFilter]
  );
  const filteredPickableEdges = useMemo(
    () => (Array.isArray(pickableEdges) ? pickableEdges : []).filter(visibleReferenceFilter),
    [pickableEdges, visibleReferenceFilter]
  );
  const filteredPickableVertices = useMemo(
    () => (Array.isArray(pickableVertices) ? pickableVertices : []).filter(visibleReferenceFilter),
    [pickableVertices, visibleReferenceFilter]
  );
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
    for (const reference of [...filteredPickableFaces, ...filteredPickableEdges, ...filteredPickableVertices]) {
      const referenceId = String(reference?.id || "").trim();
      if (!referenceId) {
        continue;
      }
      map.set(referenceId, reference);
    }
    return map;
  }, [activeSelectorRuntime, filteredPickableEdges, filteredPickableFaces, filteredPickableVertices, visibleReferenceFilter]);
  perspectivePropRef.current = perspective;
  modelKeyRef.current = modelKey;
  sceneScaleModeRef.current = normalizedSceneScaleMode;
  const runWithoutPerspectiveEvents = (callback) => {
    suppressPerspectiveEventsRef.current += 1;
    try {
      return callback();
    } finally {
      suppressPerspectiveEventsRef.current = Math.max(0, suppressPerspectiveEventsRef.current - 1);
    }
  };
  const {
    activateDefaultViewPlane,
    activateViewPlaneFace,
    applyInitialPerspective,
    applyZoomPercent,
    emitPerspectiveChange,
    resetZoomAndPan,
    syncCameraZoomPercent,
    syncFullscreenCamera,
    syncViewPlaneOrientation
  } = useViewportCamera({
    coordinateSystemFor,
    activeViewPlaneFaceRef,
    cameraZoomPercent,
    defaultPerspectiveResettingRef,
    fullscreenCameraRef,
    lastEmittedPerspectiveRef,
    cameraMovedRef: lodCameraChangeRef,
    modelBounds: meshData?.bounds,
    modelKey,
    modelKeyRef,
    modelTransformRef,
    onCameraZoomPercentChange,
    perspectiveChangeRef,
    perspectivePropRef,
    perspectiveRef,
    previewMode,
    previewModeRef,
    previewOrbitSpeed,
    runWithoutPerspectiveEvents,
    runtimeRef,
    sceneScaleModeRef,
    setActiveViewPlaneFace,
    setCameraZoomPercent,
    setDefaultPerspectiveDetached,
    setViewPlaneOrientation,
    suppressPerspectiveEventsRef,
    viewerReadyTick
  });
  const handleViewportResize = useCallback(() => {
    const runtime = runtimeRef.current;
    resampleLodAfterViewportResize(runtime, {
      syncFraming: syncRuntimeViewportFraming, syncZoom: syncCameraZoomPercent,
      emitPerspective: emitPerspectiveChange, resample: () => lodCameraChangeRef.current?.()
    });
  }, [syncCameraZoomPercent]);
  
  // DRAW MODE: the view direction is locked and the drawing editor owns pan and
  // zoom; the camera follows it so ink and model stay one picture. Orbit input
  // never reaches the controls (the editor covers the viewport), and everything
  // else that could turn or reframe the camera is switched off for the duration.
  const drawingOverlayActive = drawingEnabled && !previewMode && hasViewportContent;
  const { drawingControllerRef, handleDrawingContent, handleDrawingReady, followDrawingViewport } = useDrawingViewLock({
    active: drawingOverlayActive, drawing, runtimeRef, mountRef, viewerReadyTick
  });

  useImperativeHandle(ref, () => ({
    async prepareViewSettings(scene, signal) {
      const runtime = runtimeRef.current;
      if (scene.render.enabled) {
        const studio = await loadStudioScene();
        signal.throwIfAborted();
        if (runtime?.renderer && scene.view.lighting.enabled) {
          runtime.studioEnvironmentCache ??= createStudioEnvironmentCache();
          await runtime.studioEnvironmentCache.prepare(studio, runtime.renderer,
            scene.render.configuration, scene.quality.environmentMapSize, signal, runtime.environmentResource);
        }
      }
    },
    presentViewSettings() { return runtimeRef.current?.viewUpdateGate?.present(); },
    // The viewport produces pixels. Its host owns clipboard/draft delivery.
    async captureScreenshotBlob() {
      await viewUpdateBindingRef.current?.whenReady();
      const runtime = runtimeRef.current;
      if (!runtime?.renderer || !runtime?.scene || !runtime?.camera) {
        throw new Error("CAD Viewer not ready");
      }

      return await buildCompositeScreenshotBlob(runtime, drawingControllerRef.current?.inkCanvas() || null, {
        backgroundColor: resolveElementBackgroundColor(runtime.renderer.domElement)
      });
    },
    // Viewport LOD sampler (design/unified-tessellation.md Phase 5): projection
    // parameters + nearest eligible occurrence distances. Whole live bounds
    // include floor/group placement; numeric samples retain no scene objects.
    sampleLodCamera(options) {
      const runtime = runtimeRef.current;
      if (!runtimeModelKeyMatches(runtime, modelKeyRef.current)) return null;
      return sampleLodCamera(THREE, runtime, {
        ...options,
        selectedPartIds: lodSelectedPartIdsRef.current,
      });
    },
    // Exposed so a toolbar can drive the camera the same way the view-plane widget does,
    // which keeps one camera authority rather than a second that drifts from the widget's
    // idea of where `top` is.
    activateViewPlaneFace(faceId) {
      return activateViewPlaneFace(faceId);
    },
    applyZoomPercent(nextZoomPercent) {
      return applyZoomPercent(nextZoomPercent);
    },
    resetView() {
      const reset = zoomRuntimeToBounds(runtimeRef.current, runtimeFramingBounds(runtimeRef.current, meshData?.bounds), sceneScaleModeRef.current, {
        animate: true, modelOffset: modelTransformRef.current.offset, resetZoomBaseline: true,
        viewDirection: DEFAULT_VIEW_DIRECTION, viewUp: WORLD_UP,
      });
      if (reset) {
        activeViewPlaneFaceRef.current = "";
        setActiveViewPlaneFace("");
        defaultPerspectiveResettingRef.current = true;
        setDefaultPerspectiveDetached(false);
      }
      return reset;
    },
    activateDefaultViewPlane() {
      return activateDefaultViewPlane();
    },
    getPerspective() {
      return readScopedPerspectiveSnapshot(runtimeRef.current, {
        modelKey,
        sceneScaleMode: normalizedSceneScaleMode,
        coordinateSystem: coordinateSystemFor(normalizedSceneScaleMode)
      });
    },
    setPerspective(perspective, options = {}) {
      if (options?.animate) {
        return transitionCameraToPerspectiveSnapshot(runtimeRef.current, perspective, options);
      }
      const applied = applyPerspectiveSnapshot(runtimeRef.current, perspective);
      if (applied && options?.resetZoomBaseline) {
        resetRuntimeZoomBaseline(runtimeRef.current);
        syncCameraZoomPercent(runtimeRef.current);
      }
      return applied;
    },
    resetZoom() {
      return resetZoomAndPan({ animate: true });
    },
    zoomToFit({ animate = true } = {}) {
      const runtime = runtimeRef.current;
      const fitted = zoomRuntimeToBounds(
        runtime,
        runtimeFramingBounds(runtime, meshData?.bounds),
        sceneScaleModeRef.current,
        {
          animate,
          modelOffset: modelTransformRef.current.offset,
          resetZoomBaseline: true
        }
      );
      if (fitted && !animate) {
        emitPerspectiveChange(runtime);
        syncViewPlaneOrientation(runtime);
      }
      return fitted;
    },
    zoomToFitSelection({ partIds = [], referenceIds = [], fallbackToModel = false, animate = true } = {}) {
      const runtime = runtimeRef.current;
      // `fallbackToModel` is the CALLER saying "there is no narrower target here" — the
      // global viewport menu, which every format now opens. Deciding that from inside on
      // the render format made the fallback format-specific, and it is not: a plain mesh
      // has no sub-part selection either.
      const bounds = mergeBoundsList([
        selectorReferenceBounds(activeSelectorRuntime, referenceIds),
        displayRecordBoundsForPartIds(runtime, partIds)
      ]) || (fallbackToModel ? runtimeFramingBounds(runtime, meshData?.bounds) : null);
      const fitted = zoomRuntimeToBounds(
        runtime,
        bounds,
        sceneScaleModeRef.current,
        {
          animate,
          modelOffset: modelTransformRef.current.offset,
          resetZoomBaseline: false
        }
      );
      if (fitted && !animate) {
        emitPerspectiveChange(runtime);
        syncViewPlaneOrientation(runtime);
      }
      return fitted;
    },
    focusViewPreset(faceId) {
      return activateViewPlaneFace(faceId);
    }
  }), [
    activeSelectorRuntime,
    meshData?.bounds,
    modelKey,
    normalizedSceneScaleMode,
    resetZoomAndPan,
    syncCameraZoomPercent,
    syncViewPlaneOrientation
  ]);

  useEffect(() => {
    perspectiveChangeRef.current = onPerspectiveChange;
  }, [onPerspectiveChange]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return undefined;
    }
    runtime.onZoomChange = syncCameraZoomPercent;
    syncCameraZoomPercent(runtime);
    return () => {
      if (runtime.onZoomChange === syncCameraZoomPercent) {
        runtime.onZoomChange = null;
      }
    };
  }, [syncCameraZoomPercent, viewerReadyTick]);

  useEffect(() => {
    viewerAlertChangeRef.current = onViewerAlertChange;
  }, [onViewerAlertChange]);

  useEffect(() => {
    stepModuleTransformDetectedChangeRef.current = onStepModuleTransformDetectedChange;
  }, [onStepModuleTransformDetectedChange]);


  useEffect(() => {
    setTransformedSelectorRuntime(null);
  }, [modelKey, selectorRuntime]);

  useEffect(() => {
    setTransformedDisplayEdgeRuntime(null);
  }, [modelKey, displayEdgeRuntime]);

  useEffect(() => {
    selectorRuntimeRef.current = activeSelectorRuntime;
  }, [activeSelectorRuntime]);

  useEffect(() => {
    displayEdgeRuntimeRef.current = activeDisplayEdgeRuntime;
  }, [activeDisplayEdgeRuntime]);

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

  const handleRuntimeContextRestored = useCallback(() => {
    framedModelKeyRef.current = "";
    framedCompleteModelKeyRef.current = "";
    framedZeroPoseBoundsRef.current = null;
    framedViewingModeRef.current = "";
    lastEmittedPerspectiveRef.current = null;
    defaultPerspectiveResettingRef.current = false;
    viewerAlertChangeRef.current?.(null);
    setDefaultPerspectiveDetached(false);
    setRuntimeResetToken((value) => value + 1);
  }, []);

  const handleRuntimeInitializationError = useCallback((runtimeError) => {
    // A replacement runtime that cannot initialize has no future scene that
    // can finish an in-flight LOD handoff.
    meshSourceAdoptionRef.current?.(null, false, { disposed: true, terminal: true });
    viewerAlertChangeRef.current?.(buildRuntimeInitializationAlert(runtimeError));
  }, []);
  const handleRuntimeContextLost = useCallback(() => { meshSourceAdoptionRef.current?.(null, false); }, []);

  useViewerRuntime({
    mountRef,
    runtimeRef,
    previewModeRef,
    setError,
    setViewerReadyTick,
    viewerTheme,
    emitPerspectiveChange,
    setActiveViewPlaneFace,
    activeViewPlaneFaceRef,
    stepCameraTransition,
    stepKeyboardOrbit,
    getActiveViewPlaneFaceId,
    cancelCameraTransition,
    clearKeyboardOrbitState,
    isTrackpadLikeWheelEvent,
    isPinchWheelEvent,
    WHEEL_PINCH_DELTA_BOOST,
    getKeyboardOrbitCommand,
    getKeyboardOrbitAxes,
    applyOrbitDelta,
    getViewerThemeValue,
    getPixelRatioCap,
    applySceneBackground: applyActiveSceneBackground,
    onViewportResize: handleViewportResize,
    applyInitialPerspective,
    updateGridHelper: updateActiveGridHelper,
    clearSceneGroup,
    disposeScene: disposeRuntimeCadScene,
    disposeStudio: disposeRuntimeStudio,
    onSceneDisposed: (source, { handoff = false } = {}) => meshSourceAdoptionRef.current?.(source, false,
      { disposed: true, terminal: !handoff, handoff }),
    disposeSceneObject,
    disposeTexture,
    syncViewPlaneOrientation,
    BASE_VIEWER_THEME,
    DEFAULT_LIGHTING,
    DEFAULT_DAMPING_FACTOR,
    DEFAULT_ZOOM_SPEED,
    COARSE_POINTER_ZOOM_SPEED,
    INTERACTION_PIXEL_RATIO_CAP,
    IDLE_PIXEL_RATIO_CAP: Number(quality?.idlePixelRatioCap) > 0
      ? Number(quality.idlePixelRatioCap)
      : IDLE_PIXEL_RATIO_CAP,
    INTERACTION_IDLE_DELAY_MS,
    TRACKPAD_PINCH_ZOOM_SPEED,
    COARSE_POINTER_PINCH_ZOOM_SPEED,
    ACCELERATED_WHEEL_ZOOM_SPEED,
    KEYBOARD_ORBIT_NUDGE_RAD,
    defaultGridRadius,
    sceneScaleMode: normalizedSceneScaleMode,
    floorMode: resolvedFloorMode,
    renderMode,
    onInitializationError: handleRuntimeInitializationError,
    onFramePresented: handleFramePresented,
    presentationRequestRef,
    onContextLost: handleRuntimeContextLost,
    onContextRestored: handleRuntimeContextRestored,
    preserveInteractionPixelRatio,
    runtimeResetToken
  });

  useEffect(() => {
    const runtime = runtimeRef.current;
    const camera = runtime?.perspectiveCamera;
    const nextFocalLength = explicitViewerFocalLength(focalLength);
    if (
      runtime?.controls &&
      camera &&
      nextFocalLength == null
    ) {
      delete camera.userData.cadFocalLength;
      if (Math.abs(camera.fov - CAD_DEFAULT_VERTICAL_FOV_DEGREES) >= 1e-4) {
        camera.fov = CAD_DEFAULT_VERTICAL_FOV_DEGREES;
        camera.updateProjectionMatrix();
        camera.lookAt(runtime.controls.target);
        runtime.controls.update?.();
        emitPerspectiveChange(runtime);
        runtime.requestRender?.();
      }
      return;
    }
    if (
      !runtime?.controls ||
      !camera?.getFocalLength ||
      nextFocalLength == null
    ) {
      return;
    }
    const previousFocalLength = camera.getFocalLength();
    if (Math.abs(previousFocalLength - nextFocalLength) < 1e-4) {
      camera.userData.cadFocalLength = nextFocalLength;
      return;
    }
    const previousFov = camera.fov * Math.PI / 180;
    const offset = camera.position.clone().sub(runtime.controls.target);
    setRuntimePerspectiveFocalLength(runtime, nextFocalLength);
    const nextFov = camera.fov * Math.PI / 180;
    if (runtime.camera === camera && offset.lengthSq() > 1e-8) {
      const distanceScale = perspectiveDistanceScale(
        previousFov * 180 / Math.PI,
        nextFov * 180 / Math.PI
      );
      if (Number.isFinite(distanceScale) && distanceScale > 0) {
        camera.position.copy(runtime.controls.target).add(offset.multiplyScalar(distanceScale));
      }
    }
    camera.lookAt(runtime.controls.target);
    runtime.controls.update?.();
    emitPerspectiveChange(runtime);
    runtime.scheduleIdleQuality?.();
    runtime.requestRender?.();
  }, [focalLength, renderMode, viewerReadyTick]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }
    runtime.sceneScaleMode = normalizedSceneScaleMode;
  }, [normalizedSceneScaleMode]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (renderMode) {
      applyActivePhotographicStudio(runtime);
      return;
    }
    const shadow = runtime?.keyLight?.shadow;
    if (!runtime?.THREE || !shadow?.mapSize) {
      return;
    }
    const previousSize = Number(runtime.shadowMapSize);
    if (Math.abs(previousSize - renderShadowMapSize) < 1) {
      return;
    }
    const previousMap = shadow.map;
    shadow.map = null;
    previousMap?.dispose?.();
    shadow.mapSize.set(renderShadowMapSize, renderShadowMapSize);
    runtime.shadowMapSize = renderShadowMapSize;
    if (runtime.modelBounds) {
      applyRuntimeModelBounds(
        runtime.THREE,
        runtime,
        runtime.modelBounds,
        normalizedSceneScaleMode,
        { shadowMapSize: renderShadowMapSize }
      );
    }
    runtime.invalidateShadows?.();
    runtime.requestRender?.();
  }, [applyActivePhotographicStudio, normalizedSceneScaleMode, renderMode, renderShadowMapSize, viewerReadyTick]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }
    const previousProjection = lastProjectionRef.current;
    lastProjectionRef.current = normalizedProjection;
    const projectionChanged = previousProjection !== normalizedProjection;
    if (!syncRuntimeCameraProjection(runtime, normalizedProjection, projectionChanged ? {
      scheduleIdle: false,
      requestRender: false
    } : undefined)) {
      return;
    }
    emitPerspectiveChange(runtime);
    syncViewPlaneOrientation(runtime);
    // NOTE: syncViewPlaneOrientation is an unmemoized closure (new identity every
    // render), so listing it here re-ran this effect on every render. During a
    // preview orbit that became a self-sustaining cascade (each run calls
    // syncRuntimeCameraProjection -> emitPerspectiveChange/syncViewPlaneOrientation ->
    // setState -> re-render), tens of times per frame. This effect only needs to run
    // when the projection or viewer readiness changes, like the already-omitted
    // emitPerspectiveChange dependency above.
  }, [normalizedProjection, viewerReadyTick]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }

    const materialSettings = { ...normalizedMaterialSettings };
    if (runtime.cadScene) {
      runtime.cadScene.update({
        theme: normalizedThemeSettings,
        appearance,
        materialSettings,
        materialOverrides,
        receiveShadows,
        surfaceSettings
      });
      runtime.displayRecords = runtime.cadScene.displayRecords;
    } else {
      for (const record of runtime.displayRecords || []) {
        applyMaterialSettingsToRecord(runtime.THREE, record, materialSettings, {
          displayMode: normalizedDisplayMode,
          surfaceSettings,
          materialOverrides
        });
      }
    }
    runtime.cadScene?.syncSurfaceInstances();

    if (photographicLighting) {
      runtime.hemisphereLight.visible = false;
      runtime.ambientLight.visible = false;
      runtime.keyLight.visible = false;
      runtime.fillLight.visible = false;
      runtime.rimLight.visible = false;
      runtime.spotLight.visible = false;
      runtime.pointLight.visible = false;
      runtime.gridConfig = null;
      updateActiveGridHelper(
        runtime,
        viewerTheme,
        runtime.gridRadius ?? defaultGridRadius,
        0,
        normalizedSceneScaleMode,
        THEME_FLOOR_MODES.NONE
      );
      clearSceneGroup(runtime.stageGroup);
      applyActivePhotographicStudio(runtime);
      runtime.requestRender();
      return;
    }

    if (!renderMode) studioScene()?.disposePhotographicStudio(runtime);
    applyActiveSceneBackground(runtime, viewerTheme, normalizedThemeSettings.background);
    runtime.renderer.toneMappingExposure = Math.max(normalizedThemeSettings.lighting.toneMappingExposure, 0.05);

    runtime.hemisphereLight.visible = normalizedThemeSettings.lighting.hemisphere.enabled;
    runtime.hemisphereLight.color.set(normalizedThemeSettings.lighting.hemisphere.skyColor);
    runtime.hemisphereLight.groundColor.set(normalizedThemeSettings.lighting.hemisphere.groundColor);
    runtime.hemisphereLight.intensity = normalizedThemeSettings.lighting.hemisphere.intensity;

    runtime.ambientLight.visible = normalizedThemeSettings.lighting.ambient.enabled;
    runtime.ambientLight.color.set(normalizedThemeSettings.lighting.ambient.color);
    runtime.ambientLight.intensity = normalizedThemeSettings.lighting.ambient.intensity;

    runtime.keyLight.visible = normalizedThemeSettings.lighting.directional.enabled;
    runtime.keyLight.color.set(normalizedThemeSettings.lighting.directional.color);
    runtime.keyLight.intensity = normalizedThemeSettings.lighting.directional.intensity;

    const fillSettings = normalizedThemeSettings.lighting.fill;
    runtime.fillLight.visible = fillSettings.enabled && fillSettings.intensity > 0.0001;
    runtime.fillLight.color.set(fillSettings.color);
    runtime.fillLight.intensity = Math.max(fillSettings.intensity, 0);

    const rimSettings = normalizedThemeSettings.lighting.rim;
    runtime.rimLight.visible = rimSettings.enabled && rimSettings.intensity > 0.0001;
    runtime.rimLight.color.set(rimSettings.color);
    runtime.rimLight.intensity = Math.max(rimSettings.intensity, 0);

    runtime.spotLight.visible = normalizedThemeSettings.lighting.spot.enabled;
    runtime.spotLight.color.set(normalizedThemeSettings.lighting.spot.color);
    runtime.spotLight.intensity = normalizedThemeSettings.lighting.spot.intensity;
    runtime.spotLight.angle = normalizedThemeSettings.lighting.spot.angle;

    runtime.pointLight.visible = normalizedThemeSettings.lighting.point.enabled;
    runtime.pointLight.color.set(normalizedThemeSettings.lighting.point.color);
    runtime.pointLight.intensity = normalizedThemeSettings.lighting.point.intensity;
    syncRuntimeScaledLightingAndShadow(
      runtime.THREE,
      runtime,
      normalizedThemeSettings.lighting,
      runtime.modelRadius ?? runtime.gridRadius ?? defaultGridRadius,
      runtime.modelBounds,
      normalizedSceneScaleMode,
      renderShadowMapSizeRef.current
    );
    updateSpotLightTarget(runtime);

    // Keep a single primary shadow; the spot light drives the floor glow/fill.
    runtime.keyLight.castShadow = runtime.keyLight.visible && runtime.softwareRendering !== true;
    runtime.spotLight.castShadow = false;

    runtime.gridConfig = null;
    const themeFloorZCandidate = floorFollowsModel
      ? runtime.modelFloorZBelowModel
      : runtime.modelFloorZBase;
    const themeFloorZ = Number.isFinite(themeFloorZCandidate)
      ? themeFloorZCandidate
      : runtime.gridFloorZ ?? 0;
    updateActiveGridHelper(
      runtime,
      viewerTheme,
      runtime.gridRadius ?? defaultGridRadius,
      themeFloorZ,
      normalizedSceneScaleMode,
      resolvedFloorMode
    );
    updateSpotLightTarget(runtime);
    if (runtime.hasVisibleModel) {
      updateStageEffects(
        runtime,
        viewerTheme,
        normalizedThemeSettings,
        runtime.gridRadius ?? defaultGridRadius,
        themeFloorZ,
        resolvedFloorMode,
        normalizedSceneScaleMode
      );
    } else {
      clearSceneGroup(runtime.stageGroup);
    }
    if (renderMode) applyActivePhotographicStudio(runtime);
    runtime.requestRender();
  }, [
    defaultGridRadius,
    surfaceSettings,
    photographicLighting,
    normalizedDisplayMode,
    appearance,
    materialOverrides,
    normalizedMaterialSettings,
    normalizedThemeSettings,
    normalizedSceneScaleMode,
    resolvedFloorMode,
    receiveShadows,
    renderMode,
    floorFollowsModel,
    viewerReadyTick,
    viewerTheme,
    updateActiveGridHelper,
    applyActivePhotographicStudio
  ]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.scene) {
      return;
    }

    const studio = studioScene();
    const clearEnvironmentResource = () => {
      runtime.scene.environment = null;
      if (!runtime.studioEnvironmentCache?.owns(runtime.environmentResource)) runtime.environmentResource?.dispose();
      runtime.environmentResource = null;
      runtime.environmentResourceIdentity = "";
    };
    // Render asked for, chunk not here yet. Leaving environmentReady false is
    // the whole contract: the canvas stays under the destination backdrop until
    // this effect re-runs with the studio loaded (studioSceneTick), so nothing
    // is ever drawn with CAD lighting under a photographic camera.
    if (renderMode && renderConfiguration && !studio) {
      runtime.environmentReady = false;
      return;
    }
    if (!photographicLighting || !renderConfiguration) {
      runtime.environmentReady = true;
      if (inspectHasMaterials) {
        if (runtime.environmentResourceIdentity !== INSPECT_ENVIRONMENT_ID) {
          clearEnvironmentResource();
          runtime.environmentResource = createInspectEnvironmentResource(runtime.THREE);
          runtime.environmentResourceIdentity = INSPECT_ENVIRONMENT_ID;
        }
        runtime.scene.environment = runtime.environmentResource.texture;
        runtime.scene.environmentIntensity = 1;
      } else {
        clearEnvironmentResource();
        runtime.scene.environmentIntensity = 0;
      }
      if (renderMode) applyActivePhotographicStudio(runtime);
      else applyActiveSceneBackground(runtime, viewerTheme, normalizedThemeSettings.background);
      viewerAlertChangeRef.current?.(null);
      runtime.requestRender();
      return;
    }

    runtime.scene.environmentIntensity = 1;
    const applyBackgroundFallback = () => {
      clearEnvironmentResource();
      applyActivePhotographicStudio(runtime);
      runtime.environmentReady = true;
      runtime.requestRender();
    };

    // PMREM generation is synchronous GPU work, so this effect never suspends
    // and no in-flight environment can outlive the render mode that asked for it.
    const applyEnvironment = () => {
      const resourceIdentity = studio.environmentResourceIdentity(renderConfiguration, {
        size: renderEnvironmentMapSize
      });
      if (!resourceIdentity) {
        viewerAlertChangeRef.current?.(null);
        applyBackgroundFallback();
        return;
      }

      if (!runtime.environmentResource || runtime.environmentResourceIdentity !== resourceIdentity) {
        const nextResource = runtime.studioEnvironmentCache?.get(resourceIdentity) || studio.createEnvironmentResource(runtime.renderer, renderConfiguration, {
          size: renderEnvironmentMapSize
        });
        const previousResource = runtime.environmentResource;
        runtime.scene.environment = null;
        runtime.environmentResource = nextResource;
        runtime.environmentResourceIdentity = resourceIdentity;
        if (!runtime.studioEnvironmentCache?.owns(previousResource)) studio.disposeEnvironmentResource(previousResource);
      }

      runtime.scene.environment = runtime.environmentResource.texture;
      runtime.environmentReady = true;
      viewerAlertChangeRef.current?.(null);

      applyActivePhotographicStudio(runtime);
      runtime.requestRender();
    };

    try {
      applyEnvironment();
    } catch (error) {
      applyBackgroundFallback();
      viewerAlertChangeRef.current?.({
        severity: "warning",
        summary: "Environment unavailable",
        title: "Couldn’t prepare studio lighting",
        message: "The reflection environment could not be created. The model is shown with the studio’s direct lighting, so reflective materials may look different.",
        recovery: "Reload the viewer to retry the studio environment.",
        details: String(error?.message || error)
      });
      console.error("Failed to apply environment resource", error);
    }
  }, [
    applyActivePhotographicStudio,
    renderConfiguration,
    renderEnvironmentMapSize,
    photographicLighting,
    inspectHasMaterials,
    renderMode,
    studioSceneTick,
    viewerReadyTick,
    viewerTheme,
    normalizedThemeSettings.background
  ]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }

    if (runtime.interactionState.restoreTimerId) {
      window.clearTimeout(runtime.interactionState.restoreTimerId);
      runtime.interactionState.restoreTimerId = 0;
    }
    clearKeyboardOrbitState(runtime.keyboardOrbitState);
    const orbitActive = previewMode && previewOrbitSpeed > 0;
    runtime.previewOrbitEnabled = orbitActive;
    runtime.orbitControlsLastTimestamp = 0;
    runtime.controls.autoRotate = orbitActive;
    runtime.controls.autoRotateSpeed = PREVIEW_AUTO_ROTATE_SPEED * previewOrbitSpeed;
    if (previewMode) runtime.controls.enabled = true;
    if (!drawingOverlayActive) runtime.controls.enableDamping = true;
    runtime.controls.dampingFactor = DEFAULT_DAMPING_FACTOR;
    if (orbitActive) {
      cancelCameraTransition(runtime, { scheduleIdle: false });
      runtime.beginInteraction?.();
    } else {
      runtime.scheduleIdleQuality();
    }
    runtime.requestRender();
  }, [previewMode, previewOrbitSpeed, viewerReadyTick]);




  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }

    const {
      THREE,
      modelGroup,
      edgesGroup,
      facePickGroup,
      edgePickGroup,
      vertexPickGroup
    } = runtime;

    // releaseGpu: a model going away frees its components' GPU buffers and
    // BVHs; a rebuild of the SAME model (theme, display mode) keeps them so the
    // new records draw without re-uploading every component.
    const clearDisplayedModel = ({ preserveModelIdentity = false, releaseGpu = true } = {}) => {
      staticSceneResetRef.current.invalidate();
      cancelCameraTransition(runtime);
      // The next model publishes its own; nothing may frame against the last one.
      runtime.zeroPoseBounds = null;
      const disposedSource = disposeViewerCadScene(runtime, { clearSceneGroup, preserveModelIdentity, releaseGpu });
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
    const { controls } = runtime;
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
      : (displayEdgesVisible || surfaceStepEdgesVisible)
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
      sceneScaleMode: normalizedSceneScaleMode,
      edgeSettings: sceneTheme.edges,
      recomputeNormals,
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
    const reuseScene = !!runtime.cadScene &&
      runtime.hasVisibleModel &&
      runtime.activeModelKey === (modelKey || "") &&
      sceneBuildRef.current.key === sceneBuildKey &&
      sceneBuildRef.current.viewerTheme === viewerTheme;
    const rebuildReason = !reuseScene && runtime.cadScene
      ? sceneBuildKeyDifference(sceneBuildRef.current, { key: sceneBuildKey, viewerTheme }, runtime, modelKey)
      : "";
    let cadScene;
    if (reuseScene) {
      cadScene = runtime.cadScene;
      cadScene.update({
        source: meshData,
        theme: sceneTheme,
        materialSettings,
        materialOverrides,
        ...sceneModelSettings
      });
    } else {
      clearDisplayedModel({ releaseGpu: !runtime.hasVisibleModel || runtime.activeModelKey !== (modelKey || "") });
      cadScene = buildModel(THREE, meshData, {
        theme: sceneTheme,
        displayMode: normalizedDisplayMode,
        applyDisplayModeEdgePolicy: !explicitViewPolicy && !topologyDisplayEdgesVisible,
        scale: normalizedSceneScaleMode,
        baseTheme: viewerTheme,
        materialSettings,
        materialOverrides,
        edgeSettings: visualEdgeSettings,
        recomputeNormals,
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
      modelGroup.add(cadScene.modelGroup);
      edgesGroup.add(cadScene.edgesGroup);
      sceneBuildRef.current = { key: sceneBuildKey, viewerTheme };
    }
    runtime.cadScene = cadScene;
    // The rows this build/adoption placed. A later placement pass compares it
    // (sceneSourceAlreadyPlaced) so it repeats the per-occurrence loop only for
    // rows this effect did NOT place -- a wrapper may publish new rows over the
    // same geometry source.
    runtime.placedSourceParts = Array.isArray(meshData?.parts) ? meshData.parts : null;
    runtime.displayRecords = cadScene.displayRecords;
    runtime.syncScreenSpaceLineMaterials?.();
    setDisplayRecordsToken((token) => token + 1);
    runtime.hasVisibleModel = true;
    runtime.activeModelKey = modelKey || "";
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

    const displayBounds = cadScene.bounds || meshData.bounds;
    // TWO boxes, and the split is the point. displayBounds is the model in the
    // pose it is in right now -- what lighting, shadows, the floor height and
    // clipping must follow (the grid and stage keep the rest pose's SIZE). zeroPoseBounds is the model at its authored
    // placement: a STEP assembly before its mates moved anything. The CAMERA is grounded on that one, so
    // driving a joint, picking a group state or scrubbing an animation never
    // re-frames the model, and 100% keeps meaning "framed at the zero pose".
    const zeroPoseBounds = mergeBoundsList([cadScene.restBounds || meshData.bounds]);
    runtime.zeroPoseBounds = zeroPoseBounds;
    const zeroPoseRadius = boundsModelRadius(THREE, zeroPoseBounds, normalizedSceneScaleMode);
    const boundsMin = Array.isArray(displayBounds?.min) ? displayBounds.min : [0, 0, 0];
    const boundsMax = Array.isArray(displayBounds?.max) ? displayBounds.max : [0, 0, 0];
    const zeroPoseMin = Array.isArray(zeroPoseBounds?.min) ? zeroPoseBounds.min : [0, 0, 0];
    const zeroPoseMax = Array.isArray(zeroPoseBounds?.max) ? zeroPoseBounds.max : [0, 0, 0];
    const center = new THREE.Vector3(
      (toNumber(zeroPoseMin[0]) + toNumber(zeroPoseMax[0])) / 2,
      (toNumber(zeroPoseMin[1]) + toNumber(zeroPoseMax[1])) / 2,
      (toNumber(zeroPoseMin[2]) + toNumber(zeroPoseMax[2])) / 2
    );
    const previousTransform = modelTransformRef.current;
    if (
      previousTransform.modelKey !== modelKey ||
      previousTransform.sceneScaleMode !== normalizedSceneScaleMode ||
      !previousTransform.offset
    ) {
      previousTransform.modelKey = modelKey || "";
      previousTransform.sceneScaleMode = normalizedSceneScaleMode;
      // The model renders at its AUTHORED world coordinates: geometry is never
      // re-centered on its bounds (that translation hid any authored offset
      // from the origin and made the reference panel disagree with the
      // viewport). Framing moves the CAMERA to the model, never the model to
      // the camera. The offset vector is kept as plumbing (pick groups, clip
      // planes, zoom framing all take it) and is now always zero.
      previousTransform.offset = new THREE.Vector3(0, 0, 0);
      previousTransform.floorZ = resolveRuntimeModelFloorZ(
        displayBounds,
        previousTransform.offset,
        normalizedSceneScaleMode
      );
      previousTransform.floorZBelowModel = resolveRuntimeModelFloorZ(
        displayBounds,
        previousTransform.offset,
        normalizedSceneScaleMode,
        { followModel: true }
      );
    }
    const modelOffset = previousTransform.offset;
    const cachedFloorZ = floorFollowsModel
      ? previousTransform.floorZBelowModel
      : previousTransform.floorZ;
    const floorZ = Number.isFinite(Number(cachedFloorZ))
      ? Number(cachedFloorZ)
      : resolveRuntimeModelFloorZ(displayBounds, modelOffset, normalizedSceneScaleMode, {
        followModel: floorFollowsModel
      });
    runtime.modelFloorZBase = Number(previousTransform.floorZ);
    runtime.modelFloorZBelowModel = Number(previousTransform.floorZBelowModel);
    const { radius } = applyRuntimeModelBounds(THREE, runtime, displayBounds, normalizedSceneScaleMode, {
      shadowMapSize: renderShadowMapSizeRef.current
    });
    if (renderMode) {
      applyActivePhotographicStudio(runtime, displayBounds);
    } else {
      syncRuntimeScaledLightingAndShadow(
        THREE,
        runtime,
        normalizedThemeSettings.lighting,
        radius,
        displayBounds,
        normalizedSceneScaleMode,
        renderShadowMapSizeRef.current
      );
    }
    // The grid and the stage are the ground the model stands on, sized once from its REST
    // pose: posing a joint moves the model, never the scale of the floor under it.
    const groundRadius = sceneRadiusForBounds(THREE, cadScene.restBounds || meshData.restBounds || displayBounds, normalizedSceneScaleMode);
    updateActiveGridHelper(
      runtime,
      viewerTheme,
      groundRadius,
      floorZ,
      normalizedSceneScaleMode,
      resolvedFloorMode
    );
    if (!renderMode) {
      updateSpotLightTarget(runtime);
      updateStageEffects(runtime, viewerTheme, normalizedThemeSettings, groundRadius, runtime.gridFloorZ ?? 0, resolvedFloorMode, normalizedSceneScaleMode);
    }

    const modelGroupPlacementChanged = !modelGroup.position.equals(modelOffset);
    modelGroup.position.copy(modelOffset);
    edgesGroup.position.copy(modelOffset);
    facePickGroup.position.copy(modelOffset);
    edgePickGroup.position.copy(modelOffset);
    vertexPickGroup.position.copy(modelOffset);
    if (typeof window !== "undefined") {
      // Read-only debug/test seam (like __CAD_VIEWER_LOD__): the true-pose
      // contract — model at authored coordinates, grid pinned per the floor
      // coupling — is asserted by tests/browser/viewer-e2e.mjs through this.
      window.__cadModelPlacement = {
        modelKey: modelKey || "",
        position: modelGroup.position.toArray(),
        boundsMin: [...boundsMin],
        boundsMax: [...boundsMax],
        gridFloorZ: Number.isFinite(Number(runtime.gridFloorZ)) ? Number(runtime.gridFloorZ) : null,
        groundZ: renderMode && Number.isFinite(Number(runtime.photographicGroundZ))
          ? Number(runtime.photographicGroundZ)
          : null,
        floorFollowsModel: renderMode
          ? renderConfigurationRef.current?.backdrop?.ground === true
            && renderConfigurationRef.current.backdrop.groundPlacement !== "origin"
          : floorFollowsModel
      };
    }
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
    if (typeof window !== "undefined") {
      // Byte attribution for the headless memory harness (read, never polled here).
      window.__cadRenderMemoryProbe = () => renderMemoryAccounting(runtimeRef.current);
      // Read-only debug/test seam beside __cadModelPlacement: the LIVE record
      // transforms, so a browser test can assert where a posed occurrence
      // actually renders rather than what the data upstream of it said.
      window.__cadDisplayRecords = () => (runtimeRef.current?.displayRecords || []).map((record) => ({
        partId: String(record?.partId || ""),
        linkName: String(record?.sourcePart?.linkName || ""),
        matrix: record?.mesh?.matrix?.toArray?.() || null
      }));
      // Read-only debug/test seam beside __cadDisplayRecords: the clip the viewport
      // APPLIES (the resolved view), which for a mesh is off whatever was saved.
      window.__cadClip = () => ({ ...clipSettingsRef.current });
      // Read-only debug/test seam beside __cadClip: where the Pose tool's knobs are,
      // in CSS pixels of the viewport, with each joint's value; empty outside the tool.
      window.__cadJointHandles = () => jointHandleLayoutRef.current?.() || [];
      // Read-only debug/test seam beside __cadDisplayRecords: the LIVE camera,
      // so a browser test can assert that posing a model leaves the framing
      // exactly where the zero pose put it.
      window.__cadCamera = () => {
        const active = runtimeRef.current;
        const camera = active?.camera;
        if (!camera) {
          return null;
        }
        return {
          projection: camera.isOrthographicCamera ? "orthographic" : "perspective",
          position: camera.position.toArray(),
          target: active.controls?.target?.toArray?.() || null,
          up: camera.up.toArray(),
          zoom: Number(camera.zoom),
          halfHeight: readOrthographicHalfHeight(active),
          zoomPercent: readRuntimeZoomPercent(active),
          originalBounds: active.zeroPoseBounds
        };
      };
    }

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
    modelGroup.updateMatrixWorld(true);
    edgesGroup.updateMatrixWorld(true);

    syncRuntimeCameraClipPlanes(runtime, Math.max(radius / 1200, 0.01), Math.max(radius * 600, 2000));
    controls.minDistance = Math.max(radius / 2200, 0.02);
    controls.maxDistance = Math.max(radius * 140, 50);
    controls.zoomSpeed = DEFAULT_ZOOM_SPEED;
    runtime.edgePickThreshold = Math.max(radius / 320, 0.65);

    // Whether the camera fits at all, and why: a different model, a change of
    // viewing mode, a progressive load reaching its full extent, or a rebuild
    // whose ZERO POSE changed. The decision (and what is deliberately NOT a
    // reason: any pose, any detail swap) lives in reframeReason.
    const missingComponentIds = meshData?.missingComponentIds;
    const modelIsComplete = !(Array.isArray(missingComponentIds) && missingComponentIds.length > 0);
    const viewingMode = renderMode ? VIEWING_MODE.RENDER : VIEWING_MODE.INSPECT;
    const reframe = reframeReason({
      modelKey,
      framedModelKey: framedModelKeyRef.current,
      framedCompleteModelKey: framedCompleteModelKeyRef.current,
      mode: viewingMode,
      framedMode: framedViewingModeRef.current,
      modelComplete: modelIsComplete,
      zeroPoseBounds,
      framedZeroPoseBounds: framedZeroPoseBoundsRef.current,
      userMovedCamera: runtime.userMovedCamera
    });
    if (modelIsComplete) {
      framedCompleteModelKeyRef.current = modelKey || "";
    }
    if (reframe) {
      if (reframe === "model") runtime.userMovedCamera = false;
      const nextPerspective = resolvePerspectiveSnapshot(
        perspectiveRef ? perspectiveRef.current : undefined,
        perspective
      );
      const nextPerspectiveMatchesScene = perspectiveSnapshotMatchesScene(nextPerspective, {
        modelKey,
        sceneScaleMode: normalizedSceneScaleMode,
        coordinateSystem: coordinateSystemForSceneScale(normalizedSceneScaleMode),
        requireModelKey: true,
        requireSceneScaleMode: true,
        requireCoordinateSystem: true
      });
      runWithoutPerspectiveEvents(() => {
        // A lighting-style switch restores the current camera; progressive
        // extent changes still fit the completed model when appropriate.
        const restored = !previewModeRef.current && (reframe === "model" || reframe === "mode")
          && nextPerspectiveMatchesScene
          && applyPerspectiveSnapshot(runtime, nextPerspective, { scheduleIdle: false });
        if (restored) {
          runtime.interactiveFraming = { bounds: zeroPoseBounds,
            minRadius: getSceneScaleSettings(normalizedSceneScaleMode).minModelRadius,
            nearClip: Math.max(zeroPoseRadius / 1200, 0.01),
            direction: runtime.camera.position.clone().sub(controls.target).normalize().toArray(),
            up: runtime.camera.up.toArray() };
        }
        if (!restored) {
          cancelCameraTransition(runtime);
          // Fit with the destination lens. Scaling a completed projected-box
          // fit after changing FOV also scales its depth allowance, so the first
          // Render entry would frame differently from later mode switches.
          const fitFocalLength = explicitViewerFocalLength(focalLength);
          if (fitFocalLength != null) setRuntimePerspectiveFocalLength(runtime, fitFocalLength);
          zoomRuntimeToBounds(runtime, zeroPoseBounds, normalizedSceneScaleMode, {
            animate: false, modelOffset, viewDirection: DEFAULT_VIEW_DIRECTION, viewUp: WORLD_UP,
          });
          runtime.requestRender();
        }
      });
      captureRuntimeViewportFitScale(runtime);
      resetRuntimeZoomBaseline(runtime);
      syncCameraZoomPercent(runtime);
      framedModelKeyRef.current = modelKey || "";
      framedViewingModeRef.current = viewingMode;
      // The box this fit was measured against, so the next publish can tell a
      // rebuilt model from another publish of the same one.
      framedZeroPoseBoundsRef.current = zeroPoseBounds;
      lastEmittedPerspectiveRef.current = readScopedPerspectiveSnapshot(runtime, {
        modelKey,
        sceneScaleMode: normalizedSceneScaleMode
      });
    }

    // Runtime replacement can be a style change, a rapid reversal or context
    // recovery. Restore framing independently of which style last drew a frame.
    if (runtime.previousViewState) {
      if (runtime.previousViewState.modelKey === modelKey) {
        Object.assign(runtime, runtime.previousViewState.framing);
        syncCameraZoomPercent(runtime);
      }
      runtime.previousViewState = null;
    }

    recordSceneSyncTiming(sceneSyncStartedAt, { mode: reuseScene ? "reuse" : "rebuild", records: runtime.displayRecords.length, reason: rebuildReason });
    // A mode switch replaces the renderer. The parent's quality-change sample
    // can arrive before this scene is ready, so resample its framed camera on
    // construction too; otherwise the old quality remains until the next orbit.
    if (!reuseScene || modelGroupPlacementChanged) lodCameraChangeRef.current?.();
    setError("");
    runtime.requestRender();
    if (shouldRenderParts) {
      staticSceneResetRef.current.complete(staticResetRenderToken, {
        source: meshData, runtime, visualState: currentPartVisualState, clipState: clipSettingsRef.current,
      });
    }
    const adopted = runtime.cadScene === cadScene && runtime.activeModelKey === (modelKey || "") && cadScene.source === meshData;
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
    if (adopted) {
      // Also handles opening fullscreen before the first model finishes loading.
      syncFullscreenCamera(runtime);
      markPresentationReady(runtime);
    }
    } catch (error) {
      staticSceneResetRef.current.invalidate();
      if (error?.failedCadScene) {
        // Initial construction can fail before buildModel returns. Its typed
        // cleanup failure transfers the still-owned scene to this host.
        runtime.cadScene = error.failedCadScene;
        runtime.displayRecords = error.failedCadScene.displayRecords;
        modelGroup.add(error.failedCadScene.modelGroup);
        edgesGroup.add(error.failedCadScene.edgesGroup);
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
    markPresentationReady,
    modelKey,
    perspective,
    perspectiveRef,
    displayEdgesVisible,
    surfaceStepEdgesVisible,
    topologyDisplayEdgesVisible,
    recomputeNormals,
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
    normalizedSceneScaleMode,
    resolvedFloorMode,
    receiveShadows,
    renderMode,
    floorFollowsModel,
    viewerTheme,
    displayEdgeSettings,
    hiddenAwareVisualEdgeSettings,
    visualEdgeSettings,
    syncCameraZoomPercent,
    wireframeEdgeColor,
    applyActivePhotographicStudio
  ]);

  // The frame functions playback runs per clock tick; each is published by the effect
  // that owns the state it reads (`usePlaybackFrames`).
  const stepPoseFrameRef = useRef(null);
  usePlaybackFrames(useAnimationClockStore(), stepAnimationPlaying, stepPoseFrameRef);
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (
      !runtime?.THREE ||
      isLoading ||
      !effectiveRenderPartsIndividually ||
      !Array.isArray(meshData?.parts) ||
      !Array.isArray(runtime.displayRecords) ||
      !runtime.displayRecords.length
    ) {
      return;
    }
    // Component-package revisions already adopted this exact wrapper through
    // cadScene.update in the scene-sync effect above. That adoption applied
    // the changed record transforms and the same effect refreshed bounds,
    // lighting, floor and stage. Repeating this loop touched every occurrence
    // after an otherwise selective update. A wrapper that re-places a stable
    // geometrySource does not run the scene-sync effect, and its distinct
    // meshData wrapper still reaches the placement path below.
    if (sceneSourceAlreadyPlaced(runtime, meshData)) {
      return;
    }

    const partsById = new Map(
      meshData.parts.map((part) => [String(part?.id || ""), part]).filter(([partId]) => partId)
    );
    let updated = false;
    for (const record of runtime.displayRecords) {
      const part = partsById.get(String(record?.partId || ""));
      if (!part) {
        continue;
      }
      record.baseTransform = displayTransformForPart(meshData, part);
      record.partBounds = part.bounds;
      record.partCenter = readBoundsCenter(runtime.THREE, part.bounds);
      applyDisplayRecordTransform(runtime.THREE, record, runtime.modelRadius || 1);
      updated = true;
    }

    if (!updated) {
      return;
    }

    const { radius } = applyRuntimeModelBounds(runtime.THREE, runtime, meshData.bounds, normalizedSceneScaleMode, {
      shadowMapSize: renderShadowMapSizeRef.current
    });
    if (renderMode) {
      applyActivePhotographicStudio(runtime, meshData.bounds);
    } else {
      syncRuntimeScaledLightingAndShadow(
        runtime.THREE,
        runtime,
        normalizedThemeSettings.lighting,
        radius,
        meshData.bounds,
        normalizedSceneScaleMode,
        renderShadowMapSizeRef.current
      );
    }
    const cachedFloorZ = floorFollowsModel
      ? modelTransformRef.current.floorZBelowModel
      : modelTransformRef.current.floorZ;
    const floorZ = Number.isFinite(Number(cachedFloorZ))
      ? Number(cachedFloorZ)
      : resolveRuntimeModelFloorZ(
        meshData.bounds,
        runtime.modelGroup?.position,
        normalizedSceneScaleMode,
        { followModel: floorFollowsModel }
      );
    // As in the scene sync: the ground keeps the size the rest pose gave it.
    const groundRadius = sceneRadiusForBounds(runtime.THREE, meshData.restBounds || meshData.bounds, normalizedSceneScaleMode);
    updateActiveGridHelper(
      runtime,
      viewerTheme,
      groundRadius,
      floorZ,
      normalizedSceneScaleMode,
      resolvedFloorMode
    );
    if (!renderMode) {
      updateSpotLightTarget(runtime);
      updateStageEffects(runtime, viewerTheme, normalizedThemeSettings, groundRadius, runtime.gridFloorZ ?? 0, resolvedFloorMode, normalizedSceneScaleMode);
    }
    runtime.requestRender();
  }, [
    meshData?.parts,
    meshData?.bounds,
    isLoading,
    effectiveRenderPartsIndividually,
    normalizedSceneScaleMode,
    normalizedThemeSettings,
    renderMode,
    resolvedFloorMode,
    floorFollowsModel,
    viewerTheme,
    viewerReadyTick,
    updateActiveGridHelper,
    applyActivePhotographicStudio
  ]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }

    applyPartVisualState(runtime.THREE, runtime.displayRecords, partVisualStateRef.current);
    runtime.cadScene?.syncSurfaceInstances();
    runtime.requestRender();
  }, [viewerReadyTick, partVisualStateEnabled, recordEdgesVisible, focusedPartIds, hiddenPartIds, hoveredPartId, pickMode, pickableParts, selectedPartIds, viewerTheme, visualEdgeSettings, normalizedDisplayMode]);

  useEffect(() => {
    lodCameraChangeRef.current?.();
  }, [lodSelectionKey]);

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
        syncClip: (activeRuntime) => syncRuntimeStepClipPlane(activeRuntime, clipSettingsRef.current)
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
          syncClip: (activeRuntime) => syncRuntimeStepClipPlane(activeRuntime, clipSettingsRef.current)
        }
      );
      runtime.modelGroup?.updateMatrixWorld?.(true);
      runtime.edgesGroup?.updateMatrixWorld?.(true);
      const effectiveRuntime = nextEdgeRuntimes.selectorRuntime;
      // Picking is suspended during STEP animation playback, so skip rebuilding
      // pick-only state per frame; the playing->stopped rerun syncs the final pose.
      if (!stepAnimationPlaying && !animateMode) {
        syncDisplayMeshFaceIds(runtime, meshData, effectiveRuntime);
        syncSelectorPickGroups(runtime, effectiveRuntime, modelTransformRef.current.offset, { clearSceneGroup });
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

  useEffect(() => {
    const runtime = runtimeRef.current;
    const animation = explodedViewAnimationRef.current;
    cancelExplodedViewAnimation(explodedViewAnimationRef);

    if (
      !runtime?.THREE ||
      isLoading ||
      !Array.isArray(runtime.displayRecords) ||
      !runtime.displayRecords.length
    ) {
      animation.progress = 0;
      animation.modelKey = "";
      animation.enabled = false;
      animation.layout = null;
      return undefined;
    }

    const THREE = runtime.THREE;
    const animationModelKey = modelKey || "";
    const modelChanged = animation.modelKey !== animationModelKey;
    const baseBounds = runtime.modelBounds || meshData?.bounds;
    const targetProgress = explodedViewActive ? explodeAmount : 0;
    const wasEnabled = animation.enabled === true;
    animation.modelKey = animationModelKey;
    animation.enabled = explodedViewActive;

    // Steady disabled state: nothing to evaluate. (When disabling from an
    // exploded state we still evaluate below so the collapse animates.)
    if (!explodedViewActive && !wasEnabled) {
      if (!inactiveExplodedViewNeedsReset(animation, runtime.displayRecords)) {
        animation.layout = null;
        return undefined;
      }
      clearExplodedViewRecords(runtime.displayRecords);
      for (const record of runtime.displayRecords) {
        applyDisplayRecordTransform(THREE, record);
      }
      syncRecordTopologyDisplayEdgeTransforms(runtime, runtime.displayRecords);
      setExplodedViewPoseTick((tick) => tick + 1);
      runtime.requestRender?.();
      animation.progress = 0;
      animation.layout = null;
      return undefined;
    }

    // Compute the radial layout from the current records. On disable the
    // layout is still resolvable, so collapse can animate from the current
    // progress down to 0.
    const layout = computeExplodedViewLayout(runtime.displayRecords, baseBounds);
    animation.layout = layout;

    if (!layout.entries.length) {
      clearExplodedViewRecords(runtime.displayRecords);
      for (const record of runtime.displayRecords) {
        applyDisplayRecordTransform(THREE, record);
      }
      syncRecordTopologyDisplayEdgeTransforms(runtime, runtime.displayRecords);
      setExplodedViewPoseTick((tick) => tick + 1);
      runtime.requestRender?.();
      animation.progress = 0;
      return undefined;
    }

    // Animate only the enable/disable transition (explode/collapse). Amount
    // scrubs snap directly for a responsive feel — the slider is the timeline.
    const startProgress = clamp(toNumber(animation.progress, 0), 0, 1);
    const shouldAnimate = wasEnabled !== explodedViewActive && !modelChanged
      && Math.abs(targetProgress - startProgress) > 1e-4;

    if (!shouldAnimate) {
      animation.progress = targetProgress;
      applyExplodedViewRuntimeProgress(runtime, layout, targetProgress);
      setExplodedViewPoseTick((tick) => tick + 1);
      return undefined;
    }

    // Multi-level cascades get more time so each stage of the disassembly
    // still reads at a calm pace.
    const durationMs = EXPLODED_VIEW_ANIMATION_DURATION_MS
      * (1 + 0.35 * Math.max(layout.levelCount - 1, 0));
    const startedAt = typeof performance !== "undefined" && typeof performance.now === "function"
      ? performance.now()
      : Date.now();
    applyExplodedViewRuntimeProgress(runtime, layout, startProgress);

    const step = (timestamp) => {
      const now = Number.isFinite(Number(timestamp)) ? Number(timestamp) : Date.now();
      const linearProgress = clamp((now - startedAt) / durationMs, 0, 1);
      const eased = easeExplodedViewProgress(linearProgress);
      const progress = startProgress + (targetProgress - startProgress) * eased;
      animation.progress = progress;
      applyExplodedViewRuntimeProgress(runtime, layout, progress);
      if (linearProgress < 1) {
        animation.rafId = window.requestAnimationFrame(step);
      } else {
        animation.rafId = 0;
        animation.progress = targetProgress;
        setExplodedViewPoseTick((tick) => tick + 1);
      }
    };

    animation.rafId = window.requestAnimationFrame(step);
    return () => {
      cancelExplodedViewAnimation(explodedViewAnimationRef);
    };
  }, [
    explodedViewActive,
    explodeAmount,
    normalizedExplodedSettings,
    isLoading,
    meshData?.bounds,
    meshGeometrySource,
    modelKey,
    focusedPartIds.length,
    displayRecordsToken,
    normalizedSceneScaleMode,
    normalizedThemeSettings,
    viewerReadyTick
  ]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgePickGroup || !runtime?.facePickGroup || !runtime?.vertexPickGroup) {
      return;
    }

    syncDisplayMeshFaceIds(runtime, meshData, activeSelectorRuntime);
    syncSelectorPickGroups(runtime, activeSelectorRuntime, modelTransformRef.current.offset, { clearSceneGroup });
    syncRuntimeStepClipPlane(runtime, clipSettingsRef.current);
  }, [activeSelectorRuntime, meshData, modelKey, viewerReadyTick]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgesGroup) {
      return;
    }

    const transformByRecord = runtime.topologyDisplayEdgeTransformByRecord === true;
    syncTopologyDisplayEdgeLine(
      runtime,
      transformByRecord
        ? (displayEdgeRuntime || selectorRuntime)
        : (activeDisplayEdgeRuntime || activeSelectorRuntime),
      {
        visible: topologyDisplayEdgesVisible,
        edgeSettings: hiddenAwareVisualEdgeSettings,
        focusedPartIds,
        viewerTheme,
        dimmedOpacity: FOCUSED_DIMMED_SURFACE_OPACITY,
        transformByRecord,
        displayRecords: runtime.displayRecords,
        syncClip: (activeRuntime) => syncRuntimeStepClipPlane(activeRuntime, clipSettingsRef.current)
      }
    );
  }, [activeDisplayEdgeRuntime, activeSelectorRuntime, displayEdgeRuntime, viewerReadyTick, viewerTheme, focusedPartIds, hiddenAwareVisualEdgeSettings, selectorRuntime, topologyDisplayEdgesVisible, visualEdgeSettings]);



  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgesGroup) {
      return;
    }

    const { THREE, edgesGroup } = runtime;
    if (!runtime.partHighlightGroup || runtime.partHighlightGroup.parent !== edgesGroup) {
      runtime.partHighlightGroup = new THREE.Group();
      runtime.partHighlightGroup.renderOrder = 22;
      edgesGroup.add(runtime.partHighlightGroup);
    }
    const highlightGroup = runtime.partHighlightGroup;
    clearOverlayGroup(runtime, highlightGroup);

    const highlightedPartIds = [];
    const seenPartIds = new Set();
    const addHighlightedPartId = (partId) => {
      const normalizedPartId = String(partId || "").trim();
      if (!normalizedPartId || hiddenPartIdSet.has(normalizedPartId) || seenPartIds.has(normalizedPartId)) {
        return;
      }
      seenPartIds.add(normalizedPartId);
      highlightedPartIds.push(normalizedPartId);
    };
    for (const partId of normalizePartIdList(selectedPartIds)) {
      addHighlightedPartId(partId);
    }
    for (const partId of normalizePartIdList(hoveredPartId)) {
      addHighlightedPartId(partId);
    }

    if (topologyDisplayEdgesVisible && highlightedPartIds.length) {
      const highlightEdgeSettings = {
        ...hiddenAwareVisualEdgeSettings,
        thickness: getHighlightEdgeThickness(displayEdgeSettings, viewerTheme),
        highlightPartIds: highlightedPartIds,
        highlightColor: getHighlightEdgeColor(displayEdgeSettings),
        highlightOpacity: getHighlightEdgeOpacity(displayEdgeSettings),
        highlightRenderOrder: 26
      };
      const highlightLine = runtime.topologyDisplayEdgeTransformByRecord === true && displayEdgeRuntime
        ? createRecordTopologyDisplayEdgeGroup(runtime, displayEdgeRuntime, {
            edgeSettings: highlightEdgeSettings,
            viewerTheme,
            displayRecords: runtime.displayRecords
          })
        : createSharedTopologyDisplayEdgeObject(
            runtime,
            activeDisplayEdgeRuntime || activeSelectorRuntime,
            highlightEdgeSettings,
            viewerTheme
          );
      if (highlightLine) {
        highlightGroup.add(highlightLine);
      }
    }

    highlightGroup.visible = highlightGroup.children.length > 0;
    runtime.requestRender();

    return () => {
      clearOverlayGroup(runtime, highlightGroup);
    };
  }, [
    activeDisplayEdgeRuntime,
    activeSelectorRuntime,
    displayEdgeRuntime,
    displayEdgeSettings,
    hiddenAwareVisualEdgeSettings,
    hiddenPartIdSet,
    viewerReadyTick,
    viewerTheme,
    hoveredPartId,
    modelKey,
    selectedPartIds,
    topologyDisplayEdgesVisible,
    visualEdgeSettings
  ]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgesGroup || !runtime?.modelGroup) {
      return;
    }

    const { THREE, edgesGroup, modelGroup } = runtime;
    if (!runtime.referenceHighlightGroup || runtime.referenceHighlightGroup.parent !== edgesGroup) {
      runtime.referenceHighlightGroup = new THREE.Group();
      runtime.referenceHighlightGroup.renderOrder = 25;
      edgesGroup.add(runtime.referenceHighlightGroup);
    }
    const highlightGroup = runtime.referenceHighlightGroup;
    if (!runtime.referenceFaceFillGroup || runtime.referenceFaceFillGroup.parent !== modelGroup) {
      runtime.referenceFaceFillGroup = new THREE.Group();
      runtime.referenceFaceFillGroup.renderOrder = 24;
      modelGroup.add(runtime.referenceFaceFillGroup);
    }
    const faceFillGroup = runtime.referenceFaceFillGroup;

    clearOverlayGroup(runtime, highlightGroup);
    clearOverlayGroup(runtime, faceFillGroup);
    const selectedLineWidth = getHighlightEdgeThickness(displayEdgeSettings, viewerTheme);
    const hoveredLineWidth = selectedLineWidth;
    const highlightEdgeColor = getHighlightEdgeColor(displayEdgeSettings);
    const highlightEdgeOpacity = getHighlightEdgeOpacity(displayEdgeSettings);
    // In measure mode the snapped topology still needs a visible target, but the
    // full-strength face fill would compete with the amber/cyan annotations.
    const measureHoverHighlightOpacity = measureModeActive
      ? Math.max(0.08, highlightEdgeOpacity * 0.35)
      : highlightEdgeOpacity;

    const highlightReferenceStates = new Map();
    const runtimeReferences = Array.isArray(activeSelectorRuntime?.references)
      ? activeSelectorRuntime.references
      : activeSelectorRuntime?.referenceMap instanceof Map
        ? [...activeSelectorRuntime.referenceMap.values()]
        : [];
    const addHighlightReference = (referenceId, { hovered = false } = {}) => {
      const normalizedReferenceId = String(referenceId || "").trim();
      if (!normalizedReferenceId) {
        return;
      }
      const current = highlightReferenceStates.get(normalizedReferenceId);
      if (current) {
        current.hovered = current.hovered || hovered;
        return;
      }
      highlightReferenceStates.set(normalizedReferenceId, { hovered });
    };
    const addReferenceSelection = (referenceId, { hovered = false } = {}) => {
      const normalizedReferenceId = String(referenceId || "").trim();
      const topologyReference = pickableReferenceMap.get(normalizedReferenceId) || activeSelectorRuntime?.referenceMap?.get(normalizedReferenceId) || null;
      if (!topologyReference) {
        const syntheticOccurrenceSelector = syntheticOccurrenceSelectorFromReferenceId(normalizedReferenceId);
        if (syntheticOccurrenceSelector) {
          for (const childReference of runtimeReferences) {
            const childSelectorType = referenceSelectorType(childReference);
            if (
              (childSelectorType === "face" || childSelectorType === "edge" || childSelectorType === "vertex") &&
              referenceMatchesOccurrenceSubtree(childReference, syntheticOccurrenceSelector)
            ) {
              addHighlightReference(childReference?.id, { hovered });
            }
          }
        }
        return;
      }
      const selectorType = referenceSelectorType(topologyReference);
      if (selectorType === "occurrence") {
        const occurrenceSelector = referenceOccurrenceSelector(topologyReference);
        for (const childReference of runtimeReferences) {
          const childSelectorType = referenceSelectorType(childReference);
          if (
            (childSelectorType === "face" || childSelectorType === "edge" || childSelectorType === "vertex") &&
            referenceMatchesOccurrenceSubtree(childReference, occurrenceSelector)
          ) {
            addHighlightReference(childReference?.id, { hovered });
          }
        }
        return;
      }
      if (selectorType === "shape") {
        const shapeSelector = referenceShapeSelector(topologyReference);
        const occurrenceSelector = referenceOccurrenceSelector(topologyReference);
        for (const childReference of runtimeReferences) {
          const childSelectorType = referenceSelectorType(childReference);
          if (
            (childSelectorType === "face" || childSelectorType === "edge" || childSelectorType === "vertex") &&
            referenceMatchesShape(childReference, shapeSelector, occurrenceSelector)
          ) {
            addHighlightReference(childReference?.id, { hovered });
          }
        }
        return;
      }
      addHighlightReference(normalizedReferenceId, { hovered });
    };
    for (const referenceId of Array.isArray(selectedReferenceIds) ? selectedReferenceIds : []) {
      addReferenceSelection(referenceId);
    }
    const normalizedHoveredReferenceId = String(hoveredReferenceId || "").trim();
    if (normalizedHoveredReferenceId) {
      addReferenceSelection(normalizedHoveredReferenceId, { hovered: true });
    }

    for (const [referenceId, highlightState] of highlightReferenceStates.entries()) {
      const topologyReference = pickableReferenceMap.get(referenceId) || activeSelectorRuntime?.referenceMap?.get(referenceId) || null;
      if (!topologyReference) {
        continue;
      }
      const selectorType = referenceSelectorType(topologyReference);
      if (selectorType !== "face" && selectorType !== "edge" && selectorType !== "vertex") {
        continue;
      }

      const isHovered = Boolean(highlightState?.hovered);
      if (selectorType === "vertex") {
        const marker = buildVertexMarkerMesh(runtime, THREE, topologyReference, {
          color: REFERENCE_CORNER_COLOR,
          opacity: isHovered ? 0.96 : 0.88,
        });
        if (marker) {
          highlightGroup.add(marker);
        }
        continue;
      }

      const highlightColor = highlightEdgeColor;

      const linePositions = selectorType === "edge"
        ? buildEdgeLinePositionsFromProxy(activeSelectorRuntime, topologyReference)
        : buildFaceBoundaryLinePositions(activeSelectorRuntime, topologyReference);
      if (linePositions?.length) {
        const referenceVisibilityClass = selectorType === "edge"
          ? activeSelectorRuntime?.edges?.[topologyReference.rowIndex]?.visibilityClass || ""
          : "";
        const lineWidth = isHovered ? hoveredLineWidth : selectedLineWidth;
        const line = createScreenSpaceLineSegments(runtime, linePositions, {
          color: highlightColor,
          opacity: isHovered ? measureHoverHighlightOpacity : highlightEdgeOpacity,
          lineWidth,
          renderOrder: 26,
          depthTest: selectorType !== "edge",
          depthWrite: false,
          depthBias: topologyLineDepthBiasForWidth(lineWidth, { visibilityClass: referenceVisibilityClass })
        });
        if (line) {
          // The pick proxy these positions come from is world-at-rest; the exploded view moves
          // the MESH and leaves the proxy alone, so without this the highlight for an exploded
          // part draws where the part sits when collapsed. The face fill below needs no such
          // matrix -- it is rebuilt from the live meshes, which already carry the offset.
          const explodeMatrix = referenceExplodedViewMatrix(runtime, topologyReference);
          if (explodeMatrix) {
            line.matrixAutoUpdate = false;
            line.matrix.copy(explodeMatrix);
            line.matrixWorldNeedsUpdate = true;
          }
          highlightGroup.add(line);
        }
      }

      if (selectorType === "face") {
        const fillGeometry = buildFaceFillGeometryFromDisplayMeshes(runtime, THREE, topologyReference) ||
          buildFaceFillGeometryFromProxy(runtime, THREE, activeSelectorRuntime, topologyReference);
        if (fillGeometry) {
          const fillOpacity = isHovered ? measureHoverHighlightOpacity : highlightEdgeOpacity;
          const fillMaterial = new THREE.MeshBasicMaterial({
            color: highlightColor,
            transparent: fillOpacity < 0.999,
            opacity: fillOpacity,
            depthTest: true,
            depthWrite: false,
            polygonOffset: true,
            polygonOffsetFactor: -2,
            polygonOffsetUnits: -2,
            side: THREE.DoubleSide,
            toneMapped: false
          });
          const fillMesh = new THREE.Mesh(fillGeometry, fillMaterial);
          fillMesh.renderOrder = 25;
          faceFillGroup.add(fillMesh);
        }
      }
    }

    highlightGroup.visible = highlightGroup.children.length > 0;
    faceFillGroup.visible = faceFillGroup.children.length > 0;
    runtime.requestRender();

    return () => {
      clearOverlayGroup(runtime, highlightGroup);
      clearOverlayGroup(runtime, faceFillGroup);
    };
  }, [activeSelectorRuntime, explodedViewPoseTick, hoveredReferenceId, pickableReferenceMap, selectedReferenceIds, viewerReadyTick, viewerTheme, displayEdgeSettings, measureModeActive]);

  // Click is followed by OrbitControls clearing hover before React commits
  // draft.anchor, so the locked first point lives in a ref.
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

  useViewerMeasureOverlay({
    measureCanvasRef,
    measureState,
    activeMeasurementId,
    measureHoverRef,
    measureModeActive,
    runtimeRef,
    mountRef,
    previewMode,
    viewerReadyTick
  });

  useViewerPicking({
    runtimeRef,
    mountRef: interactionHostRef,
    sceneMountRef: mountRef,
    previewMode,
    pickMode,
    selectorRuntime: activeSelectorRuntime,
    pickableFaces: filteredPickableFaces,
    pickableEdges: filteredPickableEdges,
    pickableVertices: filteredPickableVertices,
    hiddenPartIds,
    focusedPartId: focusedPartIds,
    onHoverReferenceChange,
    onActivateReference,
    onDoubleActivateReference,
    onContextReference,
    onMeasurePick: handleMeasurePick,
    onMeasureHoverPoint: handleMeasureHoverPoint,
    viewerReadyTick,
    suppressTopologyPicking: animateMode || Array.isArray(jointHandles) || stepAnimationPlaying,
    allowMeshVertexSnap
  });

  // Runs after scene/material/clip effects. Controls already show desired values;
  // this acknowledgement concerns only the applied viewport revision.
  useEffect(() => {
    if (!viewUpdate?.revision) return;
    const { revision, expensive, binding } = viewUpdate;
    const runtime = runtimeRef.current;
    let cancelled = false;
    const complete = error => {
      if (cancelled) return;
      const acknowledged = binding.complete(revision, error);
      // Context recovery can recreate a runtime after this revision was
      // already acknowledged. That new canvas still needs its first frame.
      if (!acknowledged && !error) runtime?.viewUpdateGate?.present().catch(() => {});
    };
    if (!runtime) { complete(); return; }
    runtime.viewUpdateGate ??= createViewUpdateGate(runtime);
    runtime.viewUpdateGate.hold();
    (expensive ? runtime.viewUpdateGate.compile() : Promise.resolve()).then(() => complete(), complete);
    return () => { cancelled = true; };
  }, [viewUpdate?.revision, viewUpdate?.binding, viewerReadyTick]);

  const hasPresentableContent = hasViewportContent;
  const preparingFrame = Boolean(resolvedPresentationKey) &&
    (presentedEpoch !== presentationEpoch || presentedKey !== resolvedPresentationKey) && !error;
  const coveringModeTransition = presentedEpoch !== presentationEpoch && !error && hasPresentableContent;
  useEffect(() => {
    onPresentationChange?.({
      file: modelKey,
      renderMode,
      key: resolvedPresentationKey,
      preparing: Boolean(preparingFrame),
      covering: Boolean(coveringModeTransition),
    });
  }, [modelKey, renderMode, resolvedPresentationKey, preparingFrame, coveringModeTransition, onPresentationChange]);
  const transitionBackdrop = viewerTransitionBackdrop({
    renderMode, renderConfiguration, background: normalizedThemeSettings.background, viewerTheme
  });

  return (
    <div
      ref={interactionHostRef}
      className="relative h-full w-full"
      style={coveringModeTransition ? { backgroundColor: transitionBackdrop.backgroundColor } : undefined}
      aria-busy={preparingFrame}
    >
      <div className="h-full w-full" ref={mountRef} />
      {coveringModeTransition ? (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center" style={transitionBackdrop} role="status" data-viewer-transition={renderMode ? "render" : "inspect"}>
          <LoadingIndicator
            progress={loadingPresentation?.busy ? loadingPresentation.progress : { label: "Preparing view" }}
            operationKey={`${resolvedPresentationKey}:${renderMode}`}
          />
        </div>
      ) : null}
      <canvas
        ref={measureCanvasRef}
        className="absolute inset-0 z-10 h-full w-full touch-none"
        style={{ pointerEvents: "none" }}
        aria-hidden="true"
      />
      {drawingOverlayActive ? <DrawingOverlay drawing={drawing} onReady={handleDrawingReady} onContentChange={handleDrawingContent} onViewportChange={followDrawingViewport} /> : null}
      {jointHandles ? <JointHandleOverlay handles={jointHandles} runtimeRef={runtimeRef} hostRef={interactionHostRef} layoutSeamRef={jointHandleLayoutRef} viewerReadyTick={viewerReadyTick} /> : null}
      <ViewPlaneControl
        showViewPlane={showViewPlane && !drawingOverlayActive}
        previewMode={previewMode}
        isLoading={isLoading}
        meshData={viewportContent}
        viewPlaneOffsetRight={viewPlaneOffsetRight}
        viewPlaneOffsetBottom={viewPlaneOffsetBottom}
        viewPlaneSize={VIEW_PLANE_CONTROL_SIZE}
        viewPlaneHeader={viewPlaneHeader}
        compact={compactViewPlane}
        activeViewPlaneFace={activeViewPlaneFace}
        viewPlaneFaces={VIEW_PLANE_FACES}
        viewPlaneOrientation={viewPlaneOrientation}
        viewerTheme={viewerTheme}
        activateViewPlaneFace={activateViewPlaneFace}
        activateDefaultViewPlane={activateDefaultViewPlane}
      />
      {error ? (
        <p className="bg-popover pointer-events-none absolute left-4 top-24 z-20 rounded-lg border border-error-border px-4 py-3 text-sm text-error shadow-sm sm:top-20">
          {error}
        </p>
      ) : null}
    </div>
  );
});

export default CadViewer;

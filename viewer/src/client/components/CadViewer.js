"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { Minus, Plus, RotateCcw } from "lucide-react";
import { parseCadRefToken } from "cadjs/lib/cadRefs";
import {
  dxfBendGuideSegments,
  dxfFlatPatternExtents,
  dxfFoldIsIdentity,
  foldDxfPoint,
  normalizeDxfFoldOptions,
  transformDxfPreviewPositions
} from "cadjs/lib/dxf/foldPreview";
import { buildDxfPreviewMeshData, extractDxfScorePolylines } from "cadjs/lib/dxf/buildPreviewMesh";
import { STEP_TREE_TOPOLOGY_NODE_PREFIX } from "cadjs/lib/step/stepTree";
import { copyImageBlobToClipboard } from "@/ui/clipboard";
import { triggerBlobDownload } from "@/ui/download";
import {
  annotatePerspectiveSnapshot,
  CAMERA_PROJECTION,
  clonePerspectiveSnapshot,
  normalizeCameraProjection,
  perspectiveSnapshotEqual,
  perspectiveSnapshotMatchesScene,
  resolvePerspectiveSnapshot
} from "cadjs/lib/perspective";
import { VIEWER_PICK_MODE } from "cadjs/lib/viewer/constants";
import { normalizeStepClipSettings } from "cadjs/lib/viewer/clipPlane";
import {
  buildDrawingPoint,
  distanceToStrokeInPixels,
  drawingToolNeedsTwoPoints,
  isSurfaceLineStroke,
  strokeLengthInPixels
} from "cadjs/lib/viewer/drawingGeometry";
import {
  buildFillStrokeAtPoint,
  DRAWING_ERASE_THRESHOLD_PX,
  DRAWING_MIN_POINT_DISTANCE_PX,
  DRAWING_MIN_STROKE_LENGTH_PX,
  maxDrawingStrokeOrdinal,
  redrawDrawingCanvas,
  SURFACE_LINE_COLOR
} from "cadjs/lib/viewer/drawingCanvas";
import {
  shouldBuildDerivedDisplayEdges,
  shouldShowRecordDisplayEdges
} from "cadjs/lib/viewer/displayEdgePolicy";
import {
  displayModeForcesEdges,
  displayModeIsWireframe,
  displayModeShowsEdges,
  displayModeShowsThroughEdges,
  resolveDisplayEdgeSettings
} from "cadjs/lib/displaySettings";
import {
  createUrdfPosePickerHoverCellMesh,
  createUrdfPosePickerHoverCellOutline,
  createUrdfPosePickerShell,
  intersectUrdfPosePickerShell,
  resolveUrdfPosePickerShell,
  syncUrdfPosePickerHoverObjects
} from "cadjs/lib/viewer/urdfPosePicker";
import {
  clampSceneModelRadius,
  defaultSceneGridRadius,
  getLightingScopeRadius,
  getProportionalLightingScopeRadius,
  getSceneScaleSettings,
  normalizeSceneScaleMode,
  VIEWER_SCENE_SCALE
} from "cadjs/lib/viewer/sceneScale";
import {
  applySceneBackground,
  BASE_VIEWER_THEME,
  createStageFloorGlowPlane,
  createStageFloorPlane,
  createStageShadowPlane,
  disposeTexture,
  getViewerThemeNumber,
  getViewerThemeValue,
  getStageFloorSize,
  normalizeFloorMode,
  resolveWireframeEdgeColor,
  updateSpotLightTarget
} from "cadjs/lib/viewer/stageTheme";
import {
  updateGridHelper as updateStageGridHelper,
  updateOriginAxis as updateStageOriginAxis
} from "cadjs/lib/viewer/stageGrid";
import {
  autoZoomFrameForBounds,
  DEFAULT_AUTO_ZOOM_PADDING,
  displayRecordsBounds,
  mergeBoundsList
} from "cadjs/lib/viewer/autoZoom";
import { applyMaterialSettingsToRecord } from "cadjs/lib/viewer/surfaceMaterials";
import {
  applyPartVisualState,
  FOCUSED_DIMMED_SURFACE_OPACITY,
  normalizePartIdList,
  referenceMatchesFocusedPart
} from "cadjs/lib/viewer/partVisualState";
import {
  createRecordTopologyDisplayEdgeGroup,
  syncRecordTopologyDisplayEdgeTransforms,
  syncTopologyDisplayEdgeLine
} from "cadjs/lib/viewer/topologyDisplayEdgeLine";
import {
  applyExplodedViewProgress,
  clearExplodedViewRecords,
  computeExplodedViewLayout,
  easeExplodedViewProgress
} from "cadjs/lib/viewer/explodedView";
import {
  applyDisplayRecordTransform,
  applyRuntimeModelBounds,
  readBoundsCenter,
  resolveRuntimeModelFloorZ,
  runtimeModelKeyMatches,
  syncRuntimeStepClipPlane,
  toNumber
} from "cadjs/lib/viewer/modelRuntime";
import {
  buildGlbFaceIdsForMesh,
  buildGlbFaceIdsForPart,
  syncDisplayMeshFaceIds,
  syncSelectorPickGroups
} from "cadjs/lib/viewer/selectorPickGroups";
import { scheduleRuntimeRaycastBvh } from "cadjs/lib/viewer/raycastBvh";
import {
  buildSurfaceLinePositions,
  projectPointToSurfaceUv,
  SURFACE_LINE_UNSUPPORTED_TYPES
} from "cadjs/lib/viewer/surfaceLineGeometry";
import {
  buildCompositeScreenshotBlob,
  resolveElementBackgroundColor
} from "cadjs/lib/viewer/screenshotCapture";
import {
  buildEdgeLinePositionsFromProxy,
  buildFaceBoundaryLinePositions,
  buildFaceFillGeometryFromDisplayMeshes,
  buildFaceFillGeometryFromProxy,
  buildVertexMarkerMesh,
  REFERENCE_CORNER_COLOR,
  REFERENCE_HIGHLIGHT_WIDTH_MULTIPLIER,
  REFERENCE_SELECTED_COLOR
} from "cadjs/lib/viewer/referenceGeometry";
import { buildRuntimeInitializationAlert } from "cadjs/lib/viewer/webglSupport";
import { DRAWING_TOOL } from "@/workbench/constants";
import {
  hasCapability,
  viewportContentKind,
  VIEWPORT_CONTENT
} from "cadjs/lib/renderCapabilities";
import {
  getEnvironmentPresetById,
  THEME_FLOOR_MODES
} from "cadjs/lib/themeSettings";
import ViewPlaneControl from "./viewer/ViewPlaneControl";
import { useImplicitRaymarch } from "./viewer/hooks/useImplicitRaymarch";
import { useViewerDrawingOverlay } from "./viewer/hooks/useViewerDrawingOverlay";
import { useViewerPicking } from "./viewer/hooks/useViewerPicking";
import { useViewerRuntime } from "./viewer/hooks/useViewerRuntime";
import { PREVIEW_AUTO_ROTATE_SPEED } from "./viewer/orbitControls";
import {
  applyOrbitDelta,
  cameraMatchesViewPreset,
  clamp,
  clearKeyboardOrbitState,
  DEFAULT_VIEW_DIRECTION,
  DEFAULT_VIEW_PLANE_ORIENTATION,
  easeInOutCubic,
  getActiveViewPlaneFaceId,
  getKeyboardOrbitAxes,
  getKeyboardOrbitCommand,
  isTrackpadLikeWheelEvent,
  KEYBOARD_ORBIT_NUDGE_RAD,
  normalizeViewportFrameInsets,
  readViewPlaneOrientation,
  stepKeyboardOrbit,
  VIEW_PLANE_DEFAULT_PRESET,
  VIEW_PLANE_FACE_BY_ID,
  VIEW_PLANE_FACES,
  VIEW_PLANE_POLE_DIRECTION_DOT_THRESHOLD,
  VIEW_PLANE_POLE_DIRECTION_NUDGE,
  VIEW_PLANE_TRANSITION_MS,
  viewPlaneOrientationEqual,
  viewportFitScale,
  WORLD_UP
} from "./viewer/viewportCameraKit";
import { normalizeViewerRenderState } from "./viewer/renderState";
import {
  buildModel,
  effectiveBoundsFromRecords
} from "cadjs/common/cadScene";
import {
  resolveTopologyDisplayEdgeRuntimes,
  shouldRenderTopologyDisplayEdges,
  shouldUseRecordTopologyEdgeTransforms
} from "cadjs/common/topologyDisplayEdgeRuntime";
import {
  createScreenSpaceLineSegments,
  createTopologyDisplayEdgeObject as createSharedTopologyDisplayEdgeObject,
  topologyLineDepthBiasForWidth
} from "cadjs/common/renderEdges";
import {
  resolveStepModuleFeatures
} from "cadjs/common/stepModule";
import {
  applyStepModuleEffectsToRecords,
  buildStepModuleContext,
  createStepModuleEffectsApi,
  displayTransformForPart,
  resetStepModuleRecordEffects
} from "cadjs/common/stepModuleEffects";

const IDLE_PIXEL_RATIO_CAP = 2;
const INTERACTION_PIXEL_RATIO_CAP = 1.25;
const INTERACTION_IDLE_DELAY_MS = 140;
const DEFAULT_DAMPING_FACTOR = 0.14;
const DEFAULT_ZOOM_SPEED = 4.5;
const COARSE_POINTER_ZOOM_SPEED = 1.6;
const EXPLODED_VIEW_ANIMATION_DURATION_MS = 1000;
const ACCELERATED_WHEEL_ZOOM_SPEED = 10;
const TRACKPAD_PINCH_ZOOM_SPEED = 14;
const COARSE_POINTER_PINCH_ZOOM_SPEED = 2.4;
const CAMERA_TRANSITION_EASING = Object.freeze({
  EASE_IN_OUT_CUBIC: "ease-in-out-cubic",
  EASE_IN_OUT_SINE: "ease-in-out-sine"
});
const AUTO_ZOOM_PADDING = DEFAULT_AUTO_ZOOM_PADDING;
const CAD_COORDINATE_SYSTEM = "cad-z-up-v1";
const ROBOT_COORDINATE_SYSTEM = "cad-z-up-robot-framing-v2";
const DISPLAY_TOOLBAR_CLASSES = "cad-glass-surface pointer-events-auto absolute z-30 inline-flex h-8 w-fit items-center gap-0.5 rounded-md border border-sidebar-border p-1 text-sidebar-foreground shadow-sm";
const DISPLAY_TOOLBAR_BUTTON_CLASSES = "grid size-6 shrink-0 place-items-center rounded-sm text-sidebar-foreground/70 transition hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 disabled:pointer-events-none disabled:opacity-50";
const VIEW_PLANE_CONTROL_SIZE = "7.5rem";
const VIEW_PLANE_CONTROL_GAP = "0.5rem";
const ZOOM_CONTROL_CONTENT_WIDTH = "6.875rem";
const ZOOM_CONTROL_MIN_PERCENT = 10;
const ZOOM_CONTROL_MAX_PERCENT = 800;
const ZOOM_CONTROL_STEP_PERCENT = 10;
const CAD_EDGE_OPACITY = 0.84;
const DEFAULT_LIGHTING = {
  toneMappingExposure: 1.08,
  hemisphereSky: "#d3dde6",
  hemisphereGround: "#090c16",
  hemisphereIntensity: 1.62,
  keyLightColor: "#d6e0ea",
  keyLightIntensity: 0.82,
  fillLightColor: "#6b7f95",
  fillLightIntensity: 0.46,
  rimLightColor: "#6db6e8",
  rimLightIntensity: 0.04
};
const BEND_GUIDE_COLOR = "#f59e0b";
const BEND_GUIDE_WIDTH_MULTIPLIER = 1.35;

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

function normalizeZoomPercent(value, fallback = 100) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return fallback;
  }
  return clamp(numeric, ZOOM_CONTROL_MIN_PERCENT, ZOOM_CONTROL_MAX_PERCENT);
}

function formatZoomPercent(value) {
  return `${Math.round(normalizeZoomPercent(value))}%`;
}

function readCameraTargetDistance(runtime) {
  if (!runtime?.camera?.position || !runtime?.controls?.target) {
    return null;
  }
  const distance = runtime.camera.position.distanceTo(runtime.controls.target);
  return Number.isFinite(distance) && distance > 1e-6 ? distance : null;
}

function readOrthographicHalfHeight(runtime) {
  const camera = runtime?.camera?.isOrthographicCamera
    ? runtime.camera
    : runtime?.orthographicCamera;
  if (!camera?.isOrthographicCamera) {
    return null;
  }
  const storedHalfHeight = Number(camera.userData?.cadHalfHeight);
  if (Number.isFinite(storedHalfHeight) && storedHalfHeight > 1e-6) {
    return storedHalfHeight;
  }
  const derivedHalfHeight = Math.abs((Number(camera.top) || 0) - (Number(camera.bottom) || 0)) / 2;
  return Number.isFinite(derivedHalfHeight) && derivedHalfHeight > 1e-6 ? derivedHalfHeight : null;
}

// Radius of a bounds box, matching applyRuntimeModelBounds so the base and posed
// radii are directly comparable.
function boundsModelRadius(THREE, bounds, sceneScaleMode) {
  const min = Array.isArray(bounds?.min) ? bounds.min : null;
  const max = Array.isArray(bounds?.max) ? bounds.max : null;
  if (!THREE || !min || !max) {
    return 0;
  }
  return clampSceneModelRadius(
    new THREE.Vector3(
      toNumber(max[0]) - toNumber(min[0]),
      toNumber(max[1]) - toNumber(min[1]),
      toNumber(max[2]) - toNumber(min[2])
    ).length() / 2,
    sceneScaleMode
  );
}

// 100% means "framed to the model at rest". The camera is always fitted to the
// CURRENT pose, so when a parameter sidecar opens a model mid-animation -- an
// extended lift, an exploded assembly -- fitting that pose would define the
// enlarged framing as 100%. Framing distance and orthographic half-height are
// both proportional to model radius, so scaling the captured value by
// base/fitted radius recovers the at-rest baseline. A model whose animation
// opens 1.5x larger now reads ~67%, which is what it is.
//
// zoomFitModelRadius is the radius of the bounds the camera was last fitted to;
// runtime.modelRadius is only a fallback because it tracks whichever bounds were
// applied last, which is not always what the camera framed.
function runtimeZoomBaselineScale(runtime) {
  const baseRadius = Number(runtime?.zoomBaseModelRadius);
  const fittedRadius = Number(runtime?.zoomFitModelRadius) > 1e-6
    ? Number(runtime.zoomFitModelRadius)
    : Number(runtime?.modelRadius);
  if (
    !Number.isFinite(baseRadius) || baseRadius <= 1e-6 ||
    !Number.isFinite(fittedRadius) || fittedRadius <= 1e-6
  ) {
    return 1;
  }
  return baseRadius / fittedRadius;
}

function resetRuntimeZoomBaseline(runtime) {
  const scale = runtimeZoomBaselineScale(runtime);
  // The baseline is only ever reset right after the camera has been fitted, so
  // this is also the moment the framing matches the live viewport.
  captureRuntimeViewportFitScale(runtime);
  if (runtime?.camera?.isOrthographicCamera) {
    const halfHeight = readOrthographicHalfHeight(runtime);
    if (halfHeight) {
      runtime.zoomBaseHalfHeight = halfHeight * scale;
      return runtime.zoomBaseHalfHeight;
    }
    return halfHeight;
  }
  const distance = readCameraTargetDistance(runtime);
  if (distance) {
    runtime.zoomBaseDistance = distance * scale;
    return runtime.zoomBaseDistance;
  }
  return distance;
}

function readRuntimeZoomPercent(runtime) {
  const camera = runtime?.camera;
  if (!camera) {
    return 100;
  }
  const cameraZoom = Number.isFinite(Number(camera.zoom)) && Number(camera.zoom) > 0
    ? Number(camera.zoom)
    : 1;
  if (camera.isOrthographicCamera) {
    const halfHeight = readOrthographicHalfHeight(runtime);
    if (!halfHeight) {
      return normalizeZoomPercent(cameraZoom * 100);
    }
    const baseHalfHeight = Number(runtime.zoomBaseHalfHeight);
    const normalizedBaseHalfHeight = Number.isFinite(baseHalfHeight) && baseHalfHeight > 1e-6
      ? baseHalfHeight
      : resetRuntimeZoomBaseline(runtime) || halfHeight;
    return normalizeZoomPercent((normalizedBaseHalfHeight / halfHeight) * cameraZoom * 100);
  }
  const distance = readCameraTargetDistance(runtime);
  if (!distance) {
    return normalizeZoomPercent(cameraZoom * 100);
  }
  const baseDistance = Number(runtime.zoomBaseDistance);
  const normalizedBaseDistance = Number.isFinite(baseDistance) && baseDistance > 1e-6
    ? baseDistance
    : resetRuntimeZoomBaseline(runtime) || distance;
  return normalizeZoomPercent((normalizedBaseDistance / distance) * cameraZoom * 100);
}

function setRuntimeZoomPercent(runtime, percent) {
  if (!runtime?.THREE || !runtime?.camera || !runtime?.controls?.target) {
    return false;
  }
  const nextZoom = normalizeZoomPercent(percent) / 100;
  const camera = runtime.camera;
  cancelCameraTransition(runtime, { scheduleIdle: false });
  clearKeyboardOrbitState(runtime.keyboardOrbitState);
  if (camera.isOrthographicCamera) {
    const halfHeight = readOrthographicHalfHeight(runtime) || 1;
    const baseHalfHeight = Number(runtime.zoomBaseHalfHeight);
    const normalizedBaseHalfHeight = Number.isFinite(baseHalfHeight) && baseHalfHeight > 1e-6
      ? baseHalfHeight
      : halfHeight;
    runtime.zoomBaseHalfHeight = normalizedBaseHalfHeight;
    camera.zoom = nextZoom * (halfHeight / normalizedBaseHalfHeight);
    camera.updateProjectionMatrix?.();
    reapplyRuntimeCameraFrameInsets(runtime);
  } else {
    const target = runtime.controls.target;
    const offset = camera.position.clone().sub(target);
    const direction = offset.lengthSq() > 1e-8
      ? offset.normalize()
      : new runtime.THREE.Vector3(...DEFAULT_VIEW_DIRECTION).normalize();
    const distance = readCameraTargetDistance(runtime) || direction.length() || 1;
    const baseDistance = Number(runtime.zoomBaseDistance);
    const normalizedBaseDistance = Number.isFinite(baseDistance) && baseDistance > 1e-6
      ? baseDistance
      : distance;
    runtime.zoomBaseDistance = normalizedBaseDistance;
    const minDistance = Number.isFinite(Number(runtime.controls.minDistance))
      ? Number(runtime.controls.minDistance)
      : 0.01;
    const maxDistance = Number.isFinite(Number(runtime.controls.maxDistance)) && Number(runtime.controls.maxDistance) > 0
      ? Number(runtime.controls.maxDistance)
      : Number.POSITIVE_INFINITY;
    const nextDistance = clamp(normalizedBaseDistance / nextZoom, minDistance, maxDistance);
    camera.position.copy(target.clone().add(direction.multiplyScalar(nextDistance)));
    camera.zoom = 1;
    camera.updateProjectionMatrix?.();
    reapplyRuntimeCameraFrameInsets(runtime);
  }
  camera.lookAt(runtime.controls.target);
  runtime.controls.update?.();
  runtime.scheduleIdleQuality?.();
  runtime.requestRender?.();
  return true;
}

function cssLength(value, fallback = "0px") {
  if (typeof value === "number" && Number.isFinite(value)) {
    return `${value}px`;
  }
  const text = String(value || "").trim();
  return text || fallback;
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

// An implicit is never re-centred (its SDF is evaluated in world space), so the
// stage helpers that take a model position get the origin.
const ORIGIN_MODEL_POSITION = Object.freeze({ x: 0, y: 0, z: 0 });

function getPixelRatioCap(cap) {
  if (typeof window === "undefined") {
    return 1;
  }
  return Math.min(window.devicePixelRatio || 1, cap);
}

function getStageEffectRadius(radius, sceneScaleMode = VIEWER_SCENE_SCALE.CAD) {
  return getProportionalLightingScopeRadius(radius, sceneScaleMode);
}

function getStageEffectScale(radius, sceneScaleMode = VIEWER_SCENE_SCALE.CAD) {
  const referenceRadius = Math.max(
    getLightingScopeRadius(sceneScaleMode),
    getSceneScaleSettings(sceneScaleMode).minModelRadius
  );
  return getStageEffectRadius(radius, sceneScaleMode) / referenceRadius;
}

function setScaledLightPosition(light, position = {}, scale = 1) {
  light?.position?.set?.(
    (Number(position.x) || 0) * scale,
    (Number(position.y) || 0) * scale,
    (Number(position.z) || 0) * scale
  );
}

function scaledLightDistance(distance, scale = 1) {
  const numericDistance = Number(distance);
  return Number.isFinite(numericDistance) && numericDistance > 0
    ? numericDistance * scale
    : 0;
}

function syncRuntimeScaledLighting(runtime, lightingSettings = {}, radius, sceneScaleMode = VIEWER_SCENE_SCALE.CAD) {
  const scale = getStageEffectScale(radius, sceneScaleMode);
  setScaledLightPosition(runtime?.keyLight, lightingSettings.directional?.position, scale);
  if (lightingSettings.fill?.position) {
    setScaledLightPosition(runtime?.fillLight, lightingSettings.fill.position, scale);
  }
  if (lightingSettings.rim?.position) {
    setScaledLightPosition(runtime?.rimLight, lightingSettings.rim.position, scale);
  }
  setScaledLightPosition(runtime?.spotLight, lightingSettings.spot?.position, scale);
  setScaledLightPosition(runtime?.pointLight, lightingSettings.point?.position, scale);
  if (runtime?.spotLight) {
    runtime.spotLight.distance = scaledLightDistance(lightingSettings.spot?.distance, scale);
  }
  if (runtime?.pointLight) {
    runtime.pointLight.distance = scaledLightDistance(lightingSettings.point?.distance, scale);
  }
}

function syncRuntimeScaledLightingAndShadow(THREE, runtime, lightingSettings = {}, radius, bounds, sceneScaleMode = VIEWER_SCENE_SCALE.CAD) {
  syncRuntimeScaledLighting(runtime, lightingSettings, radius, sceneScaleMode);
  if (THREE && bounds && runtime?.keyLight?.shadow?.camera) {
    applyRuntimeModelBounds(THREE, runtime, bounds, sceneScaleMode);
  }
}

function updateStageEffects(runtime, viewerTheme, themeSettings, radius, floorZ = 0, floorMode = THEME_FLOOR_MODES.STAGE, sceneScaleMode = VIEWER_SCENE_SCALE.CAD) {
  if (!runtime?.THREE || !runtime?.stageGroup) {
    return;
  }

  clearSceneGroup(runtime.stageGroup);

  if (floorMode !== THEME_FLOOR_MODES.STAGE) {
    return;
  }

  const stageScaleMode = sceneScaleMode;
  const floorSize = getStageFloorSize(radius, stageScaleMode);
  const lightingScopeRadius = getStageEffectRadius(radius, stageScaleMode);
  runtime.stageGroup.add(createStageFloorPlane(runtime.THREE, viewerTheme, themeSettings, floorSize, floorZ, 0));
  const glowPlane = createStageFloorGlowPlane(
    runtime.THREE,
    themeSettings,
    lightingScopeRadius,
    floorSize,
    floorZ,
    stageScaleMode
  );
  if (glowPlane) {
    runtime.stageGroup.add(glowPlane);
  }
  const shadowPlane = createStageShadowPlane(runtime.THREE, themeSettings, floorSize, floorZ);
  if (shadowPlane) {
    runtime.stageGroup.add(shadowPlane);
  }
}

function getViewportFrameMetrics(runtime, frameInsets = {}) {
  const canvas = runtime?.renderer?.domElement;
  const width = Math.max(1, canvas?.clientWidth || canvas?.parentElement?.clientWidth || 1);
  const height = Math.max(1, canvas?.clientHeight || canvas?.parentElement?.clientHeight || 1);
  const normalizedInsets = normalizeViewportFrameInsets(frameInsets);
  const left = clamp(normalizedInsets.left, 0, Math.max(width - 1, 0));
  const right = clamp(normalizedInsets.right, 0, Math.max(width - left - 1, 0));
  const top = clamp(normalizedInsets.top, 0, Math.max(height - 1, 0));
  const bottom = clamp(normalizedInsets.bottom, 0, Math.max(height - top - 1, 0));
  const framedWidth = Math.max(1, width - left - right);
  const framedHeight = Math.max(1, height - top - bottom);
  const centerX = left + framedWidth / 2;
  const centerY = top + framedHeight / 2;

  return {
    width,
    height,
    top,
    right,
    bottom,
    left,
    framedWidth,
    framedHeight,
    aspect: framedWidth / framedHeight,
    offsetNdcX: (centerX / width) * 2 - 1,
    offsetNdcY: 1 - (centerY / height) * 2
  };
}

function getViewportFrameCrop(runtime, frameInsets = {}) {
  const canvas = runtime?.renderer?.domElement;
  const metrics = getViewportFrameMetrics(runtime, frameInsets);
  const pixelWidth = Math.max(1, canvas?.width || metrics.width);
  const pixelHeight = Math.max(1, canvas?.height || metrics.height);
  const scaleX = pixelWidth / Math.max(metrics.width, 1);
  const scaleY = pixelHeight / Math.max(metrics.height, 1);
  const x = Math.round(metrics.left * scaleX);
  const y = Math.round(metrics.top * scaleY);
  const right = Math.round(metrics.right * scaleX);
  const bottom = Math.round(metrics.bottom * scaleY);

  return {
    x,
    y,
    width: Math.max(1, pixelWidth - x - right),
    height: Math.max(1, pixelHeight - y - bottom)
  };
}

function applyCameraFrameInsets(runtime, frameInsets = {}, { updateProjection = true } = {}) {
  const camera = runtime?.camera;
  if (!camera?.projectionMatrix?.elements) {
    return;
  }
  const metrics = getViewportFrameMetrics(runtime, frameInsets);
  const offsetX = (metrics.right - metrics.left) / 2;
  const offsetY = (metrics.bottom - metrics.top) / 2;
  if ((Math.abs(offsetX) > 1e-6 || Math.abs(offsetY) > 1e-6) && typeof camera.setViewOffset === "function") {
    camera.setViewOffset(metrics.width, metrics.height, offsetX, offsetY, metrics.width, metrics.height);
  } else if (typeof camera.clearViewOffset === "function") {
    camera.clearViewOffset();
  } else if (updateProjection) {
    camera.updateProjectionMatrix();
  }
  if (camera.projectionMatrixInverse?.copy) {
    camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert();
  }
}

function reapplyRuntimeCameraFrameInsets(runtime, { updateProjection = false } = {}) {
  if (typeof runtime?.applyCameraFrameInsets !== "function") {
    return;
  }
  runtime.applyCameraFrameInsets(runtime, runtime.frameInsetsRef?.current, { updateProjection });
}

function getFitDistanceForBoundingSphere(camera, radius, sceneScaleMode, frameAspect = camera.aspect) {
  const safeRadius = Math.max(radius * AUTO_ZOOM_PADDING, getSceneScaleSettings(sceneScaleMode).minModelRadius);
  const verticalHalfFov = (camera.fov * Math.PI) / 360;
  const horizontalHalfFov = Math.atan(Math.tan(verticalHalfFov) * Math.max(frameAspect, 1e-3));
  const limitingHalfFov = Math.max(Math.min(verticalHalfFov, horizontalHalfFov), 1e-3);
  return safeRadius / Math.sin(limitingHalfFov);
}

function runtimeCameraProjection(runtime) {
  return normalizeCameraProjection(
    runtime?.projection || (runtime?.camera?.isOrthographicCamera ? CAMERA_PROJECTION.ORTHOGRAPHIC : CAMERA_PROJECTION.PERSPECTIVE)
  );
}

function syncRuntimeCameraClipPlanes(runtime, near, far) {
  for (const camera of [runtime?.perspectiveCamera, runtime?.orthographicCamera].filter(Boolean)) {
    camera.near = near;
    camera.far = far;
    camera.updateProjectionMatrix?.();
  }
}

function getOrthographicHalfHeightForBoundingSphere(radius, sceneScaleMode, frameMetrics = {}, padding = AUTO_ZOOM_PADDING) {
  const safeRadius = Math.max(radius * padding, getSceneScaleSettings(sceneScaleMode).minModelRadius);
  const frameAspect = Math.max(Number(frameMetrics.aspect) || 1, 1e-3);
  const viewportHeight = Math.max(Number(frameMetrics.height) || 1, 1);
  const framedHeight = Math.max(Number(frameMetrics.framedHeight) || viewportHeight, 1);
  return (safeRadius / Math.min(frameAspect, 1)) * (viewportHeight / framedHeight);
}

function setOrthographicCameraHalfHeight(runtime, halfHeight, frameMetrics = null) {
  const camera = runtime?.orthographicCamera;
  if (!camera?.isOrthographicCamera) {
    return false;
  }
  const metrics = frameMetrics || getViewportFrameMetrics(runtime, runtime?.frameInsetsRef?.current);
  const nextHalfHeight = Math.max(Number(halfHeight) || 0, 1e-3);
  const previousHalfHeight = Number(camera.userData?.cadHalfHeight);
  const previousLeft = Number(camera.left);
  const previousRight = Number(camera.right);
  const previousTop = Number(camera.top);
  const previousBottom = Number(camera.bottom);
  camera.userData.cadHalfHeight = nextHalfHeight;
  runtime.syncCameraViewport?.(camera, metrics.width, metrics.height);
  return (
    Math.abs((Number.isFinite(previousHalfHeight) ? previousHalfHeight : 0) - nextHalfHeight) > 1e-6 ||
    Math.abs((Number.isFinite(previousLeft) ? previousLeft : 0) - Number(camera.left)) > 1e-6 ||
    Math.abs((Number.isFinite(previousRight) ? previousRight : 0) - Number(camera.right)) > 1e-6 ||
    Math.abs((Number.isFinite(previousTop) ? previousTop : 0) - Number(camera.top)) > 1e-6 ||
    Math.abs((Number.isFinite(previousBottom) ? previousBottom : 0) - Number(camera.bottom)) > 1e-6
  );
}

function syncOrthographicCameraFrame(runtime, radius, sceneScaleMode, frameMetrics = null) {
  const metrics = frameMetrics || getViewportFrameMetrics(runtime, runtime?.frameInsetsRef?.current);
  return setOrthographicCameraHalfHeight(
    runtime,
    getOrthographicHalfHeightForBoundingSphere(radius, sceneScaleMode, metrics),
    metrics
  );
}

function frameRuntimeCameraForBoundingSphere(runtime, radius, sceneScaleMode, frameMetrics) {
  const activeCamera = runtime?.camera;
  const fitCamera = activeCamera?.isPerspectiveCamera
    ? activeCamera
    : runtime?.perspectiveCamera || activeCamera;
  const fitDistance = getFitDistanceForBoundingSphere(fitCamera, radius, sceneScaleMode, frameMetrics.aspect);
  if (activeCamera?.isOrthographicCamera) {
    syncOrthographicCameraFrame(runtime, radius, sceneScaleMode, frameMetrics);
  } else {
    activeCamera?.updateProjectionMatrix?.();
  }
  applyCameraFrameInsets(runtime, runtime?.frameInsetsRef?.current, { updateProjection: false });
  return fitDistance;
}

function runtimeViewportFitScale(runtime, frameMetrics) {
  const camera = runtime?.camera;
  const fitCamera = camera?.isPerspectiveCamera ? camera : runtime?.perspectiveCamera || camera;
  return viewportFitScale({
    orthographic: camera?.isOrthographicCamera === true,
    fov: Number(fitCamera?.fov) || 48,
    aspect: frameMetrics?.aspect,
    height: frameMetrics?.height,
    framedHeight: frameMetrics?.framedHeight
  });
}

// Record the viewport the camera is currently framed for. Anything that fits the
// camera afresh is by definition fitted to the viewport it ran in, so this is the
// reference the next viewport change measures against.
function captureRuntimeViewportFitScale(runtime, frameMetrics = null) {
  if (!runtime?.camera) {
    return;
  }
  const metrics = frameMetrics || getViewportFrameMetrics(runtime, runtime.frameInsetsRef?.current);
  runtime.viewportFitScale = runtimeViewportFitScale(runtime, metrics);
}

// Only the active projection's baseline moves. An orthographic reframe changes
// the half-height and leaves the camera position -- and with it the perspective
// baseline -- untouched, and a perspective reframe is the mirror of that.
function scaleRuntimeZoomBaseline(runtime, ratio) {
  if (!runtime || !Number.isFinite(ratio) || ratio <= 0) {
    return;
  }
  const baselineKey = runtime.camera?.isOrthographicCamera ? "zoomBaseHalfHeight" : "zoomBaseDistance";
  const baseline = Number(runtime[baselineKey]);
  if (Number.isFinite(baseline) && baseline > 1e-6) {
    runtime[baselineKey] = baseline * ratio;
  }
}

// A viewport change -- the window resizing, a side sheet opening, closing or
// being dragged wider -- leaves the camera framed for the viewport it no longer
// has. The vertical field of view is fixed and the orthographic half-height is
// held constant across an aspect change, so a narrowing viewport crops a wide
// model instead of shrinking it. Rescale the camera by the change in fit scale so
// the model keeps its share of the framed area.
//
// The zoom baseline rides along by the same ratio. Without that, the percent
// readout keeps describing the old viewport: it still says 100% while the framing
// no longer fits, and the next reset re-fits for real and visibly moves the camera
// with the readout unchanged at 100%.
function syncRuntimeViewportFraming(runtime, frameMetrics = null) {
  if (!runtime?.camera) {
    return false;
  }
  const metrics = frameMetrics || getViewportFrameMetrics(runtime, runtime.frameInsetsRef?.current);
  const previousFitScale = Number(runtime.viewportFitScale);
  const nextFitScale = runtimeViewportFitScale(runtime, metrics);
  // Claim the new viewport up front, including on the paths that bail below: the
  // first call has no reference yet, and the rest only bail when the camera is in
  // no state to be reframed. Carrying a stale reference forward would just save
  // the move up for whichever later resize does find a usable camera.
  runtime.viewportFitScale = nextFitScale;
  if (
    !Number.isFinite(previousFitScale) || previousFitScale <= 1e-6 ||
    !Number.isFinite(nextFitScale) || nextFitScale <= 1e-6
  ) {
    return false;
  }
  const requestedRatio = nextFitScale / previousFitScale;
  if (Math.abs(requestedRatio - 1) < 1e-6) {
    return false;
  }
  const camera = runtime.camera;
  let appliedRatio = requestedRatio;
  if (camera.isOrthographicCamera) {
    const halfHeight = readOrthographicHalfHeight(runtime);
    if (!halfHeight) {
      return false;
    }
    const nextHalfHeight = Math.max(halfHeight * requestedRatio, 1e-3);
    appliedRatio = nextHalfHeight / halfHeight;
    setOrthographicCameraHalfHeight(runtime, nextHalfHeight, metrics);
  } else {
    const target = runtime.controls?.target;
    const distance = readCameraTargetDistance(runtime);
    if (!target || !distance) {
      return false;
    }
    const minDistance = Number.isFinite(Number(runtime.controls?.minDistance))
      ? Number(runtime.controls.minDistance)
      : 0.01;
    const maxDistance = Number.isFinite(Number(runtime.controls?.maxDistance)) && Number(runtime.controls.maxDistance) > 0
      ? Number(runtime.controls.maxDistance)
      : Number.POSITIVE_INFINITY;
    const nextDistance = clamp(distance * requestedRatio, minDistance, maxDistance);
    appliedRatio = nextDistance / distance;
    if (Math.abs(appliedRatio - 1) < 1e-6) {
      return false;
    }
    // Scaling the target->camera offset moves the camera along the view ray, so
    // the orientation and the pivot are untouched -- only the distance changes.
    camera.position.copy(target.clone().add(camera.position.clone().sub(target).multiplyScalar(appliedRatio)));
    camera.lookAt(target);
  }
  scaleRuntimeZoomBaseline(runtime, appliedRatio);
  reapplyRuntimeCameraFrameInsets(runtime);
  // Bare controls.update() ticks OrbitControls' auto-rotate branch, so a resize
  // during a preview orbit would nudge the camera an extra step.
  if (runtime.controls) {
    const autoRotateBeforeResize = runtime.controls.autoRotate;
    runtime.controls.autoRotate = false;
    runtime.controls.update?.();
    runtime.controls.autoRotate = autoRotateBeforeResize;
  }
  runtime.requestRender?.();
  return true;
}

function syncRuntimeCameraProjection(runtime, projection, { scheduleIdle = true, requestRender = true } = {}) {
  if (!runtime?.camera || !runtime?.controls) {
    return false;
  }
  const nextProjection = normalizeCameraProjection(projection);
  const nextCamera = nextProjection === CAMERA_PROJECTION.ORTHOGRAPHIC
    ? runtime.orthographicCamera
    : runtime.perspectiveCamera;
  if (!nextCamera) {
    return false;
  }
  const previousCamera = runtime.camera;
  const previousPerspectiveHalfHeight = previousCamera?.isPerspectiveCamera && runtime.controls?.target
    ? (
        previousCamera.position.distanceTo(runtime.controls.target) *
        Math.tan((Math.max(Number(previousCamera.fov) || 48, 1e-3) * Math.PI) / 360) /
        Math.max(Number(previousCamera.zoom) || 1, 1e-3)
      )
    : null;
  if (previousCamera !== nextCamera) {
    nextCamera.position.copy(previousCamera.position);
    nextCamera.up.copy(previousCamera.up);
    nextCamera.near = previousCamera.near;
    nextCamera.far = previousCamera.far;
    nextCamera.zoom = Number.isFinite(previousCamera.zoom) && previousCamera.zoom > 0 ? previousCamera.zoom : 1;
    runtime.camera = nextCamera;
    runtime.controls.object = nextCamera;
  }
  runtime.projection = nextProjection;
  const frameMetrics = getViewportFrameMetrics(runtime, runtime.frameInsetsRef?.current);
  if (nextCamera.isOrthographicCamera && previousCamera !== nextCamera) {
    const previousOrthographicHalfHeight = Number(previousCamera?.userData?.cadHalfHeight);
    const preservedHalfHeight = Number.isFinite(previousPerspectiveHalfHeight) && previousPerspectiveHalfHeight > 0
      ? previousPerspectiveHalfHeight
      : previousOrthographicHalfHeight;
    if (Number.isFinite(preservedHalfHeight) && preservedHalfHeight > 0) {
      setOrthographicCameraHalfHeight(runtime, preservedHalfHeight, frameMetrics);
    } else {
      runtime.syncCameraViewport?.(nextCamera, frameMetrics.width, frameMetrics.height);
    }
  } else {
    runtime.syncCameraViewport?.(nextCamera, frameMetrics.width, frameMetrics.height);
  }
  applyCameraFrameInsets(runtime, runtime.frameInsetsRef?.current, { updateProjection: false });
  // The switch preserves the framing rather than re-fitting, but perspective and
  // orthographic measure the viewport differently, so the reference a later
  // resize compares against has to be re-read in the new projection's terms.
  captureRuntimeViewportFitScale(runtime, frameMetrics);
  // Recompute camera matrices without advancing auto-rotate. A bare controls.update()
  // ticks OrbitControls' frame-rate-dependent auto-rotation branch, so any projection
  // sync that fires during a preview orbit would nudge the camera forward an extra step.
  const autoRotateBeforeProjectionSync = runtime.controls.autoRotate;
  runtime.controls.autoRotate = false;
  runtime.controls.update?.();
  runtime.controls.autoRotate = autoRotateBeforeProjectionSync;
  if (scheduleIdle) {
    runtime.scheduleIdleQuality?.();
  }
  if (requestRender) {
    runtime.requestRender?.();
  }
  return true;
}

function easeInOutSine(t) {
  if (t <= 0) {
    return 0;
  }
  if (t >= 1) {
    return 1;
  }
  return -(Math.cos(Math.PI * t) - 1) / 2;
}

function easeCameraTransitionProgress(t, easing = CAMERA_TRANSITION_EASING.EASE_IN_OUT_CUBIC) {
  return easing === CAMERA_TRANSITION_EASING.EASE_IN_OUT_SINE
    ? easeInOutSine(t)
    : easeInOutCubic(t);
}

function readPerspectiveSnapshot(runtime) {
  if (!runtime?.camera || !runtime?.controls) {
    return null;
  }
  return {
    position: [runtime.camera.position.x, runtime.camera.position.y, runtime.camera.position.z],
    target: [runtime.controls.target.x, runtime.controls.target.y, runtime.controls.target.z],
    up: [runtime.camera.up.x, runtime.camera.up.y, runtime.camera.up.z],
    zoom: runtime.camera.zoom,
    projection: runtimeCameraProjection(runtime)
  };
}

function readScopedPerspectiveSnapshot(runtime, { modelKey = "", sceneScaleMode = "" } = {}) {
  return annotatePerspectiveSnapshot(readPerspectiveSnapshot(runtime), {
    modelKey,
    sceneScaleMode,
    coordinateSystem: coordinateSystemForSceneScale(sceneScaleMode)
  });
}

function coordinateSystemForSceneScale(sceneScaleMode) {
  return normalizeSceneScaleMode(sceneScaleMode) === VIEWER_SCENE_SCALE.URDF
    ? ROBOT_COORDINATE_SYSTEM
    : CAD_COORDINATE_SYSTEM;
}

function cancelCameraTransition(runtime, { scheduleIdle = true } = {}) {
  if (!runtime?.cameraTransition) {
    return;
  }
  runtime.cameraTransition = null;
  if (runtime.controls) {
    runtime.controls.enableDamping = true;
    runtime.controls.dampingFactor = DEFAULT_DAMPING_FACTOR;
  }
  if (scheduleIdle) {
    runtime.scheduleIdleQuality?.();
  }
}

function applyPerspectiveSnapshot(runtime, perspective, { scheduleIdle = true } = {}) {
  const nextPerspective = clonePerspectiveSnapshot(perspective);
  if (!runtime?.camera || !runtime?.controls || !nextPerspective) {
    return false;
  }
  cancelCameraTransition(runtime, { scheduleIdle: false });
  clearKeyboardOrbitState(runtime.keyboardOrbitState);
  if (Object.prototype.hasOwnProperty.call(nextPerspective, "projection")) {
    syncRuntimeCameraProjection(runtime, nextPerspective.projection, { scheduleIdle: false });
  }
  runtime.camera.position.set(...nextPerspective.position);
  runtime.controls.target.set(...nextPerspective.target);
  runtime.camera.up.set(...nextPerspective.up);
  if (Number.isFinite(nextPerspective.zoom) && nextPerspective.zoom > 0) {
    runtime.camera.zoom = nextPerspective.zoom;
    runtime.camera.updateProjectionMatrix?.();
    reapplyRuntimeCameraFrameInsets(runtime);
  }
  runtime.camera.lookAt(runtime.controls.target);
  runtime.controls.update();
  if (scheduleIdle) {
    runtime.scheduleIdleQuality?.();
  }
  runtime.requestRender?.();
  return true;
}

function transitionCameraToPerspectiveSnapshot(runtime, perspective, {
  durationMs = VIEW_PLANE_TRANSITION_MS,
  easing = CAMERA_TRANSITION_EASING.EASE_IN_OUT_CUBIC,
  orthographicHalfHeight = null,
  resetZoomBaselineOnComplete = false
} = {}) {
  const nextPerspective = clonePerspectiveSnapshot(perspective);
  if (!runtime?.THREE || !runtime?.camera || !runtime?.controls || !nextPerspective) {
    return false;
  }
  cancelCameraTransition(runtime, { scheduleIdle: false });
  clearKeyboardOrbitState(runtime.keyboardOrbitState);
  if (Object.prototype.hasOwnProperty.call(nextPerspective, "projection")) {
    syncRuntimeCameraProjection(runtime, nextPerspective.projection, { scheduleIdle: false });
  }
  const endPosition = new runtime.THREE.Vector3(...nextPerspective.position);
  const endTarget = new runtime.THREE.Vector3(...nextPerspective.target);
  const endUp = new runtime.THREE.Vector3(...nextPerspective.up);
  const endZoom = Number.isFinite(nextPerspective.zoom) && nextPerspective.zoom > 0
    ? nextPerspective.zoom
    : runtime.camera.zoom;
  const startOrthographicHalfHeight = runtime.camera?.isOrthographicCamera
    ? Number(runtime.camera.userData?.cadHalfHeight)
    : null;
  const endOrthographicHalfHeight = runtime.camera?.isOrthographicCamera
    ? Number(orthographicHalfHeight)
    : null;
  if (
    ![endPosition.x, endPosition.y, endPosition.z, endTarget.x, endTarget.y, endTarget.z, endUp.x, endUp.y, endUp.z, endZoom]
      .every(Number.isFinite) ||
    endUp.lengthSq() <= 1e-6
  ) {
    return false;
  }
  runtime.cameraTransition = {
    startTime: performance.now(),
    durationMs,
    startPosition: runtime.camera.position.clone(),
    endPosition,
    startTarget: runtime.controls.target.clone(),
    endTarget,
    startUp: runtime.camera.up.clone(),
    endUp: endUp.normalize(),
    startZoom: runtime.camera.zoom,
    endZoom,
    startOrthographicHalfHeight,
    endOrthographicHalfHeight,
    resetZoomBaselineOnComplete,
    easing
  };
  runtime.controls.enableDamping = false;
  runtime.beginInteraction?.();
  runtime.requestRender?.();
  return true;
}

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

// Aim the controls back at the model centre without touching orientation or
// distance. The model group is positioned at -center, so the model's centre in
// world space is the origin — the same target the initial framing uses.
function recenterRuntimeTarget(runtime) {
  const controls = runtime?.controls;
  const camera = runtime?.camera;
  if (!controls?.target || !camera || !runtime?.THREE) {
    return false;
  }
  const offset = new runtime.THREE.Vector3().copy(camera.position).sub(controls.target);
  controls.target.set(0, 0, 0);
  camera.position.copy(offset);
  camera.lookAt(controls.target);
  controls.update?.();
  return true;
}

// What "reset" and "fit" frame: the model in its current parameter pose, which
// is the same thing the loader framed. Framing runtime.modelBounds instead would
// crop a model a sidecar has posed larger than its at-rest box, because that
// field tracks whichever bounds were applied last rather than the live pose.
function runtimeFramingBounds(runtime, fallbackBounds = null) {
  if (!runtime?.THREE?.Matrix4 || !Array.isArray(runtime.displayRecords) || !runtime.displayRecords.length) {
    return runtime?.modelBounds || fallbackBounds;
  }
  return effectiveBoundsFromRecords(
    runtime.THREE,
    runtime.displayRecords,
    runtime.modelBounds || fallbackBounds
  );
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

function zoomRuntimeToBounds(runtime, bounds, sceneScaleMode, {
  animate = true,
  modelOffset = null,
  resetZoomBaseline = false
} = {}) {
  if (!runtime?.THREE || !runtime?.camera || !runtime?.controls) {
    return false;
  }
  const normalizedBounds = mergeBoundsList([bounds]);
  if (!normalizedBounds) {
    return false;
  }
  const frameMetrics = getViewportFrameMetrics(runtime, runtime.frameInsetsRef?.current);
  const frame = autoZoomFrameForBounds(runtime.THREE, {
    camera: runtime.camera,
    controls: runtime.controls,
    bounds: normalizedBounds,
    modelOffset,
    frameAspect: frameMetrics.aspect,
    minRadius: getSceneScaleSettings(sceneScaleMode).minModelRadius,
    padding: DEFAULT_AUTO_ZOOM_PADDING,
    defaultDirection: DEFAULT_VIEW_DIRECTION,
    viewUp: runtime.camera.up?.toArray?.() || WORLD_UP
  });
  if (!frame) {
    return false;
  }
  if (resetZoomBaseline) {
    runtime.zoomFitModelRadius = boundsModelRadius(runtime.THREE, normalizedBounds, sceneScaleMode);
  }
  const snapshot = {
    position: frame.position.toArray(),
    target: frame.target.toArray(),
    up: frame.up.toArray(),
    zoom: 1,
    projection: runtimeCameraProjection(runtime)
  };
  const orthographicHalfHeight = runtime.camera.isOrthographicCamera
    ? getOrthographicHalfHeightForBoundingSphere(
        frame.radius,
        sceneScaleMode,
        frameMetrics,
        DEFAULT_AUTO_ZOOM_PADDING
      )
    : null;

  if (animate) {
    return transitionCameraToPerspectiveSnapshot(runtime, snapshot, {
      durationMs: VIEW_PLANE_TRANSITION_MS,
      easing: CAMERA_TRANSITION_EASING.EASE_IN_OUT_CUBIC,
      orthographicHalfHeight,
      resetZoomBaselineOnComplete: resetZoomBaseline
    });
  }

  if (runtime.camera.isOrthographicCamera && orthographicHalfHeight) {
    setOrthographicCameraHalfHeight(runtime, orthographicHalfHeight, frameMetrics);
  }
  const applied = applyPerspectiveSnapshot(runtime, snapshot);
  if (applied) {
    if (resetZoomBaseline) {
      resetRuntimeZoomBaseline(runtime);
    }
    runtime.onZoomChange?.(runtime);
  }
  return applied;
}

function stepCameraTransition(runtime, timestamp) {
  const transition = runtime?.cameraTransition;
  if (!transition || !runtime?.THREE || !runtime?.camera || !runtime?.controls) {
    return false;
  }

  const durationMs = Math.max(transition.durationMs, 1);
  const progress = clamp((timestamp - transition.startTime) / durationMs, 0, 1);
  const eased = easeCameraTransitionProgress(progress, transition.easing);
  const position = new runtime.THREE.Vector3().lerpVectors(
    transition.startPosition,
    transition.endPosition,
    eased
  );
  const target = new runtime.THREE.Vector3().lerpVectors(
    transition.startTarget,
    transition.endTarget,
    eased
  );
  const up = new runtime.THREE.Vector3().lerpVectors(
    transition.startUp,
    transition.endUp,
    eased
  );
  runtime.camera.position.copy(position);
  runtime.controls.target.copy(target);
  if (up.lengthSq() > 1e-6) {
    runtime.camera.up.copy(up.normalize());
  }
  const startOrthographicHalfHeight = Number(transition.startOrthographicHalfHeight);
  const endOrthographicHalfHeight = Number(transition.endOrthographicHalfHeight);
  let projectionUpdated = false;
  if (
    runtime.camera?.isOrthographicCamera &&
    Number.isFinite(startOrthographicHalfHeight) &&
    Number.isFinite(endOrthographicHalfHeight) &&
    endOrthographicHalfHeight > 0
  ) {
    const nextHalfHeight = startOrthographicHalfHeight + ((endOrthographicHalfHeight - startOrthographicHalfHeight) * eased);
    setOrthographicCameraHalfHeight(runtime, nextHalfHeight);
    reapplyRuntimeCameraFrameInsets(runtime);
    projectionUpdated = true;
  }
  if (Number.isFinite(transition.startZoom) && Number.isFinite(transition.endZoom)) {
    runtime.camera.zoom = transition.startZoom + ((transition.endZoom - transition.startZoom) * eased);
    runtime.camera.updateProjectionMatrix?.();
    if (!projectionUpdated) {
      reapplyRuntimeCameraFrameInsets(runtime);
    }
  }
  runtime.camera.lookAt(target);

  if (progress >= 1) {
    if (transition.resetZoomBaselineOnComplete) {
      resetRuntimeZoomBaseline(runtime);
    }
    runtime.onZoomChange?.(runtime);
    runtime.cameraTransition = null;
    runtime.controls.enableDamping = true;
    runtime.controls.dampingFactor = DEFAULT_DAMPING_FACTOR;
    runtime.scheduleIdleQuality?.();
    return false;
  }
  return true;
}

function transitionCameraToViewPreset(runtime, preset) {
  if (
    !runtime?.THREE ||
    !runtime?.camera ||
    !runtime?.controls ||
    !preset ||
    !Array.isArray(preset.direction) ||
    preset.direction.length !== 3 ||
    !Array.isArray(preset.up) ||
    preset.up.length !== 3
  ) {
    return false;
  }

  const currentTarget = runtime.controls.target.clone();
  const currentOffset = new runtime.THREE.Vector3().copy(runtime.camera.position).sub(currentTarget);
  const fallbackDistance = Math.max(runtime.controls.minDistance || 1, 1);
  const currentDistance = currentOffset.length();
  const distance = clamp(
    Number.isFinite(currentDistance) && currentDistance > 1e-6 ? currentDistance : fallbackDistance,
    runtime.controls.minDistance || 0.01,
    runtime.controls.maxDistance || Infinity
  );
  const nextDirection = new runtime.THREE.Vector3(...preset.direction);
  if (nextDirection.lengthSq() < 1e-6) {
    return false;
  }
  const nextUp = new runtime.THREE.Vector3(...preset.up);
  if (nextUp.lengthSq() < 1e-6) {
    return false;
  }

  nextDirection.normalize();
  nextUp.normalize();
  const worldUp = new runtime.THREE.Vector3(...WORLD_UP).normalize();
  if (Math.abs(nextDirection.dot(worldUp)) >= VIEW_PLANE_POLE_DIRECTION_DOT_THRESHOLD) {
    let screenUp = nextUp.clone().addScaledVector(worldUp, -nextUp.dot(worldUp));
    if (screenUp.lengthSq() < 1e-6) {
      screenUp = new runtime.THREE.Vector3(0, 1, 0).addScaledVector(worldUp, -worldUp.y);
    }
    if (screenUp.lengthSq() < 1e-6) {
      screenUp = new runtime.THREE.Vector3(1, 0, 0);
    }
    screenUp.normalize();
    const poleSign = nextDirection.dot(worldUp) >= 0 ? 1 : -1;
    nextDirection.addScaledVector(screenUp, -poleSign * VIEW_PLANE_POLE_DIRECTION_NUDGE).normalize();
    nextUp.copy(worldUp);
  }
  runtime.cameraTransition = {
    startTime: performance.now(),
    durationMs: VIEW_PLANE_TRANSITION_MS,
    startPosition: runtime.camera.position.clone(),
    endPosition: currentTarget.clone().add(nextDirection.multiplyScalar(distance)),
    startTarget: currentTarget.clone(),
    endTarget: currentTarget.clone(),
    startUp: runtime.camera.up.clone(),
    endUp: nextUp
  };
  runtime.controls.enableDamping = false;
  runtime.beginInteraction?.();
  runtime.requestRender?.();
  return true;
}

function disposeSceneObject(object) {
  if (!object) {
    return;
  }
  while (object.children?.length) {
    disposeSceneObject(object.children[0]);
  }
  if (typeof object.userData?.beforeDispose === "function") {
    object.userData.beforeDispose(object);
    delete object.userData.beforeDispose;
  }
  object.parent?.remove(object);
  if (object.geometry?.userData?.cadSceneCachedGeometry !== true) {
    object.geometry?.dispose?.();
  }
  const materials = Array.isArray(object.material) ? object.material : [object.material];
  for (const material of materials) {
    material?.map?.dispose?.();
    material?.alphaMap?.dispose?.();
    material?.dispose?.();
  }
}

function clearSceneGroup(group) {
  while (group.children.length) {
    disposeSceneObject(group.children[0]);
  }
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

function isPointerInsideElement(event, element) {
  if (!event || !element || !Number.isFinite(Number(event.clientX)) || !Number.isFinite(Number(event.clientY))) {
    return false;
  }
  const rect = element.getBoundingClientRect();
  return (
    event.clientX >= rect.left &&
    event.clientX <= rect.right &&
    event.clientY >= rect.top &&
    event.clientY <= rect.bottom
  );
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
  if (group === runtime?.urdfPosePickerGuideGroup) {
    runtime.urdfPosePickerHoverCellMesh = null;
    runtime.urdfPosePickerHoverCellOutline = null;
  }
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

function parseFaceToken(copyText) {
  return String(parseCadRefToken(copyText)?.token || "").trim();
}

function mateOverlayVector(value) {
  if (!Array.isArray(value) || value.length < 3) {
    return null;
  }
  const vector = value.slice(0, 3).map((component) => Number(component));
  return vector.every((component) => Number.isFinite(component)) ? vector : null;
}

function normalizedMateOverlayEndpoint(endpoint) {
  if (!endpoint || typeof endpoint !== "object") {
    return null;
  }
  const position = mateOverlayVector(endpoint.position);
  if (!position) {
    return null;
  }
  const axes = endpoint.axes && typeof endpoint.axes === "object" ? endpoint.axes : {};
  return {
    position,
    axes: {
      x: mateOverlayVector(axes.x),
      y: mateOverlayVector(axes.y),
      z: mateOverlayVector(axes.z)
    }
  };
}

function normalizeMateIdList(value) {
  return [...new Set(
    (Array.isArray(value) ? value : [value])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  )];
}

function resolveActiveMateOverlays(assemblyMates, selectedMateIds, hoveredMateId) {
  const selectedSet = new Set(normalizeMateIdList(selectedMateIds));
  const hoveredId = String(hoveredMateId || "").trim();
  if (!selectedSet.size && !hoveredId) {
    return [];
  }
  const active = [];
  const seen = new Set();
  for (const mate of Array.isArray(assemblyMates) ? assemblyMates : []) {
    const mateId = String(mate?.id || "").trim();
    if (!mateId || seen.has(mateId)) {
      continue;
    }
    const selected = selectedSet.has(mateId);
    const hovered = hoveredId === mateId;
    if (!selected && !hovered) {
      continue;
    }
    const fixed = normalizedMateOverlayEndpoint(mate.fixedEndpoint);
    const moving = normalizedMateOverlayEndpoint(mate.movingEndpoint);
    if (!fixed && !moving) {
      continue;
    }
    seen.add(mateId);
    active.push({
      id: mateId,
      fixed,
      moving,
      selected,
      hovered
    });
  }
  return active;
}

function createMateMarkerMesh(THREE, position, {
  color,
  opacity,
  radius,
  renderOrder
}) {
  const markerGeometry = new THREE.SphereGeometry(radius, 18, 10);
  const markerMaterial = new THREE.MeshBasicMaterial({
    color,
    transparent: opacity < 0.999,
    opacity,
    depthTest: false,
    depthWrite: false,
    toneMapped: false
  });
  const marker = new THREE.Mesh(markerGeometry, markerMaterial);
  marker.position.set(position[0], position[1], position[2]);
  marker.renderOrder = renderOrder;
  return marker;
}

function pushMateAxisSegment(segments, origin, direction, length) {
  const axis = mateOverlayVector(direction);
  if (!axis) {
    return;
  }
  const magnitude = Math.hypot(axis[0], axis[1], axis[2]);
  if (magnitude <= 1e-8) {
    return;
  }
  const unit = axis.map((component) => component / magnitude);
  segments.push(
    origin[0] - unit[0] * length,
    origin[1] - unit[1] * length,
    origin[2] - unit[2] * length,
    origin[0] + unit[0] * length,
    origin[1] + unit[1] * length,
    origin[2] + unit[2] * length
  );
}

function addMateOverlayGlyph(runtime, group, mate, {
  color,
  opacity,
  markerRadius,
  axisLength,
  lineWidth,
  renderOrder
}) {
  const fixedPosition = mate.fixed?.position || null;
  const movingPosition = mate.moving?.position || null;
  const anchorPosition = fixedPosition || movingPosition;
  if (!anchorPosition) {
    return;
  }

  const positions = [];
  if (fixedPosition && movingPosition) {
    const span = Math.hypot(
      fixedPosition[0] - movingPosition[0],
      fixedPosition[1] - movingPosition[1],
      fixedPosition[2] - movingPosition[2]
    );
    if (span > Math.max(markerRadius * 0.25, 0.01)) {
      positions.push(...fixedPosition, ...movingPosition);
    }
  }
  const axes = mate.fixed?.axes || mate.moving?.axes || {};
  pushMateAxisSegment(positions, anchorPosition, axes.z || [0, 0, 1], axisLength);
  pushMateAxisSegment(positions, anchorPosition, axes.x || [1, 0, 0], axisLength * 0.62);
  if (positions.length) {
    const line = createScreenSpaceLineSegments(runtime, positions, {
      color,
      opacity,
      lineWidth,
      renderOrder,
      depthTest: false,
      depthWrite: false
    });
    if (line) {
      group.add(line);
    }
  }

  group.add(createMateMarkerMesh(runtime.THREE, anchorPosition, {
    color,
    opacity,
    radius: markerRadius,
    renderOrder: renderOrder + 1
  }));
}

function updateGridHelper(
  runtime,
  viewerTheme,
  radius,
  floorZ = 0,
  sceneScaleMode = VIEWER_SCENE_SCALE.CAD,
  floorMode = THEME_FLOOR_MODES.STAGE,
  floorSettings = {}
) {
  updateStageOriginAxis(runtime, viewerTheme, radius, floorZ, {
    disposeSceneObject,
    floorSettings
  });
  return updateStageGridHelper(runtime, viewerTheme, radius, floorZ, sceneScaleMode, floorMode, {
    disposeSceneObject,
    floorSettings
  });
}

const CadViewer = forwardRef(function CadViewer({
  meshData,
  modelKey,
  renderFormat = "",
  // Implicit entries have no mesh: their geometry is GLSL, raymarched into this
  // same scene by useImplicitRaymarch. Everything else about the viewport —
  // camera, controls, zoom, fit, view cube, screenshots — is shared with the
  // mesh formats, which is why implicit is a render type here rather than a
  // separate component.
  implicitModel = null,
  implicitGraphicsSettings = null,
  implicitDynamicRenderActive = false,
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
  perspective = null,
  perspectiveRef = null,
  projection = CAMERA_PROJECTION.PERSPECTIVE,
  showEdges,
  recomputeNormals,
  theme = BASE_VIEWER_THEME,
  themeSettings = null,
  floorModeOverride = "",
  previewMode = false,
  showViewPlane = true,
  viewPlaneOffsetRight = 16,
  viewPlaneOffsetBottom = 16,
  viewPlaneHeader = null,
  compactViewPlane = false,
  viewportFrameInsets = null,
  isLoading = false,
  pickMode = VIEWER_PICK_MODE.AUTO,
  panToolActive = false,
  renderPartsIndividually = false,
  scale = "",
  sceneScaleMode = VIEWER_SCENE_SCALE.CAD,
  pickableParts = [],
  hiddenPartIds = [],
  selectedPartIds = [],
  hoveredPartId = "",
  assemblyMates = [],
  selectedMateIds = [],
  hoveredMateId = "",
  hoveredReferenceId = "",
  selectedReferenceIds = [],
  selectorRuntime = null,
  displayEdgeRuntime = null,
  stepParameters = null,
  pickableFaces = [],
  pickableEdges = [],
  pickableVertices = [],
  surfaceLineFaceId = "",
  focusedPartId = "",
  displaySettings = null,
  drawingEnabled = false,
  drawingTool = DRAWING_TOOL.FREEHAND,
  drawingStrokes = [],
  onDrawingStrokesChange,
  onPerspectiveChange,
  onHoverReferenceChange,
  onActivateReference,
  onDoubleActivateReference,
  onContextReference,
  onViewerAlertChange,
  onStepModuleTransformDetectedChange,
  urdfPosePicker = null
}, ref) {
  const stepParameterRuntime = stepParameters;
  const stepAnimationPlaying = Boolean(stepParameterRuntime?.animationState?.playing);
  const implicitActive = viewportContentKind(renderFormat) === VIEWPORT_CONTENT.IMPLICIT;
  // What counts as "something is on screen" for overlays and the view cube:
  // an implicit has a model instead of mesh data.
  const viewportContent = implicitActive ? implicitModel : meshData;
  const hasViewportContent = !!viewportContent;
  const normalizedSceneScaleMode = normalizeSceneScaleMode(scale || sceneScaleMode);
  const normalizedProjection = normalizeCameraProjection(projection);
  const meshGeometrySource = meshData?.geometrySource && typeof meshData.geometrySource === "object"
    ? meshData.geometrySource
    : meshData;
  const defaultGridRadius = defaultSceneGridRadius(normalizedSceneScaleMode);
  const normalizedViewportFrameInsets = useMemo(
    () => normalizeViewportFrameInsets(viewportFrameInsets),
    [
      viewportFrameInsets?.top,
      viewportFrameInsets?.right,
      viewportFrameInsets?.bottom,
      viewportFrameInsets?.left
    ]
  );
  const interactionHostRef = useRef(null);
  const mountRef = useRef(null);
  const drawingCanvasRef = useRef(null);
  const drawingDraftRef = useRef(null);
  const drawingStrokesRef = useRef(Array.isArray(drawingStrokes) ? drawingStrokes : []);
  const drawingChangeRef = useRef(onDrawingStrokesChange);
  const perspectiveChangeRef = useRef(onPerspectiveChange);
  const viewerAlertChangeRef = useRef(onViewerAlertChange);
  const stepModuleTransformDetectedChangeRef = useRef(onStepModuleTransformDetectedChange);
  const urdfPosePickerRef = useRef(urdfPosePicker);
  // The pose picker shares the canvas cursor with the pan tool, so it may only
  // reset what it actually set. Its pointer-move handler runs for every file
  // kind, and blindly clearing on each move wiped the pan cursor after one
  // mouse movement.
  const urdfPosePickerOwnsCursorRef = useRef(false);
  const posePickerPointerRef = useRef(null);
  const lastEmittedPerspectiveRef = useRef(null);
  const lastProjectionRef = useRef(normalizedProjection);
  const suppressPerspectiveEventsRef = useRef(0);
  const drawingIdRef = useRef(0);
  const runtimeRef = useRef(null);
  const explodedViewAnimationRef = useRef({
    rafId: 0,
    progress: 0,
    modelKey: "",
    enabled: false,
    layout: null
  });
  const viewportFrameInsetsRef = useRef(normalizedViewportFrameInsets);
  const framedModelKeyRef = useRef("");
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
  const [activeViewPlaneFace, setActiveViewPlaneFace] = useState("");
  const [viewPlaneOrientation, setViewPlaneOrientation] = useState(DEFAULT_VIEW_PLANE_ORIENTATION);
  const [cameraZoomPercent, setCameraZoomPercent] = useState(100);
  const [urdfPosePickerGuidePoint, setUrdfPosePickerGuidePoint] = useState(null);
  const [urdfPosePickerHoverActive, setUrdfPosePickerHoverActive] = useState(false);
  const activeViewPlaneFaceRef = useRef("");
  const defaultPerspectiveResettingRef = useRef(false);
  const previewModeRef = useRef(previewMode);
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
  const normalizedViewerRenderState = useMemo(() => normalizeViewerRenderState({
    themeSettings,
    displaySettings
  }), [themeSettings, displaySettings]);
  const normalizedThemeSettings = normalizedViewerRenderState.themeSettings;
  const normalizedDisplaySettings = normalizedViewerRenderState.displaySettings;
  const normalizedDisplayMode = normalizedViewerRenderState.displayMode;
  const normalizedExplodedSettings = normalizedDisplaySettings.exploded;
  const explodeAmount = clamp(toNumber(normalizedExplodedSettings.amount, 1), 0, 1);
  const explodablePartCount = useMemo(() => renderableMeshParts(meshData).length, [meshData]);
  const explodedViewActive = normalizedExplodedSettings.enabled && explodablePartCount > 1;
  const effectiveRenderPartsIndividually = renderPartsIndividually ||
    explodedViewActive;
  // CAD edges come from the topology package, so this is the `topology` capability, not
  // "is this STEP". A second format that ships topology inherits the edge rendering.
  const shouldUseCadEdgeSource = hasCapability(renderFormat, "topology");
  const displayEdgeSettings = useMemo(
    () => resolveDisplayEdgeSettings(normalizedDisplaySettings),
    [normalizedDisplaySettings]
  );
  const wireframeMode = displayModeIsWireframe(normalizedDisplayMode);
  const displayModeForceEdges = displayModeForcesEdges(normalizedDisplayMode);
  const displayModeThroughEdges = displayModeShowsThroughEdges(normalizedDisplayMode);
  const wireframeEdgeColor = useMemo(
    () => resolveWireframeEdgeColor({
      edgeColor: displayEdgeSettings?.color,
      themeSettings: normalizedThemeSettings,
      viewerTheme
    }),
    [displayEdgeSettings, normalizedThemeSettings, viewerTheme]
  );
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
  const defaultFloorMode = floorSettings.enabled === true
    ? THEME_FLOOR_MODES.STAGE
    : THEME_FLOOR_MODES.NONE;
  const resolvedFloorMode = floorModeOverride
    ? normalizeFloorMode(floorModeOverride, defaultFloorMode)
    : defaultFloorMode;
  const floorFollowsModel = floorSettings.followModel !== false;
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
      normalizedThemeSettings.floor
    );
  }, [normalizedThemeSettings.floor]);
  // The implicit raymarch pass composites over the shared stage rather than
  // replacing it, so every format paints its background the same way.
  const applyActiveSceneBackground = applySceneBackground;
  const edgesVisible = showEdges && shouldUseCadEdgeSource && displayModeShowsEdges(normalizedDisplayMode, visualEdgeSettings);
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
  const activeSurfaceLineFaceId = String(surfaceLineFaceId || "").trim();
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
  const pickableFaceReferenceIds = useMemo(
    () => new Set(filteredPickableFaces.map((reference) => String(reference?.id || "").trim()).filter(Boolean)),
    [filteredPickableFaces]
  );
  const syncDrawingCanvasSize = (runtime = runtimeRef.current) => {
    const canvas = drawingCanvasRef.current;
    if (!canvas) {
      return null;
    }
    const rendererCanvas = runtime?.renderer?.domElement;
    const width = rendererCanvas?.width || mountRef.current?.clientWidth || 1;
    const height = rendererCanvas?.height || mountRef.current?.clientHeight || 1;
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    return canvas;
  };
  const renderDrawingOverlay = () => {
    const canvas = syncDrawingCanvasSize();
    if (!canvas) {
      return;
    }
    redrawDrawingCanvas(canvas, drawingStrokesRef.current, drawingDraftRef.current);
  };
  perspectivePropRef.current = perspective;
  modelKeyRef.current = modelKey;
  sceneScaleModeRef.current = normalizedSceneScaleMode;
  useLayoutEffect(() => {
    viewportFrameInsetsRef.current = normalizedViewportFrameInsets;
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }
    // Sheets and the sidebar do not resize the canvas -- they inset the framed
    // area over it -- so a sheet opening never reaches the resize path. It still
    // shrinks the space the model has to live in, and needs the same reframing.
    if (syncRuntimeViewportFraming(runtime)) {
      syncCameraZoomPercent(runtime);
      emitPerspectiveChange(runtime);
    }
    applyCameraFrameInsets(runtime, normalizedViewportFrameInsets);
    runtime.requestRender?.();
  }, [
    normalizedViewportFrameInsets.top,
    normalizedViewportFrameInsets.right,
    normalizedViewportFrameInsets.bottom,
    normalizedViewportFrameInsets.left,
    viewerReadyTick
  ]);
  // The pan tool remaps the primary drag from orbit to pan. Right-drag stays
  // pan either way, so the habitual gesture keeps working while the tool is on.
  //
  // The cursor closes to "grabbing" for the duration of a drag, which is what
  // makes the tool feel like dragging the scene rather than just hovering over
  // it. Driven by listeners instead of React state so a pan does not re-render
  // the viewer on every press.
  useEffect(() => {
    const runtime = runtimeRef.current;
    const controls = runtime?.controls;
    const MOUSE = runtime?.THREE?.MOUSE;
    const canvas = runtime?.renderer?.domElement;
    if (!controls?.mouseButtons || !MOUSE) {
      return undefined;
    }
    controls.mouseButtons.LEFT = panToolActive ? MOUSE.PAN : MOUSE.ROTATE;
    if (!canvas) {
      return undefined;
    }
    if (!panToolActive) {
      canvas.style.cursor = "";
      return () => {
        if (controls.mouseButtons) {
          controls.mouseButtons.LEFT = MOUSE.ROTATE;
        }
      };
    }

    canvas.style.cursor = "grab";
    const grab = () => { canvas.style.cursor = "grab"; };
    const grabbing = () => { canvas.style.cursor = "grabbing"; };
    canvas.addEventListener("pointerdown", grabbing);
    window.addEventListener("pointerup", grab);
    window.addEventListener("pointercancel", grab);
    return () => {
      canvas.removeEventListener("pointerdown", grabbing);
      window.removeEventListener("pointerup", grab);
      window.removeEventListener("pointercancel", grab);
      canvas.style.cursor = "";
      if (controls.mouseButtons) {
        controls.mouseButtons.LEFT = MOUSE.ROTATE;
      }
    };
  }, [panToolActive, viewerReadyTick]);

  const runWithoutPerspectiveEvents = (callback) => {
    suppressPerspectiveEventsRef.current += 1;
    try {
      return callback();
    } finally {
      suppressPerspectiveEventsRef.current = Math.max(0, suppressPerspectiveEventsRef.current - 1);
    }
  };
  const syncCameraZoomPercent = useCallback((runtime = runtimeRef.current) => {
    if (!runtime?.camera) {
      setCameraZoomPercent((current) => (current === 100 ? current : 100));
      return;
    }
    const nextZoomPercent = Math.round(readRuntimeZoomPercent(runtime));
    setCameraZoomPercent((current) => (
      Math.abs(current - nextZoomPercent) < 0.5 ? current : nextZoomPercent
    ));
  }, []);
  // The zoom pill lives in the workspace's top-right toolbar row now, so the live percent
  // has to travel up — the viewer keeps the camera math, the toolbar keeps the control.
  const onCameraZoomPercentChangeRef = useRef(onCameraZoomPercentChange);
  onCameraZoomPercentChangeRef.current = onCameraZoomPercentChange;
  useEffect(() => {
    onCameraZoomPercentChangeRef.current?.(cameraZoomPercent);
  }, [cameraZoomPercent]);
  const emitPerspectiveChange = (runtime = runtimeRef.current) => {
    const currentModelKey = modelKeyRef.current;
    if (!runtimeModelKeyMatches(runtime, currentModelKey)) {
      return;
    }
    const nextPerspective = readScopedPerspectiveSnapshot(runtime, {
      modelKey: currentModelKey,
      sceneScaleMode: sceneScaleModeRef.current
    });
    if (!nextPerspective) {
      return;
    }
    syncCameraZoomPercent(runtime);
    if (suppressPerspectiveEventsRef.current > 0) {
      lastEmittedPerspectiveRef.current = nextPerspective;
      return;
    }
    if (perspectiveSnapshotEqual(lastEmittedPerspectiveRef.current, nextPerspective)) {
      return;
    }
    lastEmittedPerspectiveRef.current = nextPerspective;
    perspectiveChangeRef.current?.(nextPerspective);
  };
  const syncDefaultPerspectiveState = (runtime = runtimeRef.current) => {
    if (defaultPerspectiveResettingRef.current) {
      if (runtime?.cameraTransition) {
        setDefaultPerspectiveDetached(false);
        return;
      }
      defaultPerspectiveResettingRef.current = false;
    }
    const nextDetached = runtime?.THREE
      ? !cameraMatchesViewPreset(runtime, VIEW_PLANE_DEFAULT_PRESET)
      : false;
    setDefaultPerspectiveDetached((current) => (
      current === nextDetached ? current : nextDetached
    ));
  };
  const syncViewPlaneOrientation = (runtime = runtimeRef.current) => {
    const nextOrientation = readViewPlaneOrientation(runtime);
    if (!nextOrientation) {
      return;
    }
    setViewPlaneOrientation((current) => (
      viewPlaneOrientationEqual(current, nextOrientation) ? current : nextOrientation
    ));
    syncDefaultPerspectiveState(runtime);
  };
  const applyInitialPerspective = useCallback((runtime = runtimeRef.current) => {
    const nextPerspective = resolvePerspectiveSnapshot(
      perspectiveRef ? perspectiveRef.current : undefined,
      perspectivePropRef.current
    );
    if (!perspectiveSnapshotMatchesScene(nextPerspective, {
      modelKey: modelKeyRef.current,
      sceneScaleMode: sceneScaleModeRef.current,
      coordinateSystem: coordinateSystemForSceneScale(sceneScaleModeRef.current),
      requireModelKey: true,
      requireSceneScaleMode: true,
      requireCoordinateSystem: true
    })) {
      return false;
    }
    return runWithoutPerspectiveEvents(() => applyPerspectiveSnapshot(runtime, nextPerspective, { scheduleIdle: false }));
  }, [perspectiveRef]);
  const handleViewportResize = useCallback(() => {
    const runtime = runtimeRef.current;
    if (!syncRuntimeViewportFraming(runtime)) {
      return;
    }
    syncCameraZoomPercent(runtime);
    emitPerspectiveChange(runtime);
  }, [syncCameraZoomPercent]);
  const applyZoomPercent = useCallback((nextZoomPercent) => {
    const runtime = runtimeRef.current;
    if (!setRuntimeZoomPercent(runtime, nextZoomPercent)) {
      return;
    }
    syncCameraZoomPercent(runtime);
    emitPerspectiveChange(runtime);
    syncViewPlaneOrientation(runtime);
  }, [
    syncCameraZoomPercent,
    syncViewPlaneOrientation
  ]);
  const resetZoomAndPan = useCallback(({ animate = true } = {}) => {
    const runtime = runtimeRef.current;
    const reset = zoomRuntimeToBounds(
      runtime,
      runtimeFramingBounds(runtime, meshData?.bounds),
      sceneScaleModeRef.current,
      {
        animate,
        modelOffset: modelTransformRef.current.offset,
        resetZoomBaseline: true
      }
    );
    if (reset && !animate) {
      syncCameraZoomPercent(runtime);
      emitPerspectiveChange(runtime);
      syncViewPlaneOrientation(runtime);
    }
    if (reset) {
      return true;
    }
    // Fallback for when the refit bails — no usable bounds yet, so there is
    // nothing to frame. It still has to undo the pan: resetting only the zoom
    // leaves the controls aimed wherever the user dragged to, and the caller's
    // orientation tween carries that target through, so the view snaps back in
    // zoom and angle while staying panned off-centre.
    recenterRuntimeTarget(runtime);
    if (!setRuntimeZoomPercent(runtime, 100)) {
      return false;
    }
    syncCameraZoomPercent(runtime);
    emitPerspectiveChange(runtime);
    syncViewPlaneOrientation(runtime);
    return true;
  }, [
    meshData?.bounds,
    syncCameraZoomPercent,
    syncViewPlaneOrientation
  ]);
  // An implicit publishes its envelope instead of a mesh. Framing it through the
  // same helpers the mesh path uses is what gives implicits the shared zoom
  // baseline, zoom-percent readout, reset and fit behaviour: once
  // runtime.modelBounds is set, runtimeFramingBounds() feeds resetZoomAndPan and
  // zoomToFit with no implicit-specific branch in either.
  const implicitFitSignatureRef = useRef("");
  const handleImplicitModelBounds = useCallback((bounds, { refined = false } = {}) => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.controls || !bounds) {
      return;
    }
    const { THREE, controls } = runtime;
    const sceneScale = sceneScaleModeRef.current;
    const cameraSignature = () => [
      ...runtime.camera.position.toArray(),
      ...controls.target.toArray()
    ].map((value) => Math.round(Number(value) * 1000) / 1000).join(",");

    const { radius } = applyRuntimeModelBounds(THREE, runtime, bounds, sceneScale);
    runtime.zoomBaseModelRadius = boundsModelRadius(THREE, bounds, sceneScale);
    runtime.hasVisibleModel = true;
    runtime.activeModelKey = modelKeyRef.current || "";

    // Size the shared stage to the model, exactly as the mesh path does, so an
    // implicit gets the same themed grid, floor and lighting scope as every
    // other format. An implicit is never re-centred (the SDF is evaluated in
    // world space), so its model position is the origin.
    const floorZ = resolveRuntimeModelFloorZ(bounds, ORIGIN_MODEL_POSITION, sceneScale, {
      followModel: floorFollowsModel
    });
    syncRuntimeScaledLightingAndShadow(
      THREE,
      runtime,
      normalizedThemeSettings.lighting,
      radius,
      bounds,
      sceneScale
    );
    updateActiveGridHelper(runtime, viewerTheme, radius, floorZ, sceneScale, resolvedFloorMode);
    updateSpotLightTarget(runtime);
    updateStageEffects(
      runtime,
      viewerTheme,
      normalizedThemeSettings,
      radius,
      runtime.gridFloorZ ?? 0,
      resolvedFloorMode,
      sceneScale
    );
    syncRuntimeCameraClipPlanes(runtime, Math.max(radius / 1200, 0.01), Math.max(radius * 600, 2000));
    applyCameraFrameInsets(runtime, viewportFrameInsetsRef.current, { updateProjection: false });
    controls.minDistance = Math.max(radius / 2200, 0.02);
    controls.maxDistance = Math.max(radius * 140, 50);

    const activeModelKey = modelKeyRef.current || "";
    const firstFrame = framedModelKeyRef.current !== activeModelKey;
    // A refined envelope may only move the camera if the user has not touched it
    // since our own fit; otherwise the CPU scan would yank the view out from
    // under an orbit or pan seconds after load.
    if (!firstFrame && !(refined && implicitFitSignatureRef.current === cameraSignature())) {
      runtime.requestRender();
      return;
    }

    if (firstFrame) {
      const nextPerspective = resolvePerspectiveSnapshot(
        perspectiveRef ? perspectiveRef.current : undefined,
        perspective
      );
      const restored = perspectiveSnapshotMatchesScene(nextPerspective, {
        modelKey: activeModelKey,
        sceneScaleMode: sceneScale,
        coordinateSystem: coordinateSystemForSceneScale(sceneScale),
        requireModelKey: true,
        requireSceneScaleMode: true,
        requireCoordinateSystem: true
      }) && runWithoutPerspectiveEvents(
        () => applyPerspectiveSnapshot(runtime, nextPerspective, { scheduleIdle: false })
      );
      framedModelKeyRef.current = activeModelKey;
      if (restored) {
        runtime.zoomFitModelRadius = radius;
        resetRuntimeZoomBaseline(runtime);
        syncCameraZoomPercent(runtime);
        implicitFitSignatureRef.current = "";
        runtime.requestRender();
        return;
      }
    }

    runWithoutPerspectiveEvents(() => {
      zoomRuntimeToBounds(runtime, bounds, sceneScale, {
        animate: false,
        resetZoomBaseline: true
      });
    });
    syncCameraZoomPercent(runtime);
    emitPerspectiveChange(runtime);
    syncViewPlaneOrientation(runtime);
    implicitFitSignatureRef.current = cameraSignature();
    runtime.requestRender();
  }, [
    floorFollowsModel,
    normalizedThemeSettings,
    perspective,
    perspectiveRef,
    resolvedFloorMode,
    syncCameraZoomPercent,
    syncViewPlaneOrientation,
    updateActiveGridHelper,
    viewerTheme
  ]);

  const handleImplicitShaderError = useCallback((message) => {
    if (!message) {
      viewerAlertChangeRef.current?.(null);
      setError("");
      return;
    }
    setError(message);
    viewerAlertChangeRef.current?.({
      severity: "error",
      compact: true,
      title: "Implicit CAD shader failed",
      message
    });
  }, []);

  const buildSurfaceLineFaceAnchor = (event, canvas, lockedReferenceId = "", startUv = null) => {
    const runtime = runtimeRef.current;
    if (!runtime?.raycaster || !runtime?.camera || !activeSelectorRuntime?.faceReferenceByRowIndex) {
      return null;
    }
    const activeLockedReferenceId = String(lockedReferenceId || activeSurfaceLineFaceId).trim();

    const rect = canvas.getBoundingClientRect();
    const width = rect.width || 1;
    const height = rect.height || 1;
    runtime.pointer.x = ((event.clientX - rect.left) / width) * 2 - 1;
    runtime.pointer.y = -((event.clientY - rect.top) / height) * 2 + 1;
    runtime.raycaster.setFromCamera(runtime.pointer, runtime.camera);

    const modelMeshes = (runtime.displayRecords || [])
      .map((record) => record?.mesh)
      .filter((mesh) => mesh?.visible && mesh.userData?.faceIds instanceof Uint32Array);
    const modelIntersections = modelMeshes.length ? runtime.raycaster.intersectObjects(modelMeshes, false) : [];
    const proxyIntersections = runtime.facePickMesh ? runtime.raycaster.intersectObject(runtime.facePickMesh, false) : [];
    const intersections = modelIntersections.length
      ? modelIntersections.map((intersection) => ({ intersection, source: "model" }))
      : proxyIntersections.map((intersection) => ({ intersection, source: "proxy" }));
    for (const { intersection, source } of intersections) {
      const triangleIndex = Number(intersection?.faceIndex);
      const rowIndex = Number.isInteger(triangleIndex) ? Number(intersection?.object?.userData?.faceIds?.[triangleIndex]) : NaN;
      if (!Number.isInteger(rowIndex)) {
        continue;
      }
      const reference = activeSelectorRuntime.faceReferenceByRowIndex.get(rowIndex) || null;
      const referenceId = String(reference?.id || "").trim();
      if (!referenceId) {
        continue;
      }
      if (activeLockedReferenceId) {
        if (referenceId !== activeLockedReferenceId) {
          continue;
        }
      } else if (pickableFaceReferenceIds.size && !pickableFaceReferenceIds.has(referenceId)) {
        continue;
      }

      const surface = reference?.pickData?.surface || {};
      if (SURFACE_LINE_UNSUPPORTED_TYPES.has(String(surface.type || "").trim())) {
        return null;
      }
      const localPoint = source === "model" && runtime.modelGroup
        ? runtime.modelGroup.worldToLocal(intersection.point.clone())
        : intersection.object.worldToLocal(intersection.point.clone());
      const point = [localPoint.x, localPoint.y, localPoint.z];
      const angleCenter = surface.type === "CYLINDRICAL_SURFACE" && Array.isArray(startUv) ? (startUv[0] / Math.max(Number(surface.radius) || 1, 1)) : null;
      const uv = projectPointToSurfaceUv(surface, point, angleCenter);
      if (!uv) {
        return null;
      }
      return {
        screenPoint: buildDrawingPoint(event, canvas),
        surfaceLine: {
          referenceId,
          selector: String(reference?.displaySelector || "").trim(),
          normalizedSelector: String(reference?.normalizedSelector || "").trim(),
          faceToken: parseFaceToken(reference?.copyText),
          partId: String(reference?.partId || "").trim(),
          surfaceType: String(surface.type || "").trim(),
          startPoint: point,
          endPoint: point,
          startUv: uv,
          endUv: uv
        }
      };
    }
    return null;
  };
  const updateSurfaceLineFaceAnchor = (event, canvas, draftSurfaceLine) => {
    const lockedReferenceId = String(draftSurfaceLine?.referenceId || "").trim();
    if (!lockedReferenceId) {
      return null;
    }
    const nextAnchor = buildSurfaceLineFaceAnchor(event, canvas, lockedReferenceId, draftSurfaceLine?.startUv);
    if (!nextAnchor) {
      return null;
    }
    return {
      screenPoint: nextAnchor.screenPoint,
      surfaceLine: {
        ...draftSurfaceLine,
        endPoint: nextAnchor.surfaceLine.endPoint,
        endUv: nextAnchor.surfaceLine.endUv
      }
    };
  };

  const readUrdfPosePickerModelPoint = (runtime, picker) => {
    if (!runtime?.raycaster || !runtime?.modelGroup || !picker?.active) {
      return null;
    }
    return intersectUrdfPosePickerShell(runtime, picker);
  };

  const updateUrdfPosePickerHoverFromPointer = (event) => {
    const picker = urdfPosePickerRef.current;
    const runtime = runtimeRef.current;
    const canvas = runtime?.renderer?.domElement || mountRef.current;
    if (
      !picker?.active ||
      previewModeRef.current ||
      !runtime?.raycaster ||
      !runtime?.camera ||
      !canvas ||
      !isPointerInsideElement(event, canvas)
    ) {
      if (runtime) {
        runtime.urdfPosePickerPointerNdc = null;
        syncUrdfPosePickerHoverObjects(runtime, picker);
        if (canvas?.style && urdfPosePickerOwnsCursorRef.current) {
          canvas.style.cursor = "";
          urdfPosePickerOwnsCursorRef.current = false;
        }
        runtime.requestRender?.();
      }
      setUrdfPosePickerHoverActive(false);
      setUrdfPosePickerGuidePoint((current) => (current ? null : current));
      return null;
    }

    const rect = canvas.getBoundingClientRect();
    const width = rect.width || 1;
    const height = rect.height || 1;
    runtime.pointer.x = ((event.clientX - rect.left) / width) * 2 - 1;
    runtime.pointer.y = -((event.clientY - rect.top) / height) * 2 + 1;
    runtime.urdfPosePickerPointerNdc = { x: runtime.pointer.x, y: runtime.pointer.y };
    runtime.raycaster.setFromCamera(runtime.pointer, runtime.camera);

    const pick = readUrdfPosePickerModelPoint(runtime, picker);
    syncUrdfPosePickerHoverObjects(runtime, picker);
    if (canvas.style) {
      canvas.style.cursor = pick?.point ? "pointer" : "crosshair";
      urdfPosePickerOwnsCursorRef.current = true;
    }
    setUrdfPosePickerHoverActive(Boolean(pick?.point));
    setUrdfPosePickerGuidePoint((current) => {
      if (!pick?.point) {
        return current ? null : current;
      }
      const guidePoint = pick.point;
      if (
        Array.isArray(current) &&
        Math.hypot(current[0] - guidePoint[0], current[1] - guidePoint[1], current[2] - guidePoint[2]) < 0.001
      ) {
        return current;
      }
      return guidePoint;
    });
    runtime.requestRender?.();
    return pick;
  };

  const pickUrdfPosePoint = (event) => {
    const picker = urdfPosePickerRef.current;
    const runtime = runtimeRef.current;
    const canvas = runtime?.renderer?.domElement || mountRef.current;
    if (!picker?.active || !runtime?.raycaster || !runtime?.camera || !runtime?.modelGroup || !canvas) {
      return false;
    }

    const rect = canvas.getBoundingClientRect();
    const width = rect.width || 1;
    const height = rect.height || 1;
    runtime.pointer.x = ((event.clientX - rect.left) / width) * 2 - 1;
    runtime.pointer.y = -((event.clientY - rect.top) / height) * 2 + 1;
    runtime.urdfPosePickerPointerNdc = { x: runtime.pointer.x, y: runtime.pointer.y };
    runtime.raycaster.setFromCamera(runtime.pointer, runtime.camera);

    const pick = readUrdfPosePickerModelPoint(runtime, picker);
    if (!pick) {
      setUrdfPosePickerHoverActive(false);
      return false;
    }
    setUrdfPosePickerHoverActive(true);
    setUrdfPosePickerGuidePoint(pick.point);
    picker.onPickPoint?.({
      point: pick.point,
      source: pick.source
    });
    return true;
  };

  const handlePosePickerPointerDown = (event) => {
    const picker = urdfPosePickerRef.current;
    const runtime = runtimeRef.current;
    const canvas = runtime?.renderer?.domElement || mountRef.current;
    if (!picker?.active || previewModeRef.current || event.button !== 0 || !isPointerInsideElement(event, canvas)) {
      return;
    }
    posePickerPointerRef.current = {
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY
    };
  };

  const handlePosePickerPointerMove = (event) => {
    updateUrdfPosePickerHoverFromPointer(event);
  };

  const handlePosePickerPointerUp = (event) => {
    const pointerDown = posePickerPointerRef.current;
    posePickerPointerRef.current = null;
    const picker = urdfPosePickerRef.current;
    const runtime = runtimeRef.current;
    const canvas = runtime?.renderer?.domElement || mountRef.current;
    if (
      !picker?.active ||
      previewModeRef.current ||
      !pointerDown ||
      pointerDown.pointerId !== event.pointerId ||
      !isPointerInsideElement(event, canvas)
    ) {
      return;
    }
    const travel = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
    if (travel > 8) {
      return;
    }
    pickUrdfPosePoint(event);
  };

  const handlePosePickerPointerCancel = () => {
    const runtime = runtimeRef.current;
    posePickerPointerRef.current = null;
    if (runtime) {
      runtime.urdfPosePickerPointerNdc = null;
      syncUrdfPosePickerHoverObjects(runtime, urdfPosePickerRef.current);
      if (runtime.renderer?.domElement?.style && urdfPosePickerOwnsCursorRef.current) {
        runtime.renderer.domElement.style.cursor = "";
        urdfPosePickerOwnsCursorRef.current = false;
      }
      runtime.requestRender?.();
    }
    setUrdfPosePickerHoverActive(false);
  };

  const handlePosePickerPointerLeave = () => {
    const runtime = runtimeRef.current;
    posePickerPointerRef.current = null;
    if (runtime) {
      runtime.urdfPosePickerPointerNdc = null;
      syncUrdfPosePickerHoverObjects(runtime, urdfPosePickerRef.current);
      if (runtime.renderer?.domElement?.style && urdfPosePickerOwnsCursorRef.current) {
        runtime.renderer.domElement.style.cursor = "";
        urdfPosePickerOwnsCursorRef.current = false;
      }
      runtime.requestRender?.();
    }
    setUrdfPosePickerHoverActive(false);
    setUrdfPosePickerGuidePoint((current) => (current ? null : current));
  };

  const activateViewPlaneFace = (faceId) => {
    const runtime = runtimeRef.current;
    const face = VIEW_PLANE_FACE_BY_ID[faceId];
    if (!runtime || !face) {
      return false;
    }
    activeViewPlaneFaceRef.current = face.id;
    setActiveViewPlaneFace(face.id);
    const transitioned = transitionCameraToViewPreset(runtime, face);
    if (transitioned) {
      defaultPerspectiveResettingRef.current = false;
      setDefaultPerspectiveDetached(true);
    }
    return transitioned;
  };
  const activateDefaultViewPlane = () => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return false;
    }
    activeViewPlaneFaceRef.current = "";
    setActiveViewPlaneFace("");
    const transitioned = transitionCameraToViewPreset(runtime, VIEW_PLANE_DEFAULT_PRESET);
    if (transitioned) {
      defaultPerspectiveResettingRef.current = true;
      setDefaultPerspectiveDetached(false);
    }
    return transitioned;
  };

  // PLAN MODE: a generic top-down camera lock, reusable by any model, not a DXF feature.
  //
  // Rotation is what makes a view 3D. Disabling it (and moving the left button onto pan) is
  // the whole mode: the camera keeps looking straight down, dragging slides the model, and
  // wheel-zoom still works. Everything else that reads as three-dimensional -- the view cube,
  // the vertical origin axis -- is hidden by the caller through `planMode`, so the viewport
  // stops advertising an axis you cannot turn towards.
  useEffect(() => {
    const runtime = runtimeRef.current;
    const controls = runtime?.controls;
    if (!controls) {
      return undefined;
    }
    const previousRotate = controls.enableRotate;
    const previousButtons = controls.mouseButtons ? { ...controls.mouseButtons } : null;
    if (planMode) {
      controls.enableRotate = false;
      if (controls.mouseButtons) {
        // Left-drag pans instead of orbiting; a locked view whose primary drag does nothing
        // reads as broken rather than as locked.
        controls.mouseButtons = { ...controls.mouseButtons, LEFT: THREE.MOUSE.PAN };
      }
    }
    const axis = runtime.originAxis;
    const previousAxisVisible = axis ? axis.visible : null;
    if (axis && planMode) {
      axis.visible = false;
    }
    controls.update?.();
    runtime.requestRender?.();
    return () => {
      const activeControls = runtimeRef.current?.controls;
      if (!activeControls) {
        return;
      }
      activeControls.enableRotate = previousRotate;
      if (previousButtons) {
        activeControls.mouseButtons = previousButtons;
      }
      const activeAxis = runtimeRef.current?.originAxis;
      if (activeAxis && previousAxisVisible !== null) {
        activeAxis.visible = previousAxisVisible;
      }
      activeControls.update?.();
      runtimeRef.current?.requestRender?.();
    };
  }, [planMode, viewerReadyTick]);

  // DRAWING TRANSFORM: thickness and fold, one vertex rewrite, math from
  // cadjs/lib/dxf/foldPreview (node-tested; the snapshot runtime shares it by construction).
  //
  // Applied SYNCHRONOUSLY when the meshes already exist. The previous version restored flat
  // positions in its cleanup and re-folded on the next animation frame — so every slider
  // tick painted one flat frame between the two, which is the flicker. Cleanup now only
  // cancels a pending first-load retry: the next run overwrites positions from the cached
  // flat copy anyway, and an identity run writes the flat values back explicitly.
  useEffect(() => {
    const runtime = runtimeRef.current;
    const group = runtime?.modelGroup;
    if (!group) {
      return undefined;
    }
    // Bend lines as full 2D segments (orientation matters — the fold handles any direction);
    // the scanner's bare axis-X list is only the fallback until geometry.json lands.
    const foldOptions = {
      bendLines: Array.isArray(drawingBendLines) && drawingBendLines.length ? drawingBendLines : null,
      bendAxesX: Array.isArray(bendAxisX) ? bendAxisX : [],
      bendAnglesRad: Array.isArray(bendAnglesRad) ? bendAnglesRad : [],
      thicknessScale: drawingThicknessScale
    };
    const identity = dxfFoldIsIdentity(foldOptions);
    const bendCount = foldOptions.bendLines ? foldOptions.bendLines.length : foldOptions.bendAxesX.length;

    // Post-fold model orientation: quarter-turns about each world axis, rotating the folded
    // part about the flat pattern's own centre so it stays where the camera is looking.
    // Exact by construction (sin/cos of k*90 degrees are integers), and applied to the SAME
    // buffers the fold writes, so overlays, picking, and fit all follow.
    const quarterTurn = (component) => {
      const numeric = Math.trunc(Number(component));
      return Number.isFinite(numeric) ? ((numeric % 4) + 4) % 4 : 0;
    };
    const orientation = {
      x: quarterTurn(drawingOrientation?.x),
      y: quarterTurn(drawingOrientation?.y),
      z: quarterTurn(drawingOrientation?.z)
    };
    const orientationActive = orientation.x !== 0 || orientation.y !== 0 || orientation.z !== 0;
    const orientationMatrix = orientationActive
      ? new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(
        (orientation.x * Math.PI) / 2,
        (orientation.y * Math.PI) / 2,
        (orientation.z * Math.PI) / 2,
        "XYZ"
      ))
      : null;
    const anyBendAngle = foldOptions.bendAnglesRad.some((angle) => angle !== 0);

    // Layer visibility: hiding a cut layer changes the SOLID, which only a live re-mesh can
    // express — the baked prism has the hidden geometry welded in.
    const hiddenLayers = new Set(Array.isArray(drawingHiddenLayers) ? drawingHiddenLayers : []);
    const geometryLayers = Array.isArray(drawingGeometry?.layers) ? drawingGeometry.layers : [];
    const anyCutLayerHidden = hiddenLayers.size > 0
      && geometryLayers.some((layer) => hiddenLayers.has(layer.name) && layer.kind === "cut");
    const filterByLayer = (records) => (Array.isArray(records)
      ? records.filter((record) => !hiddenLayers.has(record?.layer))
      : []);
    const effectiveGeometry = drawingGeometry?.geometry
      ? (hiddenLayers.size
        ? {
          ...drawingGeometry,
          geometry: {
            lines: filterByLayer(drawingGeometry.geometry.lines),
            arcs: filterByLayer(drawingGeometry.geometry.arcs),
            circles: filterByLayer(drawingGeometry.geometry.circles),
            texts: filterByLayer(drawingGeometry.geometry.texts)
          }
        }
        : drawingGeometry)
      : null;

    // Curved re-meshes from the package's cached contours: the flat prism has no vertices
    // inside a bend region to curve, so a curved bend is a FRESH mesh (the full mesher, the
    // old live path), not a transform of the baked one. Boxed stays the vertex fold — but a
    // hidden cut layer forces the re-mesh path too (its bends then render curved; the mesher
    // has one bend geometry).
    const curvedRequested = !!effectiveGeometry
      && ((drawingBendStyle === "curved" && bendCount > 0 && anyBendAngle) || anyCutLayerHidden);

    // Overlays (dotted guides, score lines, text markings) exist for any drawing whose
    // geometry is loaded, even flat at identity.
    const hasOverlaySource = !!effectiveGeometry;
    if (!curvedRequested && identity && !orientationActive && !hasOverlaySource
      && !drawingMaterialColor && !runtimeRef.current?.dxfTransformTouched) {
      return undefined;
    }
    runtimeRef.current.dxfTransformTouched = curvedRequested || !identity || orientationActive;
    let frame = 0;
    let attempts = 0;

    const apply = () => {
      // Everything here keys on the GEOMETRY, never the mesh. Geometries are cached and
      // reused across mounts while meshes are rebuilt per scene — a baseline stored on the
      // mesh is lost on remount, and the next visit then snapshots the previous visit's
      // POSE as "flat" (measured: reopening a 5 mm drawing made 8 mm render 40 mm tall).
      const targets = [];
      const seenGeometries = new Set();
      group.traverse((child) => {
        if (
          child.userData?.dxfBendGuide
          || child.userData?.dxfCurvedPreview
          || child.userData?.dxfScoreOverlay
          || child.userData?.dxfTextMarking
        ) {
          return;
        }
        const geometry = child.geometry;
        let position = geometry?.getAttribute?.("position");
        if (!position) {
          return;
        }
        if (seenGeometries.has(geometry)) {
          // Occurrences share geometry; transforming it once per apply is both correct and
          // what keeps the fold from compounding across instances.
          return;
        }
        seenGeometries.add(geometry);
        // First touch of this geometry, ever: snapshot the FLAT baseline and DETACH the
        // attribute onto a private buffer. The scene wraps the mesh cache's own vertex
        // array when it is already a Float32Array (cadScene sourceMesh path, no copy) —
        // writing through it would corrupt the cache's flat baseline for every future
        // mount. The transform may only ever own memory nothing else reads.
        if (!geometry.userData.dxfFoldOriginal) {
          geometry.userData.dxfFoldOriginal = Float32Array.from(position.array);
          const privateAttribute = new THREE.BufferAttribute(Float32Array.from(position.array), 3);
          geometry.setAttribute("position", privateAttribute);
          position = privateAttribute;
        }
        // The material-preset tint rides the mesh as a claim (like dxfHiddenForCurved):
        // partVisualState re-asserts surface colors on every selection/hover pass, and it
        // honours this in place of the record's base color. The curved preview shares this
        // mesh's material, so it follows automatically.
        if (drawingMaterialColor) {
          child.userData.dxfMaterialTint = new THREE.Color(drawingMaterialColor);
        } else {
          delete child.userData.dxfMaterialTint;
        }
        targets.push({ child, geometry, original: geometry.userData.dxfFoldOriginal, position });
      });

      if (!targets.length) {
        // First load only: this effect is declared before the scene sync, so a fresh model's
        // group can still be empty. Retry a few frames rather than silently doing nothing.
        if ((!identity || curvedRequested || hasOverlaySource) && attempts < 60) {
          attempts += 1;
          frame = requestAnimationFrame(apply);
        }
        return;
      }

      const removeCurvedPreview = () => {
        const curved = runtimeRef.current?.dxfCurvedPreview;
        if (curved) {
          curved.parent?.remove(curved);
          curved.geometry?.dispose?.();
          runtimeRef.current.dxfCurvedPreview = null;
        }
      };

      // Orientation helpers (no-ops when inactive), rotating about the flat pattern's own
      // centre so the reoriented part stays under the camera.
      let orientCenter = null;
      if (orientationMatrix && targets.length) {
        const source = targets[0].original;
        let minX = Infinity;
        let maxX = -Infinity;
        let minY = Infinity;
        let maxY = -Infinity;
        for (let index = 0; index < source.length; index += 3) {
          const x = source[index];
          const y = source[index + 1];
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
        orientCenter = [(minX + maxX) / 2, (minY + maxY) / 2, 0];
      }
      const orientElements = orientationMatrix?.elements || null;
      const orientBuffer = (array) => {
        if (!orientElements || !orientCenter) {
          return array;
        }
        const e = orientElements;
        for (let index = 0; index < array.length; index += 3) {
          const x = array[index] - orientCenter[0];
          const y = array[index + 1] - orientCenter[1];
          const z = array[index + 2] - orientCenter[2];
          array[index] = e[0] * x + e[4] * y + e[8] * z + orientCenter[0];
          array[index + 1] = e[1] * x + e[5] * y + e[9] * z + orientCenter[1];
          array[index + 2] = e[2] * x + e[6] * y + e[10] * z + orientCenter[2];
        }
        return array;
      };
      const orientPoint = (point) => {
        if (!orientElements || !orientCenter) {
          return point;
        }
        const e = orientElements;
        const x = point[0] - orientCenter[0];
        const y = point[1] - orientCenter[1];
        const z = point[2] - orientCenter[2];
        return [
          e[0] * x + e[4] * y + e[8] * z + orientCenter[0],
          e[1] * x + e[5] * y + e[9] * z + orientCenter[1],
          e[2] * x + e[6] * y + e[10] * z + orientCenter[2]
        ];
      };

      let guideSegments = null;
      let flat = null;
      if (curvedRequested) {
        // Full remesh, exactly the geometry the old live viewer built: tessellated bend
        // bands, constant thickness around the arc. The baked meshes are hidden, not
        // touched — the curved preview is its own object, so nothing cached is at risk.
        // Direction flips on the way in. The mesher bends "up" toward ITS +Y, and the only
        // proper rotation into CAD Z-up that keeps the pattern footprint un-mirrored,
        // (x, y, z) -> (x, z, -y), sends mesher +Y to CAD -Z. Handing the mesher the
        // opposite direction is what makes the UI's Up fold up on screen.
        const bendSettings = Array.isArray(drawingBends)
          ? drawingBends.map((bend) => ({
            angleDeg: bend?.angleDeg,
            direction: bend?.direction === "down" ? "up" : "down"
          }))
          : [];
        // The mesher treats <= 0 as "use the drawing default" (2 mm); a hair keeps the
        // 0 mm setting meaning FLAT-thin rather than jumping to the default.
        const meshThicknessMm = Math.max(Number(drawingThicknessMm) || 0, 0.05);
        let curvedData = null;
        try {
          // guideElevationSign -1: the (x, z, -y) map below sends the mesher's +Y to CAD
          // -Z, so guides elevated over the mesher's top face would land UNDER the sheet.
          curvedData = buildDxfPreviewMeshData(effectiveGeometry, meshThicknessMm, bendSettings, {
            guideElevationSign: -1,
            bendInsideRadiusMm: drawingBendRadiusMm,
            bendKFactor: drawingKFactor
          });
        } catch (curveError) {
          // A drawing the bend mesher cannot band (a hole crossing a bend region) falls
          // back to the sharp fold rather than rendering nothing.
          curvedData = null;
        }
        if (curvedData) {
          // Mesher output is Y-up; the scene is CAD Z-up: (x, y, z) -> (x, z, -y).
          const source = curvedData.vertices;
          const mapped = new Float32Array(source.length);
          for (let index = 0; index < source.length; index += 3) {
            mapped[index] = source[index];
            mapped[index + 1] = source[index + 2];
            mapped[index + 2] = -source[index + 1];
          }
          orientBuffer(mapped);
          let curved = runtimeRef.current?.dxfCurvedPreview || null;
          if (curved && curved.parent !== group) {
            curved = null;
            runtimeRef.current.dxfCurvedPreview = null;
          }
          if (!curved) {
            curved = new THREE.Mesh(new THREE.BufferGeometry(), targets[0].child.material);
            curved.userData.dxfCurvedPreview = true;
            group.add(curved);
            runtimeRef.current.dxfCurvedPreview = curved;
          }
          curved.material = targets[0].child.material;
          curved.geometry.setAttribute("position", new THREE.BufferAttribute(mapped, 3));
          curved.geometry.setIndex(new THREE.BufferAttribute(curvedData.indices, 1));
          curved.geometry.computeVertexNormals();
          curved.geometry.computeBoundingBox?.();
          curved.geometry.computeBoundingSphere?.();
          for (const { child } of targets) {
            if (child.visible) {
              child.userData.dxfHiddenForCurved = true;
              child.visible = false;
            }
          }
          const guides = curvedData.guide_line_segments;
          if (guides?.length) {
            guideSegments = new Float32Array(guides.length);
            for (let index = 0; index < guides.length; index += 3) {
              guideSegments[index] = guides[index];
              guideSegments[index + 1] = guides[index + 2];
              guideSegments[index + 2] = -guides[index + 1];
            }
          }
          flat = targets[0]?.original || null;
        }
      }

      if (!curvedRequested || !runtimeRef.current?.dxfCurvedPreview) {
        removeCurvedPreview();
        for (const { child } of targets) {
          if (child.userData.dxfHiddenForCurved) {
            child.visible = true;
            delete child.userData.dxfHiddenForCurved;
          }
        }
        for (const { geometry, original, position } of targets) {
          transformDxfPreviewPositions(original, position.array, foldOptions);
          orientBuffer(position.array);
          position.needsUpdate = true;
          geometry.computeVertexNormals?.();
          geometry.computeBoundingBox?.();
          geometry.computeBoundingSphere?.();
          if (!flat || original.length > flat.length) {
            flat = original;
          }
        }
      }

      // The dotted bend lines, folded through the same chain so each stays on its crease.
      // The overlay OBJECT persists and its buffer is swapped — removing and re-adding it
      // per slider tick made the dashes blink alongside the old geometry flicker.
      let overlay = runtimeRef.current?.dxfBendGuideOverlay || null;
      if (overlay && overlay.parent !== group) {
        // The scene sync cleared the group under us; the ref is a dangling object.
        overlay = null;
        runtimeRef.current.dxfBendGuideOverlay = null;
      }
      // Hiding a bend layer hides its dashed guides too — the crease marks ARE that layer.
      const bendLayerHidden = hiddenLayers.size > 0
        && geometryLayers.some((layer) => hiddenLayers.has(layer.name) && layer.kind === "bend");
      const segments = bendLayerHidden
        ? new Float32Array(0)
        : guideSegments
          || (flat && bendCount
            ? dxfBendGuideSegments(flat, foldOptions)
            : new Float32Array(0));
      if (!segments.length) {
        if (overlay) {
          overlay.parent?.remove(overlay);
          overlay.geometry?.dispose?.();
          overlay.material?.dispose?.();
          runtimeRef.current.dxfBendGuideOverlay = null;
        }
      } else {
        if (!overlay) {
          const { yMin, yMax } = dxfFlatPatternExtents(flat);
          const span = Math.max(yMax - yMin, 1);
          overlay = new THREE.LineSegments(
            new THREE.BufferGeometry(),
            new THREE.LineDashedMaterial({
              color: 0x5f6775,
              dashSize: span / 24,
              gapSize: span / 36,
              transparent: true,
              opacity: 0.9,
              depthWrite: false
            })
          );
          overlay.userData.dxfBendGuide = true;
          overlay.frustumCulled = false;
          group.add(overlay);
          runtimeRef.current.dxfBendGuideOverlay = overlay;
        }
        overlay.geometry.setAttribute("position", new THREE.BufferAttribute(orientBuffer(segments), 3));
        overlay.computeLineDistances();
        overlay.geometry.computeBoundingSphere?.();
      }

      // SCORE LINES and TEXT MARKINGS: the drawing's annotations, overlaid on the sheet's
      // top face and folded through the same chain as the geometry. In curved mode the fold
      // used here is the vertex fold, so a score crossing a bend band chords across the arc
      // — an accepted approximation; annotations rarely sit inside a bend.
      const resolvedFold = normalizeDxfFoldOptions(foldOptions);
      const layerColorByName = new Map(geometryLayers.map((layer) => [layer.name, layer.colorHex]));
      const flatExtents = flat ? dxfFlatPatternExtents(flat) : { zMax: 0.5 };
      const zTop = flatExtents.zMax + 0.3 / Math.max(resolvedFold.scale, 1e-6);

      let scoreSegments = [];
      if (effectiveGeometry) {
        try {
          for (const polyline of extractDxfScorePolylines(effectiveGeometry)) {
            for (let index = 0; index < polyline.length - 1; index += 1) {
              const a = foldDxfPoint(polyline[index][0], polyline[index][1], zTop, resolvedFold);
              const b = foldDxfPoint(polyline[index + 1][0], polyline[index + 1][1], zTop, resolvedFold);
              scoreSegments.push(a[0], a[1], a[2], b[0], b[1], b[2]);
            }
          }
        } catch (scoreError) {
          scoreSegments = [];
        }
      }
      let scoreOverlay = runtimeRef.current?.dxfScoreOverlay || null;
      if (scoreOverlay && scoreOverlay.parent !== group) {
        scoreOverlay = null;
        runtimeRef.current.dxfScoreOverlay = null;
      }
      if (!scoreSegments.length) {
        if (scoreOverlay) {
          scoreOverlay.parent?.remove(scoreOverlay);
          scoreOverlay.geometry?.dispose?.();
          scoreOverlay.material?.dispose?.();
          runtimeRef.current.dxfScoreOverlay = null;
        }
      } else {
        if (!scoreOverlay) {
          scoreOverlay = new THREE.LineSegments(
            new THREE.BufferGeometry(),
            new THREE.LineBasicMaterial({
              color: 0x8a93a3,
              transparent: true,
              opacity: 0.95,
              depthWrite: false
            })
          );
          scoreOverlay.userData.dxfScoreOverlay = true;
          scoreOverlay.frustumCulled = false;
          group.add(scoreOverlay);
          runtimeRef.current.dxfScoreOverlay = scoreOverlay;
        }
        scoreOverlay.geometry.setAttribute(
          "position",
          new THREE.BufferAttribute(orientBuffer(Float32Array.from(scoreSegments)), 3)
        );
        scoreOverlay.geometry.computeBoundingSphere?.();
      }

      // Text markings render as canvas-textured planes lying on the sheet — string, height,
      // rotation from the DXF; no font tables, no glyph outlines. Rebuilt per apply: a
      // drawing carries a handful of labels, not thousands.
      let textGroup = runtimeRef.current?.dxfTextGroup || null;
      if (textGroup && textGroup.parent !== group) {
        textGroup = null;
        runtimeRef.current.dxfTextGroup = null;
      }
      const disposeTextChildren = (container) => {
        for (const child of [...container.children]) {
          container.remove(child);
          child.geometry?.dispose?.();
          child.material?.map?.dispose?.();
          child.material?.dispose?.();
        }
      };
      const textMarkings = Array.isArray(effectiveGeometry?.geometry?.texts)
        ? effectiveGeometry.geometry.texts.filter((text) => String(text?.value || "").trim())
        : [];
      if (!textMarkings.length) {
        if (textGroup) {
          disposeTextChildren(textGroup);
          textGroup.parent?.remove(textGroup);
          runtimeRef.current.dxfTextGroup = null;
        }
      } else if (typeof document !== "undefined") {
        if (!textGroup) {
          textGroup = new THREE.Group();
          textGroup.userData.dxfTextMarking = true;
          group.add(textGroup);
          runtimeRef.current.dxfTextGroup = textGroup;
        }
        disposeTextChildren(textGroup);
        for (const text of textMarkings) {
          const value = String(text.value).trim();
          const heightMm = Math.max(Number(text.heightMm) || 2.5, 0.2);
          const anchor = text.position;
          const rotation = ((Number(text.rotationDeg) || 0) * Math.PI) / 180;
          const ex = [Math.cos(rotation), Math.sin(rotation)];
          const ey = [-Math.sin(rotation), Math.cos(rotation)];
          const fontPx = 64;
          const canvas = document.createElement("canvas");
          const context = canvas.getContext("2d");
          if (!context) {
            continue;
          }
          const fontSpec = `600 ${fontPx}px ui-sans-serif, system-ui, sans-serif`;
          context.font = fontSpec;
          const firstLine = value.split("\n")[0];
          const textWidthPx = Math.max(context.measureText(firstLine).width, fontPx * 0.5);
          canvas.width = Math.ceil(textWidthPx) + 8;
          canvas.height = Math.ceil(fontPx * 1.35);
          const drawContext = canvas.getContext("2d");
          drawContext.font = fontSpec;
          drawContext.fillStyle = layerColorByName.get(text.layer) || "#8a93a3";
          drawContext.textBaseline = "alphabetic";
          drawContext.fillText(firstLine, 4, fontPx);
          const texture = new THREE.CanvasTexture(canvas);
          texture.colorSpace = THREE.SRGBColorSpace;
          const planeWidth = heightMm * (canvas.width / fontPx);
          const planeHeight = heightMm * (canvas.height / fontPx);
          // The DXF anchor is baseline-left; the plane's centre sits half a width along the
          // text direction and a bit above the baseline. All in FLAT coords, then folded.
          const centerFlat = [
            anchor[0] + ex[0] * (planeWidth / 2) + ey[0] * (planeHeight * 0.22),
            anchor[1] + ex[1] * (planeWidth / 2) + ey[1] * (planeHeight * 0.22)
          ];
          const origin3 = orientPoint(foldDxfPoint(centerFlat[0], centerFlat[1], zTop, resolvedFold));
          const step = 0.5;
          const alongX = orientPoint(foldDxfPoint(centerFlat[0] + ex[0] * step, centerFlat[1] + ex[1] * step, zTop, resolvedFold));
          const alongY = orientPoint(foldDxfPoint(centerFlat[0] + ey[0] * step, centerFlat[1] + ey[1] * step, zTop, resolvedFold));
          const basisX = new THREE.Vector3(alongX[0] - origin3[0], alongX[1] - origin3[1], alongX[2] - origin3[2]).normalize();
          const basisY = new THREE.Vector3(alongY[0] - origin3[0], alongY[1] - origin3[1], alongY[2] - origin3[2]).normalize();
          const basisZ = new THREE.Vector3().crossVectors(basisX, basisY).normalize();
          const marking = new THREE.Mesh(
            new THREE.PlaneGeometry(planeWidth, planeHeight),
            new THREE.MeshBasicMaterial({
              map: texture,
              transparent: true,
              depthWrite: false,
              side: THREE.DoubleSide
            })
          );
          marking.userData.dxfTextMarking = true;
          marking.position.set(origin3[0], origin3[1], origin3[2]);
          marking.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(basisX, basisY, basisZ));
          marking.renderOrder = 2;
          textGroup.add(marking);
        }
      }

      runtime.requestRender?.();
    };

    apply();
    return () => {
      cancelAnimationFrame(frame);
    };
  }, [bendAxisX, drawingBendLines, bendAnglesRad, drawingBends, drawingBendStyle, drawingBendRadiusMm, drawingKFactor, drawingHiddenLayers, drawingOrientation, drawingMaterialColor, drawingGeometry, drawingThicknessMm, drawingThicknessScale, meshData, viewerReadyTick]);

  useImperativeHandle(ref, () => ({
    async captureScreenshot({ filename = "cad-screenshot.png", mode = "download" } = {}) {
      const runtime = runtimeRef.current;
      if (!runtime?.renderer || !runtime?.scene || !runtime?.camera) {
        throw new Error("CAD Viewer not ready");
      }

      renderDrawingOverlay();
      const blobPromise = buildCompositeScreenshotBlob(runtime, drawingCanvasRef.current, {
        backgroundColor: mode === "clipboard"
          ? resolveElementBackgroundColor(runtime.renderer.domElement)
          : "",
        crop: getViewportFrameCrop(runtime, viewportFrameInsetsRef.current)
      });

      if (mode === "clipboard") {
        return await copyImageBlobToClipboard(blobPromise);
      }

      const blob = await blobPromise;
      return triggerBlobDownload(blob, { filename });
    },
    // Exposed so a toolbar can drive the camera the same way the view-plane widget does.
    // The DXF 2D/3D toggle is exactly "look straight down" vs "the default three-quarter
    // view", and reusing these keeps one camera authority rather than a second one that
    // drifts from the widget's idea of where `top` is.
    activateViewPlaneFace(faceId) {
      return activateViewPlaneFace(faceId);
    },
    applyZoomPercent(nextZoomPercent) {
      return applyZoomPercent(nextZoomPercent);
    },
    resetView() {
      // Refit instantly (establishes target and distance), then animate the orientation —
      // both drive the same cameraTransition, so animating both would fight.
      resetZoomAndPan({ animate: false });
      activateDefaultViewPlane();
    },
    activateDefaultViewPlane() {
      return activateDefaultViewPlane();
    },
    getPerspective() {
      return readScopedPerspectiveSnapshot(runtimeRef.current, {
        modelKey,
        sceneScaleMode: normalizedSceneScaleMode
      });
    },
    setPerspective(perspective, options = {}) {
      if (options?.animate) {
        return transitionCameraToPerspectiveSnapshot(runtimeRef.current, perspective, options);
      }
      return applyPerspectiveSnapshot(runtimeRef.current, perspective);
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
      // `implicitActive` made the fallback implicit-only, and it is not: a plain mesh has
      // no sub-part selection either.
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
    previewModeRef.current = previewMode;
  }, [previewMode]);

  useEffect(() => {
    drawingChangeRef.current = onDrawingStrokesChange;
  }, [onDrawingStrokesChange]);

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
    urdfPosePickerRef.current = urdfPosePicker;
  }, [urdfPosePicker]);

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

  useEffect(() => {
    if (urdfPosePicker?.active) {
      return;
    }
    const runtime = runtimeRef.current;
    if (runtime) {
      runtime.urdfPosePickerPointerNdc = null;
      if (runtime.renderer?.domElement?.style && urdfPosePickerOwnsCursorRef.current) {
        runtime.renderer.domElement.style.cursor = "";
        urdfPosePickerOwnsCursorRef.current = false;
      }
    }
    setUrdfPosePickerHoverActive(false);
    setUrdfPosePickerGuidePoint(null);
  }, [urdfPosePicker?.active]);

  useEffect(() => {
    drawingStrokesRef.current = Array.isArray(drawingStrokes) ? drawingStrokes : [];
    drawingIdRef.current = Math.max(drawingIdRef.current, maxDrawingStrokeOrdinal(drawingStrokesRef.current));
    renderDrawingOverlay();
  }, [drawingStrokes]);

  const handleRuntimeContextRestored = useCallback(() => {
    framedModelKeyRef.current = "";
    lastEmittedPerspectiveRef.current = null;
    defaultPerspectiveResettingRef.current = false;
    viewerAlertChangeRef.current?.(null);
    setDefaultPerspectiveDetached(false);
    setRuntimeResetToken((value) => value + 1);
  }, []);

  const handleRuntimeInitializationError = useCallback((runtimeError) => {
    viewerAlertChangeRef.current?.(buildRuntimeInitializationAlert(runtimeError));
  }, []);

  useViewerRuntime({
    mountRef,
    runtimeRef,
    previewModeRef,
    setError,
    setViewerReadyTick,
    viewerTheme,
    syncDrawingCanvasSize,
    renderDrawingOverlay,
    emitPerspectiveChange,
    setActiveViewPlaneFace,
    activeViewPlaneFaceRef,
    stepCameraTransition,
    stepKeyboardOrbit,
    getActiveViewPlaneFaceId,
    cancelCameraTransition,
    clearKeyboardOrbitState,
    isTrackpadLikeWheelEvent,
    getKeyboardOrbitCommand,
    getKeyboardOrbitAxes,
    applyOrbitDelta,
    getViewerThemeValue,
    getPixelRatioCap,
    applySceneBackground: applyActiveSceneBackground,
    applyCameraFrameInsets,
    frameInsetsRef: viewportFrameInsetsRef,
    onViewportResize: handleViewportResize,
    applyInitialPerspective,
    updateGridHelper: updateActiveGridHelper,
    clearSceneGroup,
    disposeSceneObject,
    disposeTexture,
    syncViewPlaneOrientation,
    BASE_VIEWER_THEME,
    DEFAULT_LIGHTING,
    DEFAULT_DAMPING_FACTOR,
    DEFAULT_ZOOM_SPEED,
    COARSE_POINTER_ZOOM_SPEED,
    INTERACTION_PIXEL_RATIO_CAP,
    IDLE_PIXEL_RATIO_CAP,
    INTERACTION_IDLE_DELAY_MS,
    TRACKPAD_PINCH_ZOOM_SPEED,
    COARSE_POINTER_PINCH_ZOOM_SPEED,
    ACCELERATED_WHEEL_ZOOM_SPEED,
    KEYBOARD_ORBIT_NUDGE_RAD,
    defaultGridRadius,
    sceneScaleMode: normalizedSceneScaleMode,
    floorMode: resolvedFloorMode,
    onInitializationError: handleRuntimeInitializationError,
    onContextRestored: handleRuntimeContextRestored,
    preserveInteractionPixelRatio,
    runtimeResetToken
  });

  useImplicitRaymarch({
    runtimeRef,
    viewerReadyTick,
    enabled: implicitActive,
    model: implicitModel,
    themeSettings: normalizedThemeSettings,
    graphicsSettings: implicitGraphicsSettings,
    dynamicRenderActive: implicitDynamicRenderActive,
    previewMode,
    onModelBounds: handleImplicitModelBounds,
    onShaderError: handleImplicitShaderError
  });

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }
    runtime.sceneScaleMode = normalizedSceneScaleMode;
  }, [normalizedSceneScaleMode]);

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
      normalizedSceneScaleMode
    );
    updateSpotLightTarget(runtime);

    // Keep a single primary shadow; the spot light drives the floor glow/fill.
    runtime.keyLight.castShadow = runtime.keyLight.visible && runtime.softwareRendering !== true;
    runtime.spotLight.castShadow = false;

    const materialSettings = {
      ...normalizedThemeSettings.materials,
      envMapIntensity: normalizedThemeSettings.materials.envMapIntensity * (
        normalizedThemeSettings.environment.enabled ? normalizedThemeSettings.environment.intensity : 0
      )
    };
    for (const record of runtime.displayRecords || []) {
      applyMaterialSettingsToRecord(runtime.THREE, record, materialSettings, {
        displayMode: normalizedDisplayMode
      });
    }

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
    runtime.requestRender();
  }, [
    defaultGridRadius,
    normalizedDisplayMode,
    normalizedThemeSettings,
    normalizedSceneScaleMode,
    resolvedFloorMode,
    floorFollowsModel,
    viewerReadyTick,
    viewerTheme,
    updateActiveGridHelper
  ]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.scene) {
      return;
    }

    let cancelled = false;
    const environmentSettings = normalizedThemeSettings.environment;
    const clearEnvironmentTexture = () => {
      runtime.scene.environment = null;
      disposeTexture(runtime.environmentTexture);
      runtime.environmentTexture = null;
      runtime.environmentTextureUrl = "";
    };
    const applyBackgroundFallback = () => {
      clearEnvironmentTexture();
      applyActiveSceneBackground(runtime, viewerTheme, normalizedThemeSettings.background);
      runtime.requestRender();
    };

    const loadAndApplyEnvironment = async () => {
      if (!environmentSettings.enabled) {
        viewerAlertChangeRef.current?.(null);
        applyBackgroundFallback();
        return;
      }

      const preset = getEnvironmentPresetById(environmentSettings.presetId);
      const textureUrl = String(preset?.url || "").trim();
      if (!textureUrl) {
        viewerAlertChangeRef.current?.(null);
        applyBackgroundFallback();
        return;
      }

      if (!runtime.environmentTexture || runtime.environmentTextureUrl !== textureUrl) {
        const textureLoader = new runtime.THREE.TextureLoader();
        if (typeof textureLoader.setCrossOrigin === "function") {
          textureLoader.setCrossOrigin("anonymous");
        }
        const nextTexture = await textureLoader.loadAsync(textureUrl);
        if (cancelled) {
          nextTexture.dispose?.();
          return;
        }
        nextTexture.mapping = runtime.THREE.EquirectangularReflectionMapping;
        nextTexture.colorSpace = runtime.THREE.SRGBColorSpace;
        nextTexture.needsUpdate = true;
        disposeTexture(runtime.environmentTexture);
        runtime.environmentTexture = nextTexture;
        runtime.environmentTextureUrl = textureUrl;
      }

      runtime.scene.environment = runtime.environmentTexture;
      viewerAlertChangeRef.current?.(null);

      if (runtime.scene.environmentRotation?.set) {
        runtime.scene.environmentRotation.set(0, environmentSettings.rotationY, 0);
      }
      if (environmentSettings.useAsBackground) {
        runtime.scene.background = runtime.environmentTexture;
        if (runtime.scene.backgroundRotation?.set) {
          runtime.scene.backgroundRotation.set(0, environmentSettings.rotationY, 0);
        }
      } else {
        applyActiveSceneBackground(runtime, viewerTheme, normalizedThemeSettings.background);
      }
      runtime.requestRender();
    };

    loadAndApplyEnvironment().catch((error) => {
      if (!cancelled) {
        applyBackgroundFallback();
        viewerAlertChangeRef.current?.({
          severity: "warning",
          summary: "Environment unavailable",
          title: "Environment preset could not be loaded",
          message: `Failed to load ${String(getEnvironmentPresetById(environmentSettings.presetId)?.label || "the selected environment preset")}.`,
          resolution: "The viewer fell back to the current background settings. Check the network connection or choose another preset."
        });
        console.error("Failed to apply environment texture", error);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [implicitActive, viewerReadyTick, viewerTheme, normalizedThemeSettings.background, normalizedThemeSettings.environment]);

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
    runtime.previewOrbitEnabled = !!previewMode;
    runtime.orbitControlsLastTimestamp = 0;
    runtime.controls.autoRotate = !!previewMode;
    runtime.controls.autoRotateSpeed = PREVIEW_AUTO_ROTATE_SPEED;
    runtime.controls.enabled = true;
    runtime.controls.enableDamping = true;
    runtime.controls.dampingFactor = DEFAULT_DAMPING_FACTOR;
    if (previewMode) {
      cancelCameraTransition(runtime, { scheduleIdle: false });
      runtime.beginInteraction?.();
    } else {
      runtime.scheduleIdleQuality();
    }
    runtime.requestRender();
  }, [previewMode, viewerReadyTick]);

  const urdfPosePickerInteractionActive = Boolean(urdfPosePicker?.active && !previewMode);
  const urdfPosePickerCursor = urdfPosePickerInteractionActive
    ? (urdfPosePickerHoverActive ? "pointer" : "crosshair")
    : undefined;

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!urdfPosePicker?.active || !runtime?.controls) {
      return;
    }
    runtime.controls.enabled = true;
    runtime.controls.enableDamping = true;
    runtime.controls.dampingFactor = DEFAULT_DAMPING_FACTOR;
    runtime.requestRender();
  }, [urdfPosePicker?.active, viewerReadyTick]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    const canvas = runtime?.renderer?.domElement;
    if (!urdfPosePickerInteractionActive || !canvas) {
      return;
    }
    const handleCanvasPointerMove = (event) => {
      updateUrdfPosePickerHoverFromPointer(event);
    };
    const handleCanvasPointerLeave = () => {
      handlePosePickerPointerLeave();
    };
    canvas.addEventListener("pointermove", handleCanvasPointerMove, { passive: true });
    canvas.addEventListener("pointerleave", handleCanvasPointerLeave);
    return () => {
      canvas.removeEventListener("pointermove", handleCanvasPointerMove);
      canvas.removeEventListener("pointerleave", handleCanvasPointerLeave);
    };
  }, [urdfPosePickerInteractionActive, viewerReadyTick]);

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

    const clearDisplayedModel = ({ preserveModelIdentity = false } = {}) => {
      cancelCameraTransition(runtime);
      runtime.cadScene?.dispose?.();
      runtime.cadScene = null;
      clearSceneGroup(runtime.stageGroup);
      clearSceneGroup(modelGroup);
      clearSceneGroup(edgesGroup);
      clearSceneGroup(facePickGroup);
      clearSceneGroup(edgePickGroup);
      clearSceneGroup(vertexPickGroup);
      runtime.facePickMesh = null;
      runtime.edgePickLines = null;
      runtime.vertexPickPoints = null;
      runtime.edgePickObjects = [];
      runtime.topologyDisplayEdgeLine = null;
      runtime.topologyDisplayEdgeTransformByRecord = false;
      runtime.displayRecords = [];
      if (!preserveModelIdentity) {
        runtime.hasVisibleModel = false;
        runtime.activeModelKey = "";
      }
      runtime.requestRender();
    };

    // An implicit never has mesh data — the raymarch pass is its geometry. Drop
    // whatever mesh was on screen before, but leave the runtime's model identity
    // to the implicit arm: clearing activeModelKey here would make
    // emitPerspectiveChange treat every camera move as belonging to a stale
    // model and silently stop persisting the view.
    if (implicitActive) {
      clearDisplayedModel({ preserveModelIdentity: true });
      return;
    }

    if (isLoading) {
      clearDisplayedModel();
      setError("");
      return;
    }

    if (!meshData || !isNumericArray(meshData.vertices, 3) || !isNumericArray(meshData.indices, 3)) {
      clearDisplayedModel();
      return;
    }

    clearDisplayedModel();

    const { controls } = runtime;
    const hasFillRotation = normalizedThemeSettings.materials.cycleColors === true &&
      Array.isArray(normalizedThemeSettings.materials.fillColors) &&
      normalizedThemeSettings.materials.fillColors.length > 1;
    const shouldRenderFillParts = hasFillRotation &&
      Array.isArray(meshData?.parts) &&
      meshData.parts.length > 0;
    const shouldRenderSourceColorParts =
      !wireframeMode &&
      normalizedThemeSettings.materials?.overrideSourceColors !== true &&
      meshNeedsPartRenderingForSourceColors(meshData);
    const shouldRenderParts =
      effectiveRenderPartsIndividually ||
      shouldRenderFillParts ||
      shouldRenderSourceColorParts ||
      Array.isArray(pickableParts) &&
      pickableParts.length > 0 &&
      (
        pickMode === VIEWER_PICK_MODE.PARTS ||
        pickMode === VIEWER_PICK_MODE.ASSEMBLY ||
        pickMode === VIEWER_PICK_MODE.AUTO
      );
    const renderedParts = effectiveRenderPartsIndividually
      ? (Array.isArray(meshData?.parts) ? meshData.parts : [])
      : shouldRenderFillParts || shouldRenderSourceColorParts
        ? meshData.parts
        : pickableParts;
    const materialSettings = {
      ...normalizedThemeSettings.materials,
      envMapIntensity: normalizedThemeSettings.materials.envMapIntensity * (
        normalizedThemeSettings.environment.enabled ? normalizedThemeSettings.environment.intensity : 0
      )
    };
    const modelStepParameters = stepParameterRuntime?.definition
      ? {
          ...stepParameterRuntime,
          selectorRuntime
        }
      : null;

    const sceneTheme = wireframeMode
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
    const cadScene = buildModel(THREE, meshData, {
      theme: sceneTheme,
      displayMode: normalizedDisplayMode,
      applyDisplayModeEdgePolicy: !topologyDisplayEdgesVisible,
      scale: normalizedSceneScaleMode,
      baseTheme: viewerTheme,
      materialSettings,
      recomputeNormals,
      silhouette: topologyDisplayEdgesVisible && displayEdgeSettings.silhouette === true,
      parts: shouldRenderParts ? renderedParts : [],
      renderPartsIndividually: effectiveRenderPartsIndividually,
      stepParameters: modelStepParameters,
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
      }
    });
    modelGroup.add(cadScene.modelGroup);
    edgesGroup.add(cadScene.edgesGroup);
    runtime.cadScene = cadScene;
    runtime.displayRecords = cadScene.displayRecords;
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
    // meshData.bounds is the model at rest; displayBounds may be a posed
    // (animated or exploded) superset of it.
    runtime.zoomBaseModelRadius = boundsModelRadius(THREE, meshData.bounds, normalizedSceneScaleMode);
    const boundsMin = Array.isArray(displayBounds?.min) ? displayBounds.min : [0, 0, 0];
    const boundsMax = Array.isArray(displayBounds?.max) ? displayBounds.max : [0, 0, 0];
    const center = new THREE.Vector3(
      (toNumber(boundsMin[0]) + toNumber(boundsMax[0])) / 2,
      (toNumber(boundsMin[1]) + toNumber(boundsMax[1])) / 2,
      (toNumber(boundsMin[2]) + toNumber(boundsMax[2])) / 2
    );
    const previousTransform = modelTransformRef.current;
    if (
      previousTransform.modelKey !== modelKey ||
      previousTransform.sceneScaleMode !== normalizedSceneScaleMode ||
      !previousTransform.offset
    ) {
      previousTransform.modelKey = modelKey || "";
      previousTransform.sceneScaleMode = normalizedSceneScaleMode;
      previousTransform.offset = new THREE.Vector3(-center.x, -center.y, -center.z);
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
    const { radius } = applyRuntimeModelBounds(THREE, runtime, displayBounds, normalizedSceneScaleMode);
    syncRuntimeScaledLightingAndShadow(
      THREE,
      runtime,
      normalizedThemeSettings.lighting,
      radius,
      displayBounds,
      normalizedSceneScaleMode
    );
    updateActiveGridHelper(
      runtime,
      viewerTheme,
      radius,
      floorZ,
      normalizedSceneScaleMode,
      resolvedFloorMode
    );
    updateSpotLightTarget(runtime);
    updateStageEffects(runtime, viewerTheme, normalizedThemeSettings, radius, runtime.gridFloorZ ?? 0, resolvedFloorMode, normalizedSceneScaleMode);

    modelGroup.position.copy(modelOffset);
    edgesGroup.position.copy(modelOffset);
    facePickGroup.position.copy(modelOffset);
    edgePickGroup.position.copy(modelOffset);
    vertexPickGroup.position.copy(modelOffset);
    facePickGroup.updateMatrixWorld(true);
    edgePickGroup.updateMatrixWorld(true);
    vertexPickGroup.updateMatrixWorld(true);
    syncSelectorPickGroups(runtime, displaySelectorRuntime, modelOffset, { clearSceneGroup });
    scheduleRuntimeRaycastBvh(runtime);
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
    modelGroup.updateMatrixWorld(true);
    edgesGroup.updateMatrixWorld(true);

    syncRuntimeCameraClipPlanes(runtime, Math.max(radius / 1200, 0.01), Math.max(radius * 600, 2000));
    applyCameraFrameInsets(runtime, viewportFrameInsetsRef.current, { updateProjection: false });
    controls.minDistance = Math.max(radius / 2200, 0.02);
    controls.maxDistance = Math.max(radius * 140, 50);
    controls.zoomSpeed = DEFAULT_ZOOM_SPEED;
    runtime.edgePickThreshold = Math.max(radius / 320, 0.65);

    if (framedModelKeyRef.current !== (modelKey || "")) {
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
        if (
          !nextPerspectiveMatchesScene ||
          !applyPerspectiveSnapshot(runtime, nextPerspective, { scheduleIdle: false })
        ) {
          cancelCameraTransition(runtime);
          const frameMetrics = getViewportFrameMetrics(runtime, viewportFrameInsetsRef.current);
          const camera = runtime.camera;
          const fitDistance = frameRuntimeCameraForBoundingSphere(runtime, radius, normalizedSceneScaleMode, frameMetrics);
          const viewDirection = new THREE.Vector3(...DEFAULT_VIEW_DIRECTION).normalize();
          camera.zoom = 1;
          camera.up.set(...WORLD_UP);
          frameRuntimeCameraForBoundingSphere(runtime, radius, normalizedSceneScaleMode, frameMetrics);
          applyCameraFrameInsets(runtime, viewportFrameInsetsRef.current, { updateProjection: false });
          camera.position.copy(viewDirection.multiplyScalar(fitDistance));
          controls.target.set(0, 0, 0);
          camera.lookAt(controls.target);
          controls.update();
          runtime.requestRender();
        }
      });
      // The initial framing fits displayBounds, so that is the radius the
      // baseline is measured against.
      runtime.zoomFitModelRadius = radius;
      resetRuntimeZoomBaseline(runtime);
      syncCameraZoomPercent(runtime);
      framedModelKeyRef.current = modelKey || "";
      lastEmittedPerspectiveRef.current = readScopedPerspectiveSnapshot(runtime, {
        modelKey,
        sceneScaleMode: normalizedSceneScaleMode
      });
    }

    setError("");
    runtime.requestRender();
  }, [
    meshGeometrySource,
    modelKey,
    perspective,
    perspectiveRef,
    displayEdgesVisible,
    surfaceStepEdgesVisible,
    topologyDisplayEdgesVisible,
    recomputeNormals,
    implicitActive,
    isLoading,
    viewerReadyTick,
    pickMode,
    effectiveRenderPartsIndividually,
    explodedViewActive,
    pickableParts,
    selectorRuntime,
    displayEdgeRuntime,
    normalizedDisplayMode,
    normalizedSceneScaleMode,
    resolvedFloorMode,
    floorFollowsModel,
    viewerTheme,
    normalizedThemeSettings.lighting,
    normalizedThemeSettings.materials,
    normalizedThemeSettings.environment,
    displayEdgeSettings,
    hiddenAwareVisualEdgeSettings,
    visualEdgeSettings,
    syncCameraZoomPercent,
    wireframeEdgeColor,
    updateActiveGridHelper
  ]);

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

    const partsById = new Map(
      meshData.parts.map((part) => [String(part?.id || ""), part]).filter(([partId]) => partId)
    );
    let updated = false;
    for (const record of runtime.displayRecords) {
      const part = partsById.get(String(record?.partId || ""));
      if (!part) {
        continue;
      }
      record.baseTransform = displayTransformForPart(meshData, part, effectiveRenderPartsIndividually);
      record.partBounds = part.bounds;
      record.partCenter = readBoundsCenter(runtime.THREE, part.bounds);
      applyDisplayRecordTransform(runtime.THREE, record, runtime.modelRadius || 1);
      updated = true;
    }

    if (!updated) {
      return;
    }

    const { radius } = applyRuntimeModelBounds(runtime.THREE, runtime, meshData.bounds, normalizedSceneScaleMode);
    syncRuntimeScaledLightingAndShadow(
      runtime.THREE,
      runtime,
      normalizedThemeSettings.lighting,
      radius,
      meshData.bounds,
      normalizedSceneScaleMode
    );
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
    updateActiveGridHelper(
      runtime,
      viewerTheme,
      radius,
      floorZ,
      normalizedSceneScaleMode,
      resolvedFloorMode
    );
    updateSpotLightTarget(runtime);
    updateStageEffects(runtime, viewerTheme, normalizedThemeSettings, radius, runtime.gridFloorZ ?? 0, resolvedFloorMode, normalizedSceneScaleMode);
    runtime.requestRender();
  }, [
    meshData?.parts,
    meshData?.bounds,
    isLoading,
    effectiveRenderPartsIndividually,
    normalizedSceneScaleMode,
    normalizedThemeSettings,
    resolvedFloorMode,
    floorFollowsModel,
    viewerTheme,
    viewerReadyTick,
    updateActiveGridHelper
  ]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return;
    }

    applyPartVisualState(runtime.THREE, runtime.displayRecords, partVisualStateRef.current);
    runtime.requestRender();
  }, [viewerReadyTick, partVisualStateEnabled, recordEdgesVisible, focusedPartIds, hiddenPartIds, hoveredPartId, pickMode, pickableParts, selectedPartIds, viewerTheme, visualEdgeSettings, normalizedDisplayMode]);

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
    if (!definition || isLoading || !meshData) {
      stepModuleTransformDetectedChangeRef.current?.(false);
      updateTransformedRuntimeState(setTransformedSelectorRuntime, null);
      updateTransformedRuntimeState(setTransformedDisplayEdgeRuntime, null);
      runtime.topologyDisplayEdgeTransformByRecord = explodedViewActive;
      resetStepModuleRecordEffects(runtime.displayRecords);
      for (const record of runtime.displayRecords) {
        applyDisplayRecordTransform(runtime.THREE, record, runtime.modelRadius || 1);
      }
      applyPartVisualState(runtime.THREE, runtime.displayRecords, partVisualStateRef.current);
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
      runtime.requestRender?.();
      return;
    }

    let transformDetected = false;
    const features = resolveStepModuleFeatures(definition, {
      meshData,
      selectorRuntime: selectorRuntimeRef.current
    });
    const effectsByPartId = new Map();
    const effects = createStepModuleEffectsApi(runtime.THREE, {
      meshData,
      features,
      runtime,
      effectsByPartId,
      onTransformEffect: () => {
        transformDetected = true;
      }
    });
    const ctx = buildStepModuleContext({
      runtime,
      stepModuleRuntime: stepParameterRuntime,
      features,
      effects,
      cleanup: (cleanup) => {
        if (typeof cleanup === "function") {
          stepModuleCleanupRef.current.push(cleanup);
        }
      }
    });

    try {
      module?.update?.(ctx);
      module?.render?.(ctx);
    } catch (error) {
      viewerAlertChangeRef.current?.({
        severity: "warning",
        compact: true,
        title: "STEP parameter update failed",
        message: error instanceof Error ? error.message : String(error)
      });
      console.error("STEP parameter update failed", error);
    }

    applyStepModuleEffectsToRecords(runtime.THREE, runtime.displayRecords, effectsByPartId);
    const useRecordTopologyEdgeTransforms = explodedViewActive || shouldUseRecordTopologyEdgeTransforms({
      transformDetected,
      topologyDisplayEdgesVisible,
      displayEdgeRuntime,
      displayRecords: runtime.displayRecords
    });
    const nextEdgeRuntimes = resolveTopologyDisplayEdgeRuntimes({
      selectorRuntime,
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
    updateTransformedRuntimeState(setTransformedSelectorRuntime, nextSelectorRuntime ? {
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
    applyPartVisualState(runtime.THREE, runtime.displayRecords, partVisualStateRef.current);
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
    if (!stepAnimationPlaying) {
      syncDisplayMeshFaceIds(runtime, meshData, effectiveRuntime);
      syncSelectorPickGroups(runtime, effectiveRuntime, modelTransformRef.current.offset, { clearSceneGroup });
    }
    runtime.requestRender?.();
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
    stepParameterRuntime
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
      clearExplodedViewRecords(runtime.displayRecords);
      for (const record of runtime.displayRecords) {
        applyDisplayRecordTransform(THREE, record);
      }
      syncRecordTopologyDisplayEdgeTransforms(runtime, runtime.displayRecords);
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
    if (!runtime.surfaceLineGroup || runtime.surfaceLineGroup.parent !== edgesGroup) {
      runtime.surfaceLineGroup = new THREE.Group();
      runtime.surfaceLineGroup.renderOrder = 21;
      edgesGroup.add(runtime.surfaceLineGroup);
    }
    const lineGroup = runtime.surfaceLineGroup;
    clearOverlayGroup(runtime, lineGroup);

    const surfaceLineStrokes = (Array.isArray(drawingStrokes) ? drawingStrokes : []).filter(isSurfaceLineStroke);
    if (!surfaceLineStrokes.length) {
      return () => {
        clearOverlayGroup(runtime, lineGroup);
      };
    }

    const lineWidth = Math.max(getEdgeThickness(displayEdgeSettings, viewerTheme) * 1.6, 1.8);
    const lineOffset = Math.max(runtime.modelRadius || 0, 1) * 0.0008 + 0.02;
    for (const stroke of surfaceLineStrokes) {
      const surfaceLine = stroke?.surfaceLine;
      const referenceId = String(surfaceLine?.referenceId || "").trim();
      const reference = pickableReferenceMap.get(referenceId) || activeSelectorRuntime?.referenceMap?.get(referenceId) || null;
      if (!reference) {
        continue;
      }
      const linePositions = buildSurfaceLinePositions(reference, surfaceLine, {
        offset: lineOffset
      });
      if (!linePositions.length) {
        continue;
      }
      const line = createScreenSpaceLineSegments(runtime, linePositions, {
        color: SURFACE_LINE_COLOR,
        opacity: 0.98,
        lineWidth,
        renderOrder: 22,
        depthTest: true,
        depthWrite: false
      });
      if (line) {
        lineGroup.add(line);
      }
    }
    lineGroup.visible = lineGroup.children.length > 0;
    runtime.requestRender();

    return () => {
      clearOverlayGroup(runtime, lineGroup);
    };
  }, [activeSelectorRuntime, drawingStrokes, displayEdgeSettings, pickableReferenceMap, viewerReadyTick, viewerTheme]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgesGroup) {
      return;
    }

    const { THREE, edgesGroup } = runtime;
    if (!runtime.bendGuideGroup || runtime.bendGuideGroup.parent !== edgesGroup) {
      runtime.bendGuideGroup = new THREE.Group();
      runtime.bendGuideGroup.renderOrder = 15;
      edgesGroup.add(runtime.bendGuideGroup);
    }
    const bendGuideGroup = runtime.bendGuideGroup;
    clearOverlayGroup(runtime, bendGuideGroup);

    if (isLoading || !meshData || !isNumericArray(meshData.guide_line_segments, 6)) {
      return () => {
        clearOverlayGroup(runtime, bendGuideGroup);
      };
    }

    const bendGuideLine = createScreenSpaceLineSegments(runtime, meshData.guide_line_segments, {
      color: BEND_GUIDE_COLOR,
      opacity: 0.98,
      lineWidth: Math.max(getEdgeThickness(displayEdgeSettings, viewerTheme) * BEND_GUIDE_WIDTH_MULTIPLIER, 1.4),
      renderOrder: 16,
      depthTest: false,
      depthWrite: false
    });
    if (bendGuideLine) {
      bendGuideGroup.add(bendGuideLine);
    }
    bendGuideGroup.visible = bendGuideGroup.children.length > 0;
    runtime.requestRender();

    return () => {
      clearOverlayGroup(runtime, bendGuideGroup);
    };
  }, [isLoading, meshData, modelKey, displayEdgeSettings, viewerReadyTick, viewerTheme]);

  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.edgesGroup) {
      return;
    }

    const { THREE, edgesGroup } = runtime;
    if (!runtime.urdfPosePickerGuideGroup || runtime.urdfPosePickerGuideGroup.parent !== edgesGroup) {
      runtime.urdfPosePickerGuideGroup = new THREE.Group();
      runtime.urdfPosePickerGuideGroup.renderOrder = 28;
      edgesGroup.add(runtime.urdfPosePickerGuideGroup);
    }
    const guideGroup = runtime.urdfPosePickerGuideGroup;
    clearOverlayGroup(runtime, guideGroup);

    if (!urdfPosePicker?.active) {
      return () => {
        clearOverlayGroup(runtime, guideGroup);
      };
    }

    const shell = resolveUrdfPosePickerShell(runtime, urdfPosePicker);
    if (!shell) {
      return () => {
        clearOverlayGroup(runtime, guideGroup);
      };
    }

    const shellMesh = createUrdfPosePickerShell(runtime, urdfPosePicker);
    if (shellMesh) {
      guideGroup.add(shellMesh);
    }
    const hoverCellMesh = createUrdfPosePickerHoverCellMesh(runtime, urdfPosePicker);
    if (hoverCellMesh) {
      guideGroup.add(hoverCellMesh);
    }
    const hoverCellOutline = createUrdfPosePickerHoverCellOutline(runtime, urdfPosePicker);
    if (hoverCellOutline) {
      guideGroup.add(hoverCellOutline);
    }
    guideGroup.visible = guideGroup.children.length > 0;
    runtime.requestRender();

    return () => {
      clearOverlayGroup(runtime, guideGroup);
    };
  }, [
    urdfPosePicker?.active,
    urdfPosePicker?.center,
    urdfPosePickerGuidePoint,
    urdfPosePickerHoverActive,
    viewerReadyTick
  ]);

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
    if (!runtime?.THREE || !runtime?.edgesGroup) {
      return;
    }

    const { THREE, edgesGroup } = runtime;
    if (!runtime.mateOverlayGroup || runtime.mateOverlayGroup.parent !== edgesGroup) {
      runtime.mateOverlayGroup = new THREE.Group();
      runtime.mateOverlayGroup.renderOrder = 27;
      edgesGroup.add(runtime.mateOverlayGroup);
    }
    const mateOverlayGroup = runtime.mateOverlayGroup;
    clearOverlayGroup(runtime, mateOverlayGroup);

    if (isLoading || !meshData) {
      return () => {
        clearOverlayGroup(runtime, mateOverlayGroup);
      };
    }

    const activeMates = resolveActiveMateOverlays(assemblyMates, selectedMateIds, hoveredMateId);
    if (!activeMates.length) {
      return () => {
        clearOverlayGroup(runtime, mateOverlayGroup);
      };
    }

    const modelRadius = Number.isFinite(Number(runtime.modelRadius)) && Number(runtime.modelRadius) > 0
      ? Number(runtime.modelRadius)
      : 1;
    const highlightColor = getHighlightEdgeColor(displayEdgeSettings);
    const highlightOpacity = getHighlightEdgeOpacity(displayEdgeSettings);
    const markerRadius = clamp(modelRadius * 0.012, 0.55, 4.5);
    const axisLength = clamp(modelRadius * 0.07, markerRadius * 3.2, 18);
    const baseLineWidth = Math.max(getHighlightEdgeThickness(displayEdgeSettings, viewerTheme), 2.6);

    for (const mate of activeMates) {
      addMateOverlayGlyph(runtime, mateOverlayGroup, mate, {
        color: highlightColor,
        opacity: mate.selected ? highlightOpacity : Math.min(highlightOpacity, 0.82),
        markerRadius: mate.hovered && !mate.selected ? markerRadius * 0.9 : markerRadius,
        axisLength,
        lineWidth: mate.selected ? baseLineWidth : Math.max(baseLineWidth * 0.86, 2.2),
        renderOrder: mate.selected ? 28 : 27
      });
    }

    mateOverlayGroup.visible = mateOverlayGroup.children.length > 0;
    runtime.requestRender();

    return () => {
      clearOverlayGroup(runtime, mateOverlayGroup);
    };
  }, [
    assemblyMates,
    displayEdgeSettings,
    hoveredMateId,
    isLoading,
    meshData,
    modelKey,
    selectedMateIds,
    viewerReadyTick,
    viewerTheme
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
          opacity: highlightEdgeOpacity,
          lineWidth,
          renderOrder: 26,
          depthTest: selectorType !== "edge",
          depthWrite: false,
          depthBias: topologyLineDepthBiasForWidth(lineWidth, { visibilityClass: referenceVisibilityClass })
        });
        if (line) {
          highlightGroup.add(line);
        }
      }

      if (selectorType === "face") {
        const fillGeometry = buildFaceFillGeometryFromDisplayMeshes(runtime, THREE, topologyReference) ||
          buildFaceFillGeometryFromProxy(runtime, THREE, activeSelectorRuntime, topologyReference);
        if (fillGeometry) {
          const fillOpacity = highlightEdgeOpacity;
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
  }, [activeSelectorRuntime, hoveredReferenceId, pickableReferenceMap, selectedReferenceIds, viewerReadyTick, viewerTheme, displayEdgeSettings]);

  useViewerDrawingOverlay({
    drawingCanvasRef,
    drawingDraftRef,
    drawingStrokesRef,
    drawingChangeRef,
    drawingIdRef,
    drawingEnabled,
    drawingTool,
    meshData: viewportContent,
    previewMode,
    viewerReadyTick,
    renderDrawingOverlay,
    redrawDrawingCanvas,
    buildDrawingPoint,
    distanceToStrokeInPixels,
    strokeLengthInPixels,
    drawingToolNeedsTwoPoints,
    buildFillStrokeAtPoint,
    buildSurfaceLineAnchor: buildSurfaceLineFaceAnchor,
    updateSurfaceLineAnchor: updateSurfaceLineFaceAnchor,
    drawingEraseThresholdPx: DRAWING_ERASE_THRESHOLD_PX,
    drawingMinPointDistancePx: DRAWING_MIN_POINT_DISTANCE_PX,
    drawingMinStrokeLengthPx: DRAWING_MIN_STROKE_LENGTH_PX
  });

  useViewerPicking({
    runtimeRef,
    mountRef: interactionHostRef,
    sceneMountRef: mountRef,
    drawingCanvasRef,
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
    viewerReadyTick,
    suppressTopologyPicking: stepAnimationPlaying
  });

  return (
    <div
      ref={interactionHostRef}
      className="relative h-full w-full"
      style={urdfPosePickerCursor ? { cursor: urdfPosePickerCursor } : undefined}
      onPointerDownCapture={handlePosePickerPointerDown}
      onPointerMoveCapture={handlePosePickerPointerMove}
      onPointerUpCapture={handlePosePickerPointerUp}
      onPointerCancelCapture={handlePosePickerPointerCancel}
      onPointerLeave={handlePosePickerPointerLeave}
    >
      <div className="h-full w-full" ref={mountRef} />
      <canvas
        ref={drawingCanvasRef}
        className="absolute inset-0 z-10 h-full w-full touch-none"
        style={{
          pointerEvents: drawingEnabled && !previewMode && hasViewportContent ? "auto" : "none",
          cursor: drawingEnabled && !previewMode && hasViewportContent
            ? (drawingTool === DRAWING_TOOL.ERASE ? "cell" : drawingTool === DRAWING_TOOL.FILL ? "copy" : "crosshair")
            : "default"
        }}
        aria-hidden="true"
      />
      <ViewPlaneControl
        showViewPlane={showViewPlane && !planMode}
        previewMode={previewMode}
        isLoading={isLoading}
        // "Is there anything on screen?" — for an implicit that is the loaded
        // model, since it never has mesh data.
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
        <p className="cad-glass-popover pointer-events-none absolute left-4 top-24 z-20 rounded-[10px] border border-[var(--ui-error-bg)] px-4 py-3 text-sm text-[var(--ui-error-text)] shadow-[var(--ui-shadow-soft)] sm:top-20">
          {error}
        </p>
      ) : null}
    </div>
  );
});

export default CadViewer;

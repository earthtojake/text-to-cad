// The camera of a viewport runtime: zoom percent against the authored framing,
// projection and lens sync, serializable perspective snapshots, eased
// transitions, fit-to-bounds and recentring. Every function takes the runtime
// (`{ THREE, camera, perspectiveCamera, orthographicCamera, controls, renderer,
// modelGroup, requestRender, scheduleIdleQuality, ... }`) and plain bounds
// (`{ min: [x, y, z], max: [x, y, z] }`); none reads what is being shown.

import {
  clamp,
  runtimeFramingBounds,
  clearKeyboardOrbitState,
  DEFAULT_VIEW_DIRECTION,
  viewportFitScale,
  easeInOutCubic,
  VIEW_PLANE_TRANSITION_MS,
  WORLD_UP,
  viewPlaneCameraBasis
} from "./viewportCameraKit.js";
import {
  clampSceneModelRadius,
  getSceneScaleSettings
} from "@hardcore/core/lib/viewer/sceneScale.js";
import {
  toNumber
} from "@hardcore/core/lib/viewer/modelRuntime.js";
import {
  originalModelCameraFrame,
  interactiveViewportFitScale,
  interactiveCameraFrameForBounds
} from "./viewportCameraFit.js";
import {
  normalizeCameraProjection,
  CAMERA_PROJECTION,
  clonePerspectiveSnapshot
} from "@hardcore/core/lib/perspective.js";
import {
  mergeBoundsList
} from "@hardcore/core/lib/viewer/autoZoom.js";
import {
  annotatePerspectiveSnapshot
} from "@hardcore/core/lib/perspective.js";

export const DEFAULT_DAMPING_FACTOR = 0.14;

export const CAMERA_TRANSITION_EASING = Object.freeze({
  EASE_IN_OUT_CUBIC: "ease-in-out-cubic",
  EASE_IN_OUT_SINE: "ease-in-out-sine"
});

export const ZOOM_CONTROL_MIN_PERCENT = 10;

export const ZOOM_CONTROL_MAX_PERCENT = 800;

export function normalizeZoomPercent(value, fallback = 100) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return fallback;
  }
  return clamp(numeric, ZOOM_CONTROL_MIN_PERCENT, ZOOM_CONTROL_MAX_PERCENT);
}

export function formatZoomPercent(value) {
  return `${Math.round(normalizeZoomPercent(value))}%`;
}

export function readCameraTargetDistance(runtime) {
  if (!runtime?.camera?.position || !runtime?.controls?.target) {
    return null;
  }
  const distance = runtime.camera.position.distanceTo(runtime.controls.target);
  return Number.isFinite(distance) && distance > 1e-6 ? distance : null;
}

export function readOrthographicHalfHeight(runtime) {
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
export function boundsModelRadius(THREE, bounds, sceneScaleMode) {
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

// Recompute from authored geometry, never from the camera being reset. Both
// projections have their own baseline, independent of pose and scene effects.
export function resetRuntimeZoomBaseline(runtime) {
  const bounds = runtimeFramingBounds(runtime);
  if (!runtime?.camera || !runtime?.THREE || !bounds) return null;
  const frame = originalModelCameraFrame(runtime.THREE, {
    camera: runtime.camera, bounds, frameAspect: getViewportMetrics(runtime).aspect,
    minRadius: getSceneScaleSettings(runtime.sceneScaleMode).minModelRadius,
  });
  if (!frame) return null;
  runtime.zoomBaseHalfHeight = frame.halfHeight;
  runtime.zoomBaseDistance = frame.distance;
  return runtime.camera.isOrthographicCamera ? frame.halfHeight : frame.distance;
}

export function readRuntimeZoomPercent(runtime) {
  const camera = runtime?.camera;
  if (!camera) {
    return 100;
  }
  resetRuntimeZoomBaseline(runtime);
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

export function setRuntimeZoomPercent(runtime, percent) {
  if (!runtime?.THREE || !runtime?.camera || !runtime?.controls?.target) {
    return false;
  }
  resetRuntimeZoomBaseline(runtime);
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
  }
  camera.lookAt(runtime.controls.target);
  runtime.controls.update?.();
  runtime.scheduleIdleQuality?.();
  runtime.requestRender?.();
  return true;
}

// The canvas IS the viewport: it fills the box between the sidebar and the
// sheet and nothing else, so the camera frames and centres in the whole of it.
export function getViewportMetrics(runtime) {
  const canvas = runtime?.renderer?.domElement;
  const width = Math.max(1, canvas?.clientWidth || canvas?.parentElement?.clientWidth || 1);
  const height = Math.max(1, canvas?.clientHeight || canvas?.parentElement?.clientHeight || 1);
  return { width, height, aspect: width / height };
}

export function runtimeCameraProjection(runtime) {
  return normalizeCameraProjection(
    runtime?.projection || (runtime?.camera?.isOrthographicCamera ? CAMERA_PROJECTION.ORTHOGRAPHIC : CAMERA_PROJECTION.PERSPECTIVE)
  );
}

export function syncRuntimeCameraClipPlanes(runtime, near, far) {
  for (const camera of [runtime?.perspectiveCamera, runtime?.orthographicCamera].filter(Boolean)) {
    camera.near = near;
    camera.far = far;
    camera.updateProjectionMatrix?.();
  }
}

export function setOrthographicCameraHalfHeight(runtime, halfHeight, frameMetrics = null) {
  const camera = runtime?.orthographicCamera;
  if (!camera?.isOrthographicCamera) {
    return false;
  }
  const metrics = frameMetrics || getViewportMetrics(runtime);
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

export function runtimeViewportFitScale(runtime, frameMetrics) {
  const camera = runtime?.camera;
  const fitCamera = camera?.isPerspectiveCamera ? camera : runtime?.perspectiveCamera || camera;
  const projected = interactiveViewportFitScale(runtime.THREE, {
    camera, framing: runtime.interactiveFraming, aspect: frameMetrics?.aspect,
  });
  if (Number.isFinite(projected) && projected > 0) return projected;
  return viewportFitScale({
    orthographic: camera?.isOrthographicCamera === true,
    fov: Number(fitCamera?.fov) || 48,
    aspect: frameMetrics?.aspect
  });
}

// Record the viewport the camera is currently framed for. Anything that fits the
// camera afresh is by definition fitted to the viewport it ran in, so this is the
// reference the next viewport change measures against.
export function captureRuntimeViewportFitScale(runtime, frameMetrics = null) {
  if (!runtime?.camera) {
    return;
  }
  const metrics = frameMetrics || getViewportMetrics(runtime);
  runtime.viewportFitScale = runtimeViewportFitScale(runtime, metrics);
}

// A viewport change -- the window resizing, or a side sheet opening, closing or
// being dragged wider and resizing the canvas beside it -- leaves the camera
// framed for the viewport it no longer has. The vertical field of view is fixed and the orthographic half-height is
// held constant across an aspect change, so a narrowing viewport crops a wide
// model instead of shrinking it. Rescale the camera by the change in fit scale so
// the model keeps its share of the framed area.
//
// The zoom ruler is recalculated from the authored box in the new viewport.
// It cannot inherit a selection fit or the bounds of a moving assembly.
export function syncRuntimeViewportFraming(runtime, frameMetrics = null) {
  if (!runtime?.camera) {
    return false;
  }
  const metrics = frameMetrics || getViewportMetrics(runtime);
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
  resetRuntimeZoomBaseline(runtime);
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

export function syncRuntimeCameraProjection(runtime, projection, { scheduleIdle = true, requestRender = true } = {}) {
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
  const frameMetrics = getViewportMetrics(runtime);
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

export function easeInOutSine(t) {
  if (t <= 0) {
    return 0;
  }
  if (t >= 1) {
    return 1;
  }
  return -(Math.cos(Math.PI * t) - 1) / 2;
}

export function easeCameraTransitionProgress(t, easing = CAMERA_TRANSITION_EASING.EASE_IN_OUT_CUBIC) {
  return easing === CAMERA_TRANSITION_EASING.EASE_IN_OUT_SINE
    ? easeInOutSine(t)
    : easeInOutCubic(t);
}

export function readPerspectiveSnapshot(runtime) {
  if (!runtime?.camera || !runtime?.controls) {
    return null;
  }
  const orthographicHalfHeight = readOrthographicHalfHeight(runtime);
  return {
    position: [runtime.camera.position.x, runtime.camera.position.y, runtime.camera.position.z],
    target: [runtime.controls.target.x, runtime.controls.target.y, runtime.controls.target.z],
    up: [runtime.camera.up.x, runtime.camera.up.y, runtime.camera.up.z],
    zoom: runtime.camera.zoom,
    projection: runtimeCameraProjection(runtime),
    ...(Number.isFinite(runtime.perspectiveCamera?.getFocalLength?.())
      ? { focalLength: runtime.perspectiveCamera.getFocalLength() }
      : {}),
    ...(orthographicHalfHeight ? { orthographicHalfHeight } : {})
  };
}

export function setRuntimePerspectiveFocalLength(runtime, focalLength) {
  const camera = runtime?.perspectiveCamera;
  const next = Number(focalLength);
  if (!camera?.setFocalLength || !Number.isFinite(next) || next <= 0) {
    return false;
  }
  camera.setFocalLength(next);
  camera.userData.cadFocalLength = next;
  return true;
}

export function cancelCameraTransition(runtime, { scheduleIdle = true } = {}) {
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

export function applyPerspectiveSnapshot(runtime, perspective, { scheduleIdle = true } = {}) {
  const nextPerspective = clonePerspectiveSnapshot(perspective);
  if (!runtime?.camera || !runtime?.controls || !nextPerspective) {
    return false;
  }
  cancelCameraTransition(runtime, { scheduleIdle: false });
  clearKeyboardOrbitState(runtime.keyboardOrbitState);
  if (Object.prototype.hasOwnProperty.call(nextPerspective, "projection")) {
    syncRuntimeCameraProjection(runtime, nextPerspective.projection, { scheduleIdle: false });
  }
  if (Number.isFinite(nextPerspective.focalLength) && nextPerspective.focalLength > 0) {
    setRuntimePerspectiveFocalLength(runtime, nextPerspective.focalLength);
  }
  runtime.camera.position.set(...nextPerspective.position);
  runtime.controls.target.set(...nextPerspective.target);
  runtime.camera.up.set(...nextPerspective.up);
  if (
    Number.isFinite(nextPerspective.orthographicHalfHeight) &&
    nextPerspective.orthographicHalfHeight > 0
  ) {
    setOrthographicCameraHalfHeight(runtime, nextPerspective.orthographicHalfHeight);
  }
  if (Number.isFinite(nextPerspective.zoom) && nextPerspective.zoom > 0) {
    runtime.camera.zoom = nextPerspective.zoom;
    runtime.camera.updateProjectionMatrix?.();
  }
  runtime.camera.lookAt(runtime.controls.target);
  runtime.controls.update();
  if (scheduleIdle) {
    runtime.scheduleIdleQuality?.();
  }
  runtime.requestRender?.();
  return true;
}

export function transitionCameraToPerspectiveSnapshot(runtime, perspective, {
  durationMs = VIEW_PLANE_TRANSITION_MS,
  easing = CAMERA_TRANSITION_EASING.EASE_IN_OUT_CUBIC,
  orthographicHalfHeight = undefined,
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
  if (Number.isFinite(nextPerspective.focalLength) && nextPerspective.focalLength > 0) {
    setRuntimePerspectiveFocalLength(runtime, nextPerspective.focalLength);
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
    ? Number(orthographicHalfHeight ?? nextPerspective.orthographicHalfHeight)
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

// Aim the controls back at the model centre without touching orientation or
// distance. The model renders at its authored world coordinates (no bounds
// re-centering), so the target is the model's world bounds centre — the same
// target the initial framing uses — not the origin.
export function recenterRuntimeTarget(runtime) {
  const controls = runtime?.controls;
  const camera = runtime?.camera;
  if (!controls?.target || !camera || !runtime?.THREE) {
    return false;
  }
  const THREE = runtime.THREE;
  const bounds = runtimeFramingBounds(runtime);
  const boundsMin = Array.isArray(bounds?.min) ? bounds.min : [0, 0, 0];
  const boundsMax = Array.isArray(bounds?.max) ? bounds.max : [0, 0, 0];
  const worldCenter = new THREE.Vector3(
    (toNumber(boundsMin[0]) + toNumber(boundsMax[0])) / 2,
    (toNumber(boundsMin[1]) + toNumber(boundsMax[1])) / 2,
    (toNumber(boundsMin[2]) + toNumber(boundsMax[2])) / 2
  );
  if (runtime.modelGroup?.position) {
    worldCenter.add(runtime.modelGroup.position);
  }
  const offset = new THREE.Vector3().copy(camera.position).sub(controls.target);
  controls.target.copy(worldCenter);
  camera.position.copy(worldCenter).add(offset);
  camera.lookAt(controls.target);
  controls.update?.();
  return true;
}

export function zoomRuntimeToBounds(runtime, bounds, sceneScaleMode, {
  animate = true,
  modelOffset = null,
  resetZoomBaseline = false,
  originalModelScale = false,
  viewDirection = null,
  viewUp = null
} = {}) {
  if (!runtime?.THREE || !runtime?.camera || !runtime?.controls) {
    return false;
  }
  const normalizedBounds = mergeBoundsList([bounds]);
  if (!normalizedBounds) {
    return false;
  }
  const frameMetrics = getViewportMetrics(runtime);
  // Render adjusts its clipping range to the current pose every frame. A fit
  // must use the model's base range, or resetting after zooming out would fit
  // behind the old distant near plane instead of returning to the default view.
  // A physical lens changes vertical FOV with aspect. Fit using the destination
  // viewport before installing the pose, not the aspect before a panel opened or closed.
  runtime.syncCameraViewport?.(runtime.camera, frameMetrics.width, frameMetrics.height);
  const fitNearClip = Math.max(boundsModelRadius(runtime.THREE, normalizedBounds, sceneScaleMode) / 1200, 0.01);
  const frame = interactiveCameraFrameForBounds(runtime.THREE, {
    camera: runtime.camera,
    controls: runtime.controls,
    bounds: normalizedBounds,
    modelOffset,
    frameAspect: frameMetrics.aspect,
    minRadius: getSceneScaleSettings(sceneScaleMode).minModelRadius,
    nearClip: fitNearClip,
    viewDirection,
    viewUp: viewUp || runtime.camera.up?.toArray?.() || WORLD_UP
  });
  if (!frame) {
    return false;
  }
  // Cube shortcuts reset to the same 100% ruler the original model opened with.
  // Refitting each face would silently redefine that scale for a tall or flat part.
  if (originalModelScale) {
    const original = originalModelCameraFrame(runtime.THREE, {
      camera: runtime.camera, bounds: normalizedBounds, frameAspect: frameMetrics.aspect,
      minRadius: getSceneScaleSettings(sceneScaleMode).minModelRadius, modelOffset
    });
    if (original) {
      frame.halfHeight = original.halfHeight;
      frame.distance = original.distance;
      frame.position.copy(frame.target).addScaledVector(frame.direction, original.distance);
    }
  }
  runtime.interactiveFraming = {
    bounds: normalizedBounds, direction: originalModelScale ? [...DEFAULT_VIEW_DIRECTION] : frame.direction.toArray(), up: frame.up.toArray(),
    minRadius: getSceneScaleSettings(sceneScaleMode).minModelRadius,
    nearClip: fitNearClip,
  };
  captureRuntimeViewportFitScale(runtime, frameMetrics);
  const snapshot = {
    position: frame.position.toArray(),
    target: frame.target.toArray(),
    up: frame.up.toArray(),
    zoom: 1,
    projection: runtimeCameraProjection(runtime)
  };
  const orthographicHalfHeight = runtime.camera.isOrthographicCamera ? frame.halfHeight : null;

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
  if (applied && resetZoomBaseline) {
    resetRuntimeZoomBaseline(runtime);
  }
  return applied;
}

export function stepCameraTransition(runtime, timestamp) {
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
  if (
    runtime.camera?.isOrthographicCamera &&
    Number.isFinite(startOrthographicHalfHeight) &&
    Number.isFinite(endOrthographicHalfHeight) &&
    endOrthographicHalfHeight > 0
  ) {
    const nextHalfHeight = startOrthographicHalfHeight + ((endOrthographicHalfHeight - startOrthographicHalfHeight) * eased);
    setOrthographicCameraHalfHeight(runtime, nextHalfHeight);
  }
  if (Number.isFinite(transition.startZoom) && Number.isFinite(transition.endZoom)) {
    runtime.camera.zoom = transition.startZoom + ((transition.endZoom - transition.startZoom) * eased);
    runtime.camera.updateProjectionMatrix?.();
  }
  runtime.camera.lookAt(target);

  if (progress >= 1) {
    if (transition.resetZoomBaselineOnComplete) {
      resetRuntimeZoomBaseline(runtime);
    }
    runtime.cameraTransition = null;
    runtime.controls.enableDamping = true;
    runtime.controls.dampingFactor = DEFAULT_DAMPING_FACTOR;
    runtime.scheduleIdleQuality?.();
    return false;
  }
  return true;
}

export function transitionCameraToViewPreset(runtime, preset) {
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
  // The basis maths lives in viewportCameraKit so the "up is always world up" invariant is
  // testable without mounting a viewer. It returns world up for EVERY preset, so the orbit
  // axis is the same from any view.
  const basis = viewPlaneCameraBasis(preset, WORLD_UP);
  if (!basis) {
    return false;
  }
  const nextDirection = new runtime.THREE.Vector3(...basis.direction);
  const nextUp = new runtime.THREE.Vector3(...basis.up);
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

// The snapshot a session stores: the camera, scoped to the model, scale mode and
// coordinate system it was taken in, so it is only ever restored into the same.
export function readScopedPerspectiveSnapshot(runtime, { modelKey = "", sceneScaleMode = "", coordinateSystem = "" } = {}) {
  return annotatePerspectiveSnapshot(readPerspectiveSnapshot(runtime), {
    modelKey,
    sceneScaleMode,
    coordinateSystem
  });
}

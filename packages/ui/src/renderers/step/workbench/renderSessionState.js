import { resolveCameraSnapshot } from "@hardcore/core/common/camera.js";
import { clonePerspectiveSnapshot } from "@hardcore/core/lib/perspective.js";

// This slice records the viewport only. Preset, lens and scene configuration
// belong to display; no enabled flag or photographic payload can override it.
export function createRenderSessionState(value = null) {
  const oldCamera = value?.enabled === true ? value?.payload?.camera : null;
  return { cadCamera: renderCameraSnapshot(oldCamera || value?.cadCamera) };
}

export function renderSessionStateEqual(a, b) {
  return JSON.stringify(createRenderSessionState(a)) === JSON.stringify(createRenderSessionState(b));
}

export function renderCameraSnapshot(camera) {
  const snapshot = clonePerspectiveSnapshot(camera);
  if (!snapshot) {
    return null;
  }
  return {
    position: snapshot.position,
    target: snapshot.target,
    up: snapshot.up,
    ...(Object.prototype.hasOwnProperty.call(snapshot, "zoom") ? { zoom: snapshot.zoom } : {}),
    ...(Object.prototype.hasOwnProperty.call(snapshot, "projection") ? { projection: snapshot.projection } : {}),
    ...(Object.prototype.hasOwnProperty.call(snapshot, "focalLength") ? { focalLength: snapshot.focalLength } : {}),
    ...(Object.prototype.hasOwnProperty.call(snapshot, "orthographicHalfHeight")
      ? { orthographicHalfHeight: snapshot.orthographicHalfHeight }
      : {})
  };
}

export function resolveRenderCameraSnapshot(camera, bounds = null, { sceneScale = "cad" } = {}) {
  return renderCameraSnapshot(resolveCameraSnapshot(camera, bounds, { sceneScale }));
}

export function readRenderSessionCamera(viewer, fallback = null) {
  // Automatic framing can precede the first camera-change event. A mode switch
  // must preserve the actual viewport, including its orthographic frame size.
  return renderCameraSnapshot(viewer?.getPerspective?.()) || renderCameraSnapshot(fallback);
}

import {
  normalizeRenderPayload,
  resolveSceneSettings
} from "@hardcore/core/common/sceneSettings.js";
import {
  CAMERA_PROJECTION,
  normalizeCameraProjection,
  resolveCameraSnapshot
} from "@hardcore/core/common/camera.js";
import { clonePerspectiveSnapshot } from "@hardcore/core/lib/perspective.js";
import { CAD_DISPLAY_MODE } from "@hardcore/core/lib/displaySettings.js";

export const DEFAULT_RENDER_PAYLOAD = Object.freeze({ quality: "preview" });

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function cloneValue(value) {
  if (Array.isArray(value)) {
    return value.map(cloneValue);
  }
  if (isPlainObject(value)) {
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, cloneValue(child)]));
  }
  return value;
}

export function createRenderSessionState(value = null) {
  const source = isPlainObject(value) ? value : {};
  // Migrate old file sessions' mode-specific camera into the common camera.
  // This is user-state migration, not a snapshot CLI compatibility path.
  const oldPayload = isPlainObject(source.payload) ? source.payload : {};
  const { studio: _studio, camera: oldCamera, ...settings } = oldPayload;
  let payload;
  try { payload = normalizeRenderPayload({ ...DEFAULT_RENDER_PAYLOAD, ...settings }); }
  catch { payload = normalizeRenderPayload(DEFAULT_RENDER_PAYLOAD); }
  const camera = renderCameraSnapshot(source.enabled && oldCamera ? oldCamera : source.cadCamera);
  return {
    enabled: source.enabled === true,
    payload,
    cadCamera: camera,
    cadProjection: normalizeCameraProjection(camera?.projection || source.cadProjection,
      CAMERA_PROJECTION.ORTHOGRAPHIC)
  };
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

export function setRenderPayloadValue(payload, path, value) {
  const normalizedPayload = normalizeRenderPayload(payload || DEFAULT_RENDER_PAYLOAD);
  const normalizedPath = (Array.isArray(path) ? path : []).map((part) => String(part || "").trim()).filter(Boolean);
  if (!normalizedPath.length) {
    return normalizedPayload;
  }
  const nextPayload = cloneValue(normalizedPayload);
  let cursor = nextPayload;
  for (let index = 0; index < normalizedPath.length - 1; index += 1) {
    const part = normalizedPath[index];
    cursor[part] = isPlainObject(cursor[part]) ? { ...cursor[part] } : {};
    cursor = cursor[part];
  }
  cursor[normalizedPath[normalizedPath.length - 1]] = cloneValue(value);
  return normalizeRenderPayload(nextPayload);
}

export function resetRenderPayload() {
  return normalizeRenderPayload(DEFAULT_RENDER_PAYLOAD);
}

export function renderSessionForReset(session) {
  const current = createRenderSessionState(session);
  return createRenderSessionState({ ...current, payload: resetRenderPayload() });
}

export function renderSessionForEnabledChange(session, enabled, {
  activeCamera = null,
  activeProjection = null
} = {}) {
  const current = createRenderSessionState(session);
  const camera = renderCameraSnapshot(activeCamera) || current.cadCamera;
  return createRenderSessionState({
    ...current,
    enabled,
    cadCamera: camera,
    cadProjection: camera?.projection || activeProjection || current.cadProjection
  });
}

export function renderVisualPayload(payload) {
  const {
    camera: _camera,
    quality: _quality,
    ...visual
  } = normalizeRenderPayload(payload || DEFAULT_RENDER_PAYLOAD);
  return visual;
}

export function renderVisualSettingsKey(payload) {
  return JSON.stringify(renderVisualPayload(payload));
}

export function resolveRenderSessionQuality(session, options = {}) {
  const current = createRenderSessionState(session);
  return resolveSceneSettings({
    appearance: options.appearance,
    prefersDark: options.prefersDark === true,
    display: current.enabled ? {
      mode: CAD_DISPLAY_MODE.RENDER,
      render: { quality: current.payload.quality }
    } : null
  }).quality;
}

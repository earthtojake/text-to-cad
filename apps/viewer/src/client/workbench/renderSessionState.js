import {
  normalizeRenderPayload,
  resolveSceneSettings
} from "cadgen-js/common/sceneSettings.js";
import {
  CAMERA_PROJECTION,
  normalizeCameraProjection,
  resolveCameraSnapshot
} from "cadgen-js/common/camera.js";
import { clonePerspectiveSnapshot } from "cadgen-js/lib/perspective.js";
import { FILE_SHEET_SECTION_IDS, normalizeFileSheetOpenSectionIds } from "./fileSheetSections.js";

export const DEFAULT_RENDER_PAYLOAD = Object.freeze({});

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
  let payload;
  try {
    // Studio selection belongs to snapshot requests. Viewer defaults always use
    // global appearance; only explicit photographic customizations are stored.
    const { studio: _studio, ...settings } = isPlainObject(source.payload) ? source.payload : DEFAULT_RENDER_PAYLOAD;
    payload = normalizeRenderPayload(settings);
  } catch {
    payload = normalizeRenderPayload(DEFAULT_RENDER_PAYLOAD);
  }
  return {
    enabled: source.enabled === true,
    payload,
    openSectionIds: Array.isArray(source.openSectionIds)
      ? normalizeFileSheetOpenSectionIds(source.openSectionIds, [
          FILE_SHEET_SECTION_IDS.RENDER,
          FILE_SHEET_SECTION_IDS.MATERIALS,
          FILE_SHEET_SECTION_IDS.STEP_POSE,
          FILE_SHEET_SECTION_IDS.STEP_ANIMATION
        ])
      : [FILE_SHEET_SECTION_IDS.RENDER],
    cadCamera: renderCameraSnapshot(source.cadCamera),
    cadProjection: normalizeCameraProjection(
      source.cadProjection || source.cadCamera?.projection,
      CAMERA_PROJECTION.ORTHOGRAPHIC
    )
  };
}

export function renderSessionStateEqual(a, b) {
  return JSON.stringify(createRenderSessionState(a)) === JSON.stringify(createRenderSessionState(b));
}

export function renderCameraSeed(snapshot, {
  includeOrthographicFraming = true,
  includeFocalLength = true
} = {}) {
  const camera = clonePerspectiveSnapshot(snapshot);
  if (!camera) {
    return null;
  }
  return {
    position: camera.position,
    target: camera.target,
    up: camera.up,
    ...(Object.prototype.hasOwnProperty.call(camera, "zoom") ? { zoom: camera.zoom } : {}),
    ...(includeFocalLength && Object.prototype.hasOwnProperty.call(camera, "focalLength")
      ? { focalLength: camera.focalLength }
      : {}),
    ...(includeOrthographicFraming && Object.prototype.hasOwnProperty.call(camera, "orthographicHalfHeight")
      ? { orthographicHalfHeight: camera.orthographicHalfHeight }
      : {})
  };
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

export function resetRenderPayload(activeCamera = null) {
  const camera = renderCameraSnapshot(activeCamera);
  return normalizeRenderPayload({
    ...DEFAULT_RENDER_PAYLOAD,
    ...(camera ? { camera: renderCameraSeed(camera, { includeFocalLength: false }) } : {})
  });
}

export function renderSessionForReset(session, { activeCamera = null } = {}) {
  const current = createRenderSessionState(session);
  return createRenderSessionState({
    ...current,
    payload: resetRenderPayload(current.enabled ? activeCamera : null)
  });
}

export function renderSessionForEnabledChange(session, enabled, {
  activeCamera = null,
  activeProjection = null
} = {}) {
  const current = createRenderSessionState(session);
  if (enabled === current.enabled) {
    return current;
  }
  const camera = renderCameraSnapshot(activeCamera);
  if (enabled) {
    return createRenderSessionState({
      ...current,
      enabled: true,
      openSectionIds: [FILE_SHEET_SECTION_IDS.RENDER],
      cadCamera: camera || current.cadCamera,
      cadProjection: camera?.projection || activeProjection || current.cadProjection
    });
  }
  return createRenderSessionState({
    ...current,
    enabled: false,
    payload: camera
      ? {
          ...current.payload,
          camera: {
            ...renderCameraSeed(camera),
            projection: camera.projection || activeProjection
          }
        }
      : current.payload
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
    render: current.enabled
      ? (current.payload.quality ? { quality: current.payload.quality } : {})
      : null
  }).quality;
}

import {
  CAMERA_PROJECTION,
  cloneCameraVector,
  normalizeCameraProjection,
  normalizeCameraZoom,
  normalizeCameraFocalLength,
  normalizeOrthographicHalfHeight
} from "../common/camera.js";

export { CAMERA_PROJECTION, normalizeCameraProjection };

function normalizePerspectiveMetadataValue(value) {
  return String(value || "").trim();
}

export function clonePerspectiveVector(vector) {
  return cloneCameraVector(vector);
}

export function clonePerspectiveSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object") {
    return null;
  }
  const position = clonePerspectiveVector(snapshot.position);
  const target = clonePerspectiveVector(snapshot.target);
  const up = clonePerspectiveVector(snapshot.up);
  if (!position || !target || !up) {
    return null;
  }
  const clonedSnapshot = {
    position,
    target,
    up
  };
  if (Object.prototype.hasOwnProperty.call(snapshot, "zoom")) {
    clonedSnapshot.zoom = normalizeCameraZoom(snapshot.zoom, 1);
  }
  if (Object.prototype.hasOwnProperty.call(snapshot, "projection")) {
    clonedSnapshot.projection = normalizeCameraProjection(snapshot.projection);
  }
  if (Object.prototype.hasOwnProperty.call(snapshot, "focalLength")) {
    const focalLength = normalizeCameraFocalLength(snapshot.focalLength);
    if (focalLength != null) clonedSnapshot.focalLength = focalLength;
  }
  if (Object.prototype.hasOwnProperty.call(snapshot, "orthographicHalfHeight")) {
    const orthographicHalfHeight = normalizeOrthographicHalfHeight(snapshot.orthographicHalfHeight);
    if (orthographicHalfHeight != null) {
      clonedSnapshot.orthographicHalfHeight = orthographicHalfHeight;
    }
  }
  const modelKey = normalizePerspectiveMetadataValue(snapshot.modelKey);
  const sceneScaleMode = normalizePerspectiveMetadataValue(snapshot.sceneScaleMode);
  const coordinateSystem = normalizePerspectiveMetadataValue(snapshot.coordinateSystem);
  if (modelKey) {
    clonedSnapshot.modelKey = modelKey;
  }
  if (sceneScaleMode) {
    clonedSnapshot.sceneScaleMode = sceneScaleMode;
  }
  if (coordinateSystem) {
    clonedSnapshot.coordinateSystem = coordinateSystem;
  }
  return clonedSnapshot;
}

export function annotatePerspectiveSnapshot(snapshot, { modelKey = "", sceneScaleMode = "", coordinateSystem = "" } = {}) {
  const annotatedSnapshot = clonePerspectiveSnapshot(snapshot);
  if (!annotatedSnapshot) {
    return null;
  }
  const normalizedModelKey = normalizePerspectiveMetadataValue(modelKey);
  const normalizedSceneScaleMode = normalizePerspectiveMetadataValue(sceneScaleMode);
  const normalizedCoordinateSystem = normalizePerspectiveMetadataValue(coordinateSystem);
  if (normalizedModelKey) {
    annotatedSnapshot.modelKey = normalizedModelKey;
  }
  if (normalizedSceneScaleMode) {
    annotatedSnapshot.sceneScaleMode = normalizedSceneScaleMode;
  }
  if (normalizedCoordinateSystem) {
    annotatedSnapshot.coordinateSystem = normalizedCoordinateSystem;
  }
  return annotatedSnapshot;
}

export function resolvePerspectiveSnapshot(primary, fallback) {
  if (typeof primary !== "undefined") {
    return clonePerspectiveSnapshot(primary);
  }
  return clonePerspectiveSnapshot(fallback);
}

function perspectiveVectorEqual(a, b, epsilon = 1e-4) {
  if (a === b) {
    return true;
  }
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) {
    return false;
  }
  for (let index = 0; index < a.length; index += 1) {
    if (Math.abs((Number(a[index]) || 0) - (Number(b[index]) || 0)) > epsilon) {
      return false;
    }
  }
  return true;
}

export function perspectiveSnapshotEqual(a, b, epsilon = 1e-4) {
  if (a === b) {
    return true;
  }
  if (!a || !b) {
    return !a && !b;
  }
  const aOrthographicHalfHeight = normalizeOrthographicHalfHeight(a.orthographicHalfHeight);
  const bOrthographicHalfHeight = normalizeOrthographicHalfHeight(b.orthographicHalfHeight);
  const orthographicHalfHeightEqual = aOrthographicHalfHeight == null || bOrthographicHalfHeight == null
    ? aOrthographicHalfHeight == null && bOrthographicHalfHeight == null
    : Math.abs(aOrthographicHalfHeight - bOrthographicHalfHeight) <= epsilon;
  const aFocalLength = normalizeCameraFocalLength(a.focalLength);
  const bFocalLength = normalizeCameraFocalLength(b.focalLength);
  const focalLengthEqual = aFocalLength == null || bFocalLength == null
    ? aFocalLength == null && bFocalLength == null
    : Math.abs(aFocalLength - bFocalLength) <= epsilon;
  return (
    perspectiveVectorEqual(a.position, b.position, epsilon) &&
    perspectiveVectorEqual(a.target, b.target, epsilon) &&
    perspectiveVectorEqual(a.up, b.up, epsilon) &&
    Math.abs(normalizeCameraZoom(a.zoom, 1) - normalizeCameraZoom(b.zoom, 1)) <= epsilon &&
    normalizeCameraProjection(a.projection) === normalizeCameraProjection(b.projection) &&
    orthographicHalfHeightEqual &&
    focalLengthEqual &&
    normalizePerspectiveMetadataValue(a.modelKey) === normalizePerspectiveMetadataValue(b.modelKey) &&
    normalizePerspectiveMetadataValue(a.sceneScaleMode) === normalizePerspectiveMetadataValue(b.sceneScaleMode) &&
    normalizePerspectiveMetadataValue(a.coordinateSystem) === normalizePerspectiveMetadataValue(b.coordinateSystem)
  );
}

export function perspectiveSnapshotMatchesScene(snapshot, {
  modelKey = "",
  sceneScaleMode = "",
  coordinateSystem = "",
  requireModelKey = false,
  requireSceneScaleMode = false,
  requireCoordinateSystem = false
} = {}) {
  const normalizedSnapshot = clonePerspectiveSnapshot(snapshot);
  if (!normalizedSnapshot) {
    return false;
  }
  const normalizedModelKey = normalizePerspectiveMetadataValue(modelKey);
  if (requireModelKey && normalizedModelKey && normalizedSnapshot.modelKey !== normalizedModelKey) {
    return false;
  }
  if (normalizedModelKey && normalizedSnapshot.modelKey && normalizedSnapshot.modelKey !== normalizedModelKey) {
    return false;
  }
  const normalizedSceneScaleMode = normalizePerspectiveMetadataValue(sceneScaleMode);
  if (requireSceneScaleMode && normalizedSceneScaleMode && normalizedSnapshot.sceneScaleMode !== normalizedSceneScaleMode) {
    return false;
  }
  if (normalizedSceneScaleMode && normalizedSnapshot.sceneScaleMode && normalizedSnapshot.sceneScaleMode !== normalizedSceneScaleMode) {
    return false;
  }
  const normalizedCoordinateSystem = normalizePerspectiveMetadataValue(coordinateSystem);
  if (requireCoordinateSystem && normalizedCoordinateSystem && normalizedSnapshot.coordinateSystem !== normalizedCoordinateSystem) {
    return false;
  }
  if (normalizedCoordinateSystem && normalizedSnapshot.coordinateSystem && normalizedSnapshot.coordinateSystem !== normalizedCoordinateSystem) {
    return false;
  }
  return true;
}

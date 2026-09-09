export const DEFAULT_AUTO_ZOOM_PADDING = 1.04;

const EPSILON = 1e-6;

function toNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function normalizePartId(value) {
  return String(value || "").trim();
}

function partIdMatchesFilter(partId, filter) {
  const normalizedPartId = normalizePartId(partId);
  if (!filter?.size) {
    return true;
  }
  if (filter.has("__model__")) {
    return true;
  }
  if (!normalizedPartId) {
    return false;
  }
  for (const candidate of filter) {
    const normalizedCandidate = normalizePartId(
      String(candidate || "").startsWith("#")
        ? String(candidate || "").slice(1)
        : candidate
    );
    if (
      normalizedPartId === normalizedCandidate ||
      normalizedPartId.startsWith(`${normalizedCandidate}.`)
    ) {
      return true;
    }
  }
  return false;
}

function isNumericBounds(bounds) {
  return Array.isArray(bounds?.min) &&
    Array.isArray(bounds?.max) &&
    bounds.min.length >= 3 &&
    bounds.max.length >= 3;
}

function vectorComponents(value) {
  if (value?.isVector3) {
    return [value.x, value.y, value.z];
  }
  if (Array.isArray(value) || ArrayBuffer.isView(value)) {
    return [toNumber(value[0]), toNumber(value[1]), toNumber(value[2])];
  }
  return [0, 0, 0];
}

function normalizedVector(THREE, value) {
  if (!value) {
    return null;
  }
  const [x, y, z] = vectorComponents(value);
  const vector = new THREE.Vector3(x, y, z);
  return vector.lengthSq() > EPSILON ? vector.normalize() : null;
}

export function mergeBoundsList(boundsList = []) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  let count = 0;
  for (const bounds of Array.isArray(boundsList) ? boundsList : []) {
    if (!isNumericBounds(bounds)) {
      continue;
    }
    count += 1;
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], toNumber(bounds.min[axis]));
      max[axis] = Math.max(max[axis], toNumber(bounds.max[axis]));
    }
  }
  return count > 0 && min.every(Number.isFinite) && max.every(Number.isFinite)
    ? { min, max }
    : null;
}

export function shiftedBounds(bounds, translation = null) {
  if (!isNumericBounds(bounds)) {
    return null;
  }
  const offset = vectorComponents(translation);
  return {
    min: bounds.min.slice(0, 3).map((value, index) => toNumber(value) + offset[index]),
    max: bounds.max.slice(0, 3).map((value, index) => toNumber(value) + offset[index])
  };
}

export function displayRecordsBounds(records = [], {
  partIds = null,
  translationByRecord = null
} = {}) {
  const filter = partIds instanceof Set && partIds.size > 0 ? partIds : null;
  const boundsList = [];
  for (const record of Array.isArray(records) ? records : []) {
    if (!record || !isNumericBounds(record.partBounds)) {
      continue;
    }
    const partId = normalizePartId(record.partId);
    if (filter && !partIdMatchesFilter(partId, filter)) {
      continue;
    }
    const translation = translationByRecord instanceof Map
      ? translationByRecord.get(record)
      : null;
    boundsList.push(shiftedBounds(record.partBounds, translation));
  }
  return mergeBoundsList(boundsList);
}

export function focusedDisplayRecordsBounds(records = [], {
  partIds = null,
  translationByRecord = null,
  fallbackBounds = null
} = {}) {
  const filter = partIds instanceof Set && partIds.size > 0 ? partIds : null;
  if (!filter) {
    return displayRecordsBounds(records, { translationByRecord }) || fallbackBounds;
  }
  const recordBounds = displayRecordsBounds(records, { partIds: filter, translationByRecord });
  return filter.has("__model__") ? (recordBounds || fallbackBounds) : recordBounds;
}

export function boundsCenterAndRadius(THREE, bounds, {
  offset = null
} = {}) {
  if (!THREE?.Vector3 || !isNumericBounds(bounds)) {
    return null;
  }
  const center = new THREE.Vector3(
    (toNumber(bounds.min[0]) + toNumber(bounds.max[0])) / 2,
    (toNumber(bounds.min[1]) + toNumber(bounds.max[1])) / 2,
    (toNumber(bounds.min[2]) + toNumber(bounds.max[2])) / 2
  );
  if (offset?.isVector3) {
    center.add(offset);
  }
  const radius = new THREE.Vector3(
    Math.max(toNumber(bounds.max[0]) - toNumber(bounds.min[0]), 0),
    Math.max(toNumber(bounds.max[1]) - toNumber(bounds.min[1]), 0),
    Math.max(toNumber(bounds.max[2]) - toNumber(bounds.min[2]), 0)
  ).length() / 2;
  return { center, radius };
}

export function fitDistanceForRadius(camera, radius, {
  aspect = camera?.aspect || 1,
  minRadius = 0,
  padding = DEFAULT_AUTO_ZOOM_PADDING
} = {}) {
  const fov = Math.max(toNumber(camera?.fov, 48), EPSILON);
  const safeRadius = Math.max(
    toNumber(radius) * Math.max(toNumber(padding, DEFAULT_AUTO_ZOOM_PADDING), EPSILON),
    toNumber(minRadius)
  );
  const verticalHalfFov = (fov * Math.PI) / 360;
  const horizontalHalfFov = Math.atan(Math.tan(verticalHalfFov) * Math.max(toNumber(aspect, 1), EPSILON));
  const limitingHalfFov = Math.max(Math.min(verticalHalfFov, horizontalHalfFov), EPSILON);
  return safeRadius / Math.sin(limitingHalfFov);
}

export function autoZoomFrameForBounds(THREE, {
  camera,
  controls,
  bounds,
  modelOffset = null,
  frameAspect = camera?.aspect || 1,
  minRadius = 0,
  padding = DEFAULT_AUTO_ZOOM_PADDING,
  defaultDirection = [2.1, -1.65, 1.08],
  viewDirection = null,
  viewUp = null
} = {}) {
  if (!THREE?.Vector3 || !camera || !controls) {
    return null;
  }
  const frame = boundsCenterAndRadius(THREE, bounds, { offset: modelOffset });
  if (!frame || !Number.isFinite(frame.radius)) {
    return null;
  }
  const offset = camera.position.clone().sub(controls.target);
  const direction = normalizedVector(THREE, viewDirection) || (offset.lengthSq() > EPSILON
    ? offset.normalize()
    : new THREE.Vector3(...defaultDirection).normalize());
  const up = normalizedVector(THREE, viewUp) || camera.up.clone();
  const distance = fitDistanceForRadius(camera, frame.radius, {
    aspect: frameAspect,
    minRadius,
    padding
  });
  const position = frame.center.clone().add(direction.multiplyScalar(distance));
  return {
    center: frame.center,
    radius: frame.radius,
    distance,
    position,
    target: frame.center.clone(),
    up,
    zoom: camera.zoom
  };
}

import { isFinitePoint, normalizeVector3 } from "./measurement.js";

const MIN_DIMENSION_OFFSET = 0.75;
const DIMENSION_OFFSET_RATIO = 0.12;
const TICK_LENGTH_RATIO = 0.075;

function subtract(a, b) {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function add(a, b) {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}

function scale(vector, amount) {
  return [vector[0] * amount, vector[1] * amount, vector[2] * amount];
}

function cross(a, b) {
  return [
    (a[1] * b[2]) - (a[2] * b[1]),
    (a[2] * b[0]) - (a[0] * b[2]),
    (a[0] * b[1]) - (a[1] * b[0])
  ];
}

function dot(a, b) {
  return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2]);
}

function vectorLength(vector) {
  return Math.hypot(vector[0], vector[1], vector[2]);
}

function cameraPoint(camera) {
  const position = camera?.position;
  if (!position || !Number.isFinite(position.x) || !Number.isFinite(position.y) || !Number.isFinite(position.z)) {
    return null;
  }
  return [position.x, position.y, position.z];
}

function midpointOfPoints(a, b) {
  if (!isFinitePoint(a) || !isFinitePoint(b)) {
    return null;
  }
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
}

function faceNormal(pick) {
  return normalizeVector3(pick?.reference?.pickData?.normal);
}

export function dimensionEndpoints(pickA, pickB, measurement) {
  const pointA = pickA?.point;
  const pointB = pickB?.point;
  if (!isFinitePoint(pointA) || !isFinitePoint(pointB)) {
    return null;
  }
  // A face-to-face result is a normal distance.  Draw that normal distance, not
  // the potentially diagonal distance between the two click locations.
  const normal = measurement?.perpendicular !== null && measurement?.perpendicular !== undefined
    ? faceNormal(pickA)
    : null;
  if (!normal) {
    return { start: pointA, end: pointB };
  }
  const signedDistance = dot(subtract(pointB, pointA), normal);
  return {
    start: pointA,
    end: add(pointA, scale(normal, signedDistance))
  };
}

/**
 * Produces a conventional dimension construction in world space: witness lines,
 * an offset dimension line, and ticks.  The offset is camera-aware so labels and
 * lines are not buried in the picked surface.
 */
export function measureDimensionSegments(pickA, pickB, measurement = null, { camera = null } = {}) {
  const endpoints = dimensionEndpoints(pickA, pickB, measurement);
  if (!endpoints) {
    return null;
  }
  const directionRaw = subtract(endpoints.end, endpoints.start);
  const length = vectorLength(directionRaw);
  if (!(length > 1e-9)) {
    return null;
  }
  const direction = scale(directionRaw, 1 / length);
  const midpoint = midpointOfPoints(endpoints.start, endpoints.end);
  const eyeDirection = midpoint && cameraPoint(camera)
    ? normalizeVector3(subtract(cameraPoint(camera), midpoint))
    : null;
  const cameraUp = normalizeVector3(camera?.up ? [camera.up.x, camera.up.y, camera.up.z] : null);
  const offsetDirection = normalizeVector3(cross(eyeDirection || cameraUp || [0, 0, 1], direction)) ||
    normalizeVector3(cross(cameraUp || [0, 1, 0], direction)) ||
    [0, 1, 0];
  const offset = Math.max(MIN_DIMENSION_OFFSET, length * DIMENSION_OFFSET_RATIO);
  const tickLength = Math.max(MIN_DIMENSION_OFFSET * 0.55, length * TICK_LENGTH_RATIO);
  const witnessStart = add(endpoints.start, scale(offsetDirection, offset));
  const witnessEnd = add(endpoints.end, scale(offsetDirection, offset));
  const tickDirection = direction;
  const tick = (point) => {
    const half = scale(tickDirection, tickLength / 2);
    return [subtract(point, half), add(point, half)];
  };
  return {
    start: endpoints.start,
    end: endpoints.end,
    witnessStart,
    witnessEnd,
    labelPoint: midpointOfPoints(witnessStart, witnessEnd),
    ticks: [tick(witnessStart), tick(witnessEnd)],
    segments: [
      [endpoints.start, witnessStart],
      [endpoints.end, witnessEnd],
      [witnessStart, witnessEnd],
      tick(witnessStart),
      tick(witnessEnd)
    ]
  };
}

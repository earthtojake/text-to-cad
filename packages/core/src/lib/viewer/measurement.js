// Measurement maths for the viewer's measure tool.
//
// This module is deliberately pure: it never reads the selector proxy and never
// knows about scene transforms. Snap geometry arrives already resolved and
// already in the same frame as the hit point, because only the viewer knows the
// offset it applied to re-centre the model. A reference's own `pickData` is in
// the model's untranslated frame, and it describes edges as `segmentStart` /
// `segmentCount` offsets into a shared buffer rather than as points, so it can
// never be snapped against directly.

import { measureEntityPair } from "./measureEntities.js";

const PLANAR_SURFACE_TYPES = new Set(["plane", "planar"]);
const PARALLEL_NORMAL_TOLERANCE = 0.999;
const EPSILON = 1e-9;

export const MEASURE_SNAP_LABELS = {
  vertex: "Vertex",
  edge: "Edge",
  face: "Face",
  // A point on a mesh's triangle (`meshMeasure.js`), between its corners and sides.
  surface: "Surface",
  // A circle's or arc's centre, where a drawing's pick snaps to a hole.
  center: "Centre",
  free: "Point"
};

export function normalizeVector3(value) {
  if (!Array.isArray(value) || value.length < 3) {
    return null;
  }
  const x = Number(value[0]);
  const y = Number(value[1]);
  const z = Number(value[2]);
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) {
    return null;
  }
  const magnitude = Math.hypot(x, y, z);
  if (!(magnitude > 0)) {
    return null;
  }
  return [x / magnitude, y / magnitude, z / magnitude];
}

function pointVector(a, b) {
  if (!isFinitePoint(a) || !isFinitePoint(b)) {
    return null;
  }
  return [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function dot3(a, b) {
  return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2]);
}

// `Number(null)` is 0 and `Number("")` is 0, so an absent quantity has to be
// rejected before coercion — otherwise a face with no length reports length 0.
function finiteNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function isFinitePoint(value) {
  return (
    Array.isArray(value) &&
    value.length >= 3 &&
    Number.isFinite(value[0]) &&
    Number.isFinite(value[1]) &&
    Number.isFinite(value[2])
  );
}

/**
 * Same rule STEP uses for corners: pick the nearest projected vertex, but only
 * if it is within maxScreenDistancePx of the cursor.
 */
export function pickMeshVertexByScreenDistance(vertices, clientPoint, maxScreenDistancePx, projectToClient) {
  const clientX = Number(clientPoint?.x);
  const clientY = Number(clientPoint?.y);
  const maxDistance = Number(maxScreenDistancePx);
  if (
    !Number.isFinite(clientX) ||
    !Number.isFinite(clientY) ||
    !Number.isFinite(maxDistance) ||
    maxDistance < 0 ||
    !Array.isArray(vertices) ||
    typeof projectToClient !== "function"
  ) {
    return null;
  }
  let bestPoint = null;
  let bestDistance = Infinity;
  for (const vertex of vertices) {
    if (!isFinitePoint(vertex)) {
      continue;
    }
    const projected = projectToClient(vertex);
    const projectedX = Number(projected?.x);
    const projectedY = Number(projected?.y);
    if (!Number.isFinite(projectedX) || !Number.isFinite(projectedY)) {
      continue;
    }
    const distance = Math.hypot(clientX - projectedX, clientY - projectedY);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestPoint = vertex.slice(0, 3);
    }
  }
  if (!bestPoint || bestDistance > maxDistance) {
    return null;
  }
  return { point: bestPoint, snapKind: "vertex", screenDistance: bestDistance };
}

export function distanceBetweenPoints(a, b) {
  const vector = pointVector(a, b);
  if (!vector) {
    return null;
  }
  const distance = Math.hypot(vector[0], vector[1], vector[2]);
  return distance < EPSILON ? 0 : distance;
}

export function closestPointOnSegment(point, start, end) {
  if (!isFinitePoint(point) || !isFinitePoint(start) || !isFinitePoint(end)) {
    return null;
  }
  const direction = pointVector(start, end);
  if (!direction) {
    return null;
  }
  const lengthSquared = (direction[0] ** 2) + (direction[1] ** 2) + (direction[2] ** 2);
  if (lengthSquared <= 0) {
    return start;
  }
  const relative = pointVector(start, point);
  if (!relative) {
    return null;
  }
  const t = clamp(dot3(relative, direction) / lengthSquared, 0, 1);
  return [
    start[0] + (direction[0] * t),
    start[1] + (direction[1] * t),
    start[2] + (direction[2] * t)
  ];
}

export function hasMeasurableSegments(segments) {
  return (
    (ArrayBuffer.isView(segments) || Array.isArray(segments)) &&
    segments.length >= 6 &&
    segments.length % 6 === 0
  );
}

/**
 * Closest point on a flat `[x1,y1,z1, x2,y2,z2, ...]` list of independent line
 * segments — the layout the viewer's edge proxy uses. Consecutive segments are
 * not assumed to share endpoints, so this is not a polyline walk.
 */
export function closestPointOnSegmentList(segments, point) {
  if (!hasMeasurableSegments(segments) || !isFinitePoint(point)) {
    return null;
  }
  let bestPoint = null;
  let bestDistance = Infinity;
  for (let offset = 0; offset + 5 < segments.length; offset += 6) {
    const candidate = closestPointOnSegment(
      point,
      [segments[offset], segments[offset + 1], segments[offset + 2]],
      [segments[offset + 3], segments[offset + 4], segments[offset + 5]]
    );
    if (!candidate) {
      continue;
    }
    const candidateDistance = distanceBetweenPoints(point, candidate);
    if (candidateDistance !== null && candidateDistance < bestDistance) {
      bestDistance = candidateDistance;
      bestPoint = candidate;
    }
  }
  return bestPoint;
}

export function isPlanarFace(reference) {
  const pickData = reference?.pickData;
  if (!pickData) {
    return false;
  }
  const surfaceType = String(pickData.surfaceType || pickData.surface?.type || "").trim().toLowerCase();
  if (!surfaceType || !PLANAR_SURFACE_TYPES.has(surfaceType)) {
    return false;
  }
  return normalizeVector3(pickData.normal) !== null;
}

const ARC_FIT_TOLERANCE = 0.02;

function cross3(a, b) {
  return [
    (a[1] * b[2]) - (a[2] * b[1]),
    (a[2] * b[0]) - (a[0] * b[2]),
    (a[0] * b[1]) - (a[1] * b[0])
  ];
}

function segmentPoints(segments) {
  const points = [];
  for (let offset = 0; offset + 5 < segments.length; offset += 6) {
    if (offset === 0) {
      points.push([segments[0], segments[1], segments[2]]);
    }
    points.push([segments[offset + 3], segments[offset + 4], segments[offset + 5]]);
  }
  return points;
}

// The circumcentre of three points, which is the exact centre of the circle they
// lie on. Using the centroid of the tessellation instead would only be right for
// a full circle and would quietly mislocate every arc.
function circumcentre(p1, p2, p3) {
  const a = [p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]];
  const b = [p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2]];
  const normal = cross3(a, b);
  const normalLengthSquared = dot3(normal, normal);
  if (normalLengthSquared <= EPSILON) {
    return null;
  }
  const bxn = cross3(b, normal);
  const nxa = cross3(normal, a);
  const aa = dot3(a, a);
  const bb = dot3(b, b);
  const scale = 1 / (2 * normalLengthSquared);
  return [
    p1[0] + (((aa * bxn[0]) + (bb * nxa[0])) * scale),
    p1[1] + (((aa * bxn[1]) + (bb * nxa[1])) * scale),
    p1[2] + (((aa * bxn[2]) + (bb * nxa[2])) * scale)
  ];
}

/**
 * What an edge actually is, read off its tessellation rather than off the
 * artifact's own labels. The topology exporter reports edge `curveType` using
 * the surface-type enum names (a circle comes through as "cylinder", a line as
 * "plane") and ships no edge `params` at all, so radius and direction have to be
 * recovered from the geometry to be trustworthy.
 */
export function edgeGeometryFromSegments(segments) {
  if (!hasMeasurableSegments(segments)) {
    return null;
  }
  const points = segmentPoints(segments);
  if (points.length < 2) {
    return null;
  }
  const firstDirection = normalizeVector3([
    points[1][0] - points[0][0],
    points[1][1] - points[0][1],
    points[1][2] - points[0][2]
  ]);
  if (!firstDirection) {
    return null;
  }
  const straight = points.every((point, index) => {
    if (index === 0) {
      return true;
    }
    const direction = normalizeVector3([
      point[0] - points[index - 1][0],
      point[1] - points[index - 1][1],
      point[2] - points[index - 1][2]
    ]);
    return !direction || Math.abs(dot3(direction, firstDirection)) > PARALLEL_NORMAL_TOLERANCE;
  });
  if (straight) {
    return { kind: "line", direction: firstDirection };
  }
  if (points.length < 3) {
    return null;
  }
  // Sampled at thirds rather than at the ends: a closed circle's first and last
  // tessellation points are the same point, which collapses the circumcircle.
  const centre = circumcentre(
    points[0],
    points[Math.floor(points.length / 3)],
    points[Math.floor((points.length * 2) / 3)]
  ) || circumcentre(points[0], points[Math.floor(points.length / 2)], points[points.length - 1]);
  if (!centre) {
    return null;
  }
  const radii = points.map((point) => distanceBetweenPoints(centre, point)).filter((value) => value !== null);
  if (!radii.length) {
    return null;
  }
  const radius = radii.reduce((total, value) => total + value, 0) / radii.length;
  if (!(radius > EPSILON)) {
    return null;
  }
  const spread = Math.max(...radii) - Math.min(...radii);
  if (spread / radius > ARC_FIT_TOLERANCE) {
    return { kind: "curve" };
  }
  return { kind: "arc", radius, center: centre };
}

export function classifyMeasurePick({
  reference = null,
  hitPoint = null,
  referenceId = "",
  edgeSegments = null,
  // The fit only depends on the segments, so a caller hovering the same edge
  // frame after frame can hand back the previous result instead of refitting.
  edgeGeometry,
  vertexPoint = null
} = {}) {
  const normalizedHit = isFinitePoint(hitPoint) ? hitPoint.slice(0, 3) : null;
  const pickData = reference?.pickData || {};
  const selectorType = String(pickData.selectorType || reference?.selectorType || "").trim().toLowerCase();
  const snapKind = classifyMeasureSnapKind({
    pickData,
    selectorType,
    hitPoint: normalizedHit,
    edgeSegments,
    vertexPoint
  });
  if (!snapKind) {
    return null;
  }
  const point = measurePointFromReference({
    snapKind,
    hitPoint: normalizedHit,
    edgeSegments,
    vertexPoint
  });
  if (!point) {
    return null;
  }
  return {
    referenceId: String(referenceId || "").trim(),
    reference: reference || null,
    snapKind,
    point,
    geometry: snapKind === "edge"
      ? (edgeGeometry === undefined ? edgeGeometryFromSegments(edgeSegments) : edgeGeometry)
      : null
  };
}

export function classifyMeasureSnapKind({
  pickData = null,
  selectorType = "",
  hitPoint = null,
  edgeSegments = null,
  vertexPoint = null
} = {}) {
  if (!pickData) {
    return isFinitePoint(hitPoint) ? "free" : null;
  }
  const normalizedSelectorType = String(pickData.selectorType || selectorType || "").trim().toLowerCase();
  if (normalizedSelectorType === "vertex" && isFinitePoint(vertexPoint)) {
    return "vertex";
  }
  if (hasMeasurableSegments(edgeSegments) && isFinitePoint(hitPoint)) {
    return "edge";
  }
  if (normalizedSelectorType === "face") {
    return "face";
  }
  return isFinitePoint(hitPoint) ? "free" : null;
}

export function measurePointFromReference({
  snapKind = "",
  hitPoint = null,
  edgeSegments = null,
  vertexPoint = null
} = {}) {
  const normalizedKind = String(snapKind || "").trim();
  if (normalizedKind === "vertex") {
    return isFinitePoint(vertexPoint) ? vertexPoint.slice(0, 3) : null;
  }
  if (normalizedKind === "edge") {
    if (!isFinitePoint(hitPoint)) {
      return null;
    }
    return closestPointOnSegmentList(edgeSegments, hitPoint);
  }
  if (normalizedKind === "face" || normalizedKind === "free") {
    return isFinitePoint(hitPoint) ? hitPoint.slice(0, 3) : null;
  }
  return null;
}

/**
 * The reading of two picks, in the order a CAD measure tool reports it: what the two ENTITIES make
 * (`measureEntities.js`), not what the two points picked on them do. `kind` says which it is:
 *
 * - `normal`: the perpendicular distance (`perpendicular`) — parallel planes, a vertex to a plane or an
 *   edge, parallel edges;
 * - `centers`: the centre-to-centre distance (`centerDistance`) of two circles or cylinders;
 * - `angle`: the angle (`angleDeg`, the acute one) of two planes, or two edges that are not parallel,
 *   with the shortest distance between them (`minDistance`);
 * - `min`: the shortest distance between the two (`minDistance`); `distance`: that of two points;
 * - `points`: the pair has no reading of its own, and the distance is the one between the points picked.
 *
 * `euclidean` and `delta` are always those of the two points picked; `ends` are the points the reading
 * is drawn between. Picks on a mesh (`units`) are two points on its surface and approximate.
 */
export function measurementFromPicks(pickA, pickB) {
  const pointA = isFinitePoint(pickA?.point) ? pickA.point : null;
  const pointB = isFinitePoint(pickB?.point) ? pickB.point : null;
  if (!pointA || !pointB) {
    return null;
  }
  const euclidean = distanceBetweenPoints(pointA, pointB);
  if (euclidean === null) {
    return null;
  }
  // Picks on a mesh carry the units the scene is read in and are approximate (`meshMeasure.js`);
  // a STEP's are exact, in its millimetres.
  const units = pickA?.units || pickB?.units || null;
  if (units) {
    const perWorld = Number(units.perWorld) || 1;
    return {
      kind: "points",
      euclidean: euclidean * perWorld,
      perpendicular: null,
      centerDistance: null,
      minDistance: null,
      angleDeg: null,
      delta: [0, 1, 2].map(axis => (pointB[axis] - pointA[axis]) * perWorld),
      unit: String(units.unit || ""),
      approximate: pickA?.approximate === true || pickB?.approximate === true
    };
  }
  const result = {
    kind: "points",
    euclidean,
    perpendicular: null,
    centerDistance: null,
    minDistance: null,
    angleDeg: null,
    delta: [pointB[0] - pointA[0], pointB[1] - pointA[1], pointB[2] - pointA[2]],
    unit: "mm"
  };
  const entities = measureEntityPair(pickA, pickB);
  if (!entities) {
    return result;
  }
  result.kind = entities.kind;
  result.angleDeg = entities.angleDeg;
  if (entities.kind === "normal") result.perpendicular = entities.distance;
  else if (entities.kind === "centers") result.centerDistance = entities.distance;
  else result.minDistance = entities.distance;
  result.ends = { start: entities.start, end: entities.end };
  return result;
}

/**
 * What a single selected entity is worth on its own — length, area, radius —
 * taken from the exact values the topology computed rather than from the
 * tessellation. This is the half of a CAD measure tool that answers "how big is
 * this thing" before any second pick is made. A face's area is cadgen's exact measure of it, which
 * the view asks for when the face is pointed at: `faceArea` is its state, and `{state: "ready",
 * area}` reports it.
 */
export function entityMeasurementFromPick(pick, { faceArea = null } = {}) {
  if (pick?.snapKind === "vertex" && isFinitePoint(pick.point)) {
    // Where it is in the model's own coordinates, not where the viewer drew the re-centred model.
    const offset = isFinitePoint(pick.offset) ? pick.offset : [0, 0, 0];
    return { selectorType: "vertex", typeLabel: "vertex", unit: "mm", point: [0, 1, 2].map(axis => pick.point[axis] - offset[axis]) };
  }
  if (pick?.snapKind !== "edge" && pick?.snapKind !== "face") {
    return null;
  }
  const reference = pick?.reference;
  const pickData = reference?.pickData;
  if (!pickData) {
    return null;
  }
  const selectorType = String(pickData.selectorType || reference?.selectorType || "").trim().toLowerCase();
  const params = pickData.params || {};
  if (selectorType === "edge") {
    const geometry = pick.geometry || null;
    const radius = geometry?.kind === "arc" ? (finiteNumber(params.radius) ?? finiteNumber(geometry.radius)) : null;
    return compactEntity({
      selectorType: "edge",
      typeLabel: edgeTypeLabel(geometry),
      length: finiteNumber(pickData.length),
      radius,
      diameter: radius === null ? null : radius * 2,
      center: geometry?.kind === "arc" && isFinitePoint(geometry.center) ? geometry.center.slice(0, 3) : null
    });
  }
  if (selectorType === "face") {
    const surfaceType = String(pickData.surfaceType || "").trim().toLowerCase();
    const radius = finiteNumber(params.radius);
    return compactEntity({
      selectorType: "face",
      typeLabel: surfaceType || "face",
      area: faceArea?.state === "ready" ? finiteNumber(faceArea.area) : null,
      radius,
      diameter: radius === null ? null : radius * 2,
      center: isFinitePoint(params.center) ? params.center.slice(0, 3) : null,
      normal: PLANAR_SURFACE_TYPES.has(surfaceType) ? normalizeVector3(pickData.normal) : null
    });
  }
  return null;
}

// The artifact's own edge labels are unreliable, so the name comes from the fit.
function edgeTypeLabel(geometry) {
  if (geometry?.kind === "line") {
    return "line";
  }
  if (geometry?.kind === "arc") {
    return "circle";
  }
  return "edge";
}

function compactEntity(entity) {
  const compact = { unit: "mm" };
  for (const [key, value] of Object.entries(entity)) {
    if (value !== null && value !== undefined) {
      compact[key] = value;
    }
  }
  return compact.length !== undefined ||
    compact.area !== undefined ||
    compact.radius !== undefined ||
    compact.majorRadius !== undefined ||
    compact.point !== undefined
    ? compact
    : null;
}

function roundedPrecision(precision) {
  return Number.isInteger(Number(precision)) ? Number(precision) : 2;
}

function firstFiniteQuantity(values) {
  for (const value of values) {
    const numeric = finiteNumber(value);
    if (numeric !== null) {
      return numeric;
    }
  }
  return null;
}

export function formatMeasurement(measurement, { precision = 2 } = {}) {
  if (!measurement || !Number.isFinite(Number(measurement.euclidean))) {
    return "";
  }
  const value = firstFiniteQuantity([
    measurement.perpendicular,
    measurement.centerDistance,
    measurement.minDistance,
    measurement.euclidean
  ]);
  if (value === null) {
    return "";
  }
  if (measurement.approximate === true) {
    // A mesh's reading: "≈", to a tenth of a millimetre or so in whatever its file measures in.
    const unit = measurement.unit || "";
    return `≈ ${value.toFixed(APPROXIMATE_DECIMALS[unit] ?? 2)}${unit ? ` ${unit}` : ""}`;
  }
  return `${value.toFixed(roundedPrecision(precision))} ${measurement.unit || "mm"}`;
}

// How many decimals an approximate reading keeps, by its unit: about a tenth of a millimetre.
const APPROXIMATE_DECIMALS = Object.freeze({ m: 4, cm: 2, mm: 1, "µm": 0, in: 3, ft: 4 });

export function formatMeasurementAngle(measurement, { precision = 1 } = {}) {
  const angle = finiteNumber(measurement?.angleDeg);
  if (angle === null) {
    return "";
  }
  return `${angle.toFixed(roundedPrecision(precision))}°`;
}

export function formatMeasurementDelta(measurement, { precision = 2 } = {}) {
  if (!Array.isArray(measurement?.delta) || measurement.delta.length < 3) {
    return "";
  }
  const values = measurement.delta.slice(0, 3).map((component) => Number(component));
  if (!values.every((component) => Number.isFinite(component))) {
    return "";
  }
  const digits = roundedPrecision(precision);
  const formatComponent = (component) => {
    const formatted = component.toFixed(digits);
    return formatted === `-${(0).toFixed(digits)}` ? (0).toFixed(digits) : formatted;
  };
  return `ΔX ${formatComponent(values[0])}  ΔY ${formatComponent(values[1])}  ΔZ ${formatComponent(values[2])}`;
}

export function formatEntityMeasurement(entity, { precision = 2 } = {}) {
  if (!entity) {
    return "";
  }
  const digits = roundedPrecision(precision);
  const unit = entity.unit || "mm";
  if (Array.isArray(entity.point)) {
    // A vertex: where it is, as a position reads (no unit after each axis).
    return `${entity.point.map((value, axis) => `${"XYZ"[axis]} ${(Math.abs(value) < 0.5 * 10 ** -digits ? 0 : value).toFixed(digits)}`).join("  ")} ${unit}`;
  }
  const parts = [];
  if (entity.diameter !== undefined) {
    parts.push(`⌀ ${entity.diameter.toFixed(digits)} ${unit}`);
  } else if (entity.majorRadius !== undefined) {
    parts.push(`R ${entity.majorRadius.toFixed(digits)} / ${(entity.minorRadius ?? entity.majorRadius).toFixed(digits)} ${unit}`);
  }
  if (entity.length !== undefined) {
    parts.push(`L ${entity.length.toFixed(digits)} ${unit}`);
  }
  if (entity.area !== undefined) {
    parts.push(`A ${entity.area.toFixed(digits)} ${unit}²`);
  }
  if (Array.isArray(entity.normal)) {
    parts.push(`N ${entity.normal.map(value => (Math.abs(value) < 5e-3 ? 0 : value).toFixed(2)).join(" ")}`);
  }
  return parts.join("  ");
}

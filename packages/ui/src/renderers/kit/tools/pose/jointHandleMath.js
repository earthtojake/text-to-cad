/**
 * The Pose tool's geometry: where a joint's handle sits, and what a drag of its
 * knob means for the joint's value.
 *
 * Everything is plain `[x, y, z]` in ONE space (the caller's: the viewer passes
 * model space), with pointer rays as `{ origin, direction }` and screen points
 * in CSS pixels. No scene, no camera, no React: the viewer supplies the ray under
 * the pointer and a `project(point) -> [x, y]`, the format adapters supply the
 * pivot and axis, and a drag returns the joint's next VALUE. Limits are not
 * applied here; clamping belongs to the handlers the value is handed to.
 *
 * A drag picks its mapping once, at the grab, and keeps it: the camera cannot
 * move while a knob is held, so the view that made a mapping degenerate cannot
 * change under it.
 *  - revolute: the pointer ray meets the plane through the pivot, normal to the
 *    axis; the signed angle about the axis accumulates sample to sample, so a
 *    continuous joint winds past 180 degrees without a jump. Edge-on to the
 *    camera that plane has no usable intersection, and the drag becomes screen
 *    distance along the near side of the ring: one arm length is one radian.
 *  - prismatic: the point of the axis line closest to the pointer ray. With the
 *    axis pointing at the camera that point runs away, and the drag becomes
 *    pixels at the pivot's depth: right or up is positive.
 */

const RAD_TO_DEG = 180 / Math.PI;
const EPSILON = 1e-9;

/** |ray . axis| below this: the rotation plane is within ~12 degrees of edge-on. */
export const REVOLUTE_EDGE_ON_LIMIT = 0.2;
/** |ray . axis| above this: the slide axis is within ~15 degrees of the view direction. */
export const PRISMATIC_HEAD_ON_LIMIT = 0.966;

export const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const subtract = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const scale = (a, s) => [a[0] * s, a[1] * s, a[2] * s];
export const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
export const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
export const length = (a) => Math.hypot(a[0], a[1], a[2]);

export function normalize(a) {
  const size = length(a);
  return size > EPSILON ? scale(a, 1 / size) : null;
}

/** The part of `vector` that lies in the plane normal to the unit `axis`. */
export function rejectFromAxis(vector, axis) {
  return subtract(vector, scale(axis, dot(vector, axis)));
}

/** A unit vector normal to `axis` that depends on nothing but the axis. */
export function stablePerpendicular(axis) {
  const unit = normalize(axis) || [0, 0, 1];
  // Cross with the world axis the joint axis is least aligned with: never degenerate.
  const abs = unit.map(Math.abs);
  const helper = abs[0] <= abs[1] && abs[0] <= abs[2] ? [1, 0, 0] : abs[1] <= abs[2] ? [0, 1, 0] : [0, 0, 1];
  return normalize(cross(unit, helper));
}

/** Rodrigues: `vector` turned by `angleRad` about the unit `axis`. */
export function rotateAboutAxis(vector, axis, angleRad) {
  const cos = Math.cos(angleRad);
  const sin = Math.sin(angleRad);
  return add(
    add(scale(vector, cos), scale(cross(axis, vector), sin)),
    scale(axis, dot(axis, vector) * (1 - cos))
  );
}

/** Signed angle (radians, within +-pi) from `from` to `to` about the unit `axis`. */
export function signedAngleAbout(axis, from, to) {
  return Math.atan2(dot(cross(from, to), axis), dot(from, to));
}

/**
 * The unit direction a handle's arm leaves the pivot in. A slider's arm is its
 * axis. A turning joint's arm lies in the rotation plane, toward `toward` (a
 * point that moves with the child, so the knob rides the moving part); `null`
 * when `toward` is on the axis and gives the plane no direction.
 */
export function handleArmDirection({ kind, pivot, axis, toward = null }) {
  const unitAxis = normalize(axis);
  if (!unitAxis) return null;
  if (kind === "prismatic") return unitAxis;
  return toward ? normalize(rejectFromAxis(subtract(toward, pivot), unitAxis)) : null;
}

/**
 * Points of the circle of `radius` about the axis, from `fromDeg` to `toDeg`
 * measured from `direction` (a unit vector in the rotation plane).
 */
export function arcPoints({ pivot, axis, direction, radius, fromDeg, toDeg, stepDeg = 6 }) {
  const unitAxis = normalize(axis);
  const segments = Math.max(Math.ceil(Math.abs(toDeg - fromDeg) / stepDeg), 1);
  const points = [];
  for (let index = 0; index <= segments; index += 1) {
    const angle = (fromDeg + ((toDeg - fromDeg) * index) / segments) / RAD_TO_DEG;
    points.push(add(pivot, scale(rotateAboutAxis(direction, unitAxis, angle), radius)));
  }
  return points;
}

/** Where `ray` meets the plane through `pivot` normal to `axis`; `null` behind the ray or parallel to it. */
export function rayPlanePoint(ray, pivot, axis) {
  const denominator = dot(ray.direction, axis);
  if (Math.abs(denominator) < EPSILON) return null;
  const distance = dot(subtract(pivot, ray.origin), axis) / denominator;
  return distance > 0 ? add(ray.origin, scale(ray.direction, distance)) : null;
}

/** Distance along the unit `axis` from `pivot` to the axis point closest to `ray`; `null` when they are parallel. */
export function closestAxisDistance(ray, pivot, axis) {
  const alignment = dot(axis, ray.direction);
  const denominator = 1 - alignment * alignment;
  if (denominator < EPSILON) return null;
  const offset = subtract(ray.origin, pivot);
  return (dot(offset, axis) - alignment * dot(offset, ray.direction)) / denominator;
}

const screenDelta = (from, to) => [to[0] - from[0], to[1] - from[1]];

function planeDirection(ray, pivot, axis) {
  const point = rayPlanePoint(ray, pivot, axis);
  return point ? normalize(rejectFromAxis(subtract(point, pivot), axis)) : null;
}

// Positive rotation carries the near side of the ring along axis x near; a
// person dragging an edge-on ring is dragging that near side.
function edgeOnScreenTangent({ pivot, axis, reach }, { ray, project }) {
  const near = normalize(rejectFromAxis(scale(ray.direction, -1), axis)) || stablePerpendicular(axis);
  const tangent = screenDelta(project(pivot), project(add(pivot, scale(cross(axis, near), reach))));
  const pixels = Math.hypot(tangent[0], tangent[1]);
  return pixels > EPSILON ? { direction: [tangent[0] / pixels, tangent[1] / pixels], pixelsPerRadian: pixels } : null;
}

// Pixels per world unit at the pivot's depth, measured across the axis (which is
// across the view, since the axis is along it).
function headOnPixelsPerUnit({ pivot, axis, reach }, { project }) {
  const across = screenDelta(project(pivot), project(add(pivot, scale(stablePerpendicular(axis), reach))));
  return Math.hypot(across[0], across[1]) / reach;
}

/**
 * Take hold of a knob. `handle` is `{ kind, pivot, axis, value, reach }` (`reach`
 * is the arm's world length, the screen fallbacks' sense of scale); `sample` is
 * `{ ray, pointer, project }`. Returns the grab, or `null` when nothing about
 * this view can be dragged.
 */
export function beginJointDrag(handle, sample) {
  const axis = normalize(handle.axis);
  if (!axis || !(handle.reach > 0)) return null;
  const grab = { kind: handle.kind, pivot: handle.pivot, axis, value: handle.value, pointer: sample.pointer };
  const alignment = Math.abs(dot(sample.ray.direction, axis));
  if (handle.kind === "prismatic") {
    const distance = alignment < PRISMATIC_HEAD_ON_LIMIT ? closestAxisDistance(sample.ray, handle.pivot, axis) : null;
    if (distance !== null) return { ...grab, mode: "axis", distance };
    const pixelsPerUnit = headOnPixelsPerUnit({ ...handle, axis }, sample);
    return pixelsPerUnit > EPSILON ? { ...grab, mode: "screen", pixelsPerUnit } : null;
  }
  const direction = alignment >= REVOLUTE_EDGE_ON_LIMIT ? planeDirection(sample.ray, handle.pivot, axis) : null;
  if (direction) return { ...grab, mode: "plane", direction };
  const tangent = edgeOnScreenTangent({ ...handle, axis }, sample);
  return tangent ? { ...grab, mode: "screen", tangent } : null;
}

/**
 * Move a held knob to `sample` (`{ ray, pointer }`). Returns the grab to carry
 * into the next sample; its `value` is the joint's value now: the value at the
 * grab plus everything dragged since, unclamped.
 */
export function advanceJointDrag(grab, sample) {
  if (grab.mode === "plane") {
    const direction = planeDirection(sample.ray, grab.pivot, grab.axis);
    // A ray that left the plane (past its horizon) or crossed the pivot says nothing: hold.
    if (!direction) return grab;
    // Sample to sample, never from the grab: each step is well inside +-180, so the sum can wind.
    return { ...grab, direction, value: grab.value + signedAngleAbout(grab.axis, grab.direction, direction) * RAD_TO_DEG };
  }
  if (grab.mode === "axis") {
    const distance = closestAxisDistance(sample.ray, grab.pivot, grab.axis);
    return distance === null ? grab : { ...grab, distance, value: grab.value + distance - grab.distance };
  }
  const [dx, dy] = screenDelta(grab.pointer, sample.pointer);
  const moved = grab.kind === "prismatic"
    // Screen y grows downward: right or up slides the joint out.
    ? (dx - dy) / grab.pixelsPerUnit
    : ((dx * grab.tangent.direction[0] + dy * grab.tangent.direction[1]) / grab.tangent.pixelsPerRadian) * RAD_TO_DEG;
  return { ...grab, pointer: sample.pointer, value: grab.value + moved };
}

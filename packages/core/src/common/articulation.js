// The articulation player.
//
// cadgen resolves a model's kinematics into ONE artifact (`cadgen.articulation`): controls
// with their limits and rest values, joints in their rest frames with affine rows over the
// controls, which occurrences each joint carries, what a drag gesture writes, the named
// poses and the opening pose. This module plays it and decides nothing: control values go
// to joint values by dot products, joint values to one world delta per joint (its parent's
// delta, then its own displacement about its rest axis), and the deltas onto the effect
// records of the occurrences the artifact says each joint carries. A delta IS an effect
// matrix: for an occurrence at rest placement R, the posed placement is D * R, which is how
// every effect premultiplies (recordEffects.js), so a clip's keys play on top of a pose
// unchanged (applySceneState.js).
//
// The same player serves a robot description: its articulation puts a link's visuals under
// the joint that carries them, a mimic is a row with a leader term and a bias, and a
// continuous joint has no limits.

const DEG_TO_RAD = Math.PI / 180;

function isObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function finite(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export function articulationControls(articulation) {
  return Array.isArray(articulation?.controls) ? articulation.controls.filter((control) => control?.id) : [];
}

export function articulationHandles(articulation) {
  return Array.isArray(articulation?.handles) ? articulation.handles.filter((handle) => handle?.id) : [];
}

export function articulationPoses(articulation) {
  return isObject(articulation?.poses) ? articulation.poses : {};
}

/** The control a value is for, by id. */
export function articulationControl(articulation, id) {
  return articulationControls(articulation).find((control) => control.id === String(id || "")) || null;
}

/** A value within the control's limits; an unreadable value is the control's rest value. */
export function clampControlValue(control, value) {
  const rest = finite(control?.default, 0);
  let number = finite(value, rest);
  const min = finite(control?.min, Number.NEGATIVE_INFINITY);
  const max = finite(control?.max, Number.POSITIVE_INFINITY);
  if (number < Math.min(min, max)) number = Math.min(min, max);
  if (number > Math.max(min, max)) number = Math.max(min, max);
  return number;
}

/** Every control at its rest value. */
export function openingControlValues(articulation) {
  const opening = isObject(articulation?.opening) ? articulation.opening : {};
  return Object.fromEntries(articulationControls(articulation).map((control) => [
    control.id, clampControlValue(control, Object.hasOwn(opening, control.id) ? opening[control.id] : control.default)
  ]));
}

/** A full configuration: every control, the given ones clamped, the rest at their rest values. */
export function normalizeControlValues(articulation, values) {
  const given = isObject(values) ? values : {};
  const opening = openingControlValues(articulation);
  return Object.fromEntries(articulationControls(articulation).map((control) => [
    control.id, Object.hasOwn(given, control.id) ? clampControlValue(control, given[control.id]) : opening[control.id]
  ]));
}

/** A named pose as a full configuration: what it names, and every other control at rest. */
export function poseControlValues(articulation, name) {
  const preset = articulationPoses(articulation)[String(name || "")];
  return normalizeControlValues(articulation, { ...openingControlValues(articulation), ...(isObject(preset) ? preset : {}) });
}

/** bias + sum(weight * control). */
export function rowValue(row, values) {
  if (!isObject(row)) return 0;
  let total = finite(row.bias, 0);
  for (const term of Array.isArray(row.terms) ? row.terms : []) {
    if (!Array.isArray(term)) continue;
    total += finite(term[1], 0) * finite(values?.[term[0]], 0);
  }
  return total;
}

/** Every joint's {turn (degrees), travel (model units)} at a configuration. */
export function jointValues(articulation, values) {
  const result = {};
  for (const joint of Array.isArray(articulation?.joints) ? articulation.joints : []) {
    if (!joint?.id) continue;
    result[joint.id] = { turn: rowValue(joint.turn, values), travel: rowValue(joint.travel, values) };
  }
  return result;
}

/** True when no joint moves: the artifact as written (every row at 0). */
export function articulationAtRest(articulation, values, epsilon = 1e-9) {
  return Object.values(jointValues(articulation, values)).every(
    ({ turn, travel }) => Math.abs(turn) <= epsilon && Math.abs(travel) <= epsilon
  );
}

const scratch = { axis: null, origin: null, rotation: null, step: null };

function scratchFor(THREE) {
  if (!scratch.axis) {
    scratch.axis = new THREE.Vector3();
    scratch.origin = new THREE.Vector3();
    scratch.rotation = new THREE.Matrix4();
    scratch.step = new THREE.Matrix4();
  }
  return scratch;
}

// D(axis, q) in rest space: T(o) R(axis, turn) T(-o), then T(axis * travel) — the two
// commute, both being about one axis.
function jointMotion(THREE, joint, turnDeg, travel, target) {
  const { axis, origin, rotation, step } = scratchFor(THREE);
  axis.set(finite(joint.axis?.[0], 0), finite(joint.axis?.[1], 0), finite(joint.axis?.[2], 1)).normalize();
  origin.set(finite(joint.origin?.[0], 0), finite(joint.origin?.[1], 0), finite(joint.origin?.[2], 0));
  target.identity();
  if (turnDeg) {
    target.premultiply(step.makeTranslation(-origin.x, -origin.y, -origin.z));
    target.premultiply(rotation.makeRotationAxis(axis, turnDeg * DEG_TO_RAD));
    target.premultiply(step.makeTranslation(origin.x, origin.y, origin.z));
  }
  if (travel) {
    target.premultiply(step.makeTranslation(axis.x * travel, axis.y * travel, axis.z * travel));
  }
  return target;
}

/** One world delta per joint at a configuration: its parent's delta times its own
 * displacement. Joints are listed parents first, so one pass composes the chain. */
export function jointDeltas(THREE, articulation, values) {
  const rows = jointValues(articulation, values);
  const deltas = new Map();
  for (const joint of Array.isArray(articulation?.joints) ? articulation.joints : []) {
    if (!joint?.id) continue;
    const parent = deltas.get(joint.parent) || null;
    const delta = new THREE.Matrix4();
    if (joint.kind !== "fixed" && Array.isArray(joint.axis)) {
      const own = rows[joint.id];
      jointMotion(THREE, joint, own.turn, own.travel, delta);
    }
    if (parent) delta.premultiply(parent);
    deltas.set(joint.id, delta);
  }
  return deltas;
}

/** The occurrences a joint carries, as the artifact lists them. */
export function jointCarries(articulation, jointId) {
  const carried = articulation?.carries?.[jointId];
  return Array.isArray(carried) ? carried : [];
}

/**
 * Pose the effect records: each joint's delta onto every occurrence it carries (over whatever
 * an effect already holds, though a pose is the first thing a pass writes). Returns how many
 * occurrences moved; at rest nothing is written, which is the "artifact as written is q=0" law.
 */
export function applyArticulationToEffects(THREE, articulation, values, effectsByPartId) {
  if (!articulation || !effectsByPartId || articulationAtRest(articulation, values)) return 0;
  let moved = 0;
  for (const [jointId, delta] of jointDeltas(THREE, articulation, values)) {
    for (const partId of jointCarries(articulation, jointId)) {
      const effect = effectsByPartId.get(partId) || { matrix: null, style: null, visible: null, highlighted: false };
      effect.matrix = effect.matrix ? effect.matrix.clone().premultiply(delta) : delta.clone();
      effectsByPartId.set(partId, effect);
      moved += 1;
    }
  }
  return moved;
}

/** What a handle shows: its joint row's value at the configuration. */
export function handleRowValue(articulation, handle, values) {
  const joint = (Array.isArray(articulation?.joints) ? articulation.joints : []).find((entry) => entry?.id === handle?.joint);
  return rowValue(joint?.[handle?.dof], values);
}

/**
 * Back-drive: the write that lands a handle's row on `target`. The row is affine in the
 * control the handle names, so the value is (target - the rest of the row) / weight, clamped
 * to that control's limits — a geared member moves its coupling, a free one moves itself,
 * and neither can go where its slider could not.
 */
export function controlWriteForHandle(articulation, handle, values, target) {
  const control = articulationControl(articulation, handle?.control);
  const weight = finite(handle?.weight, 0);
  if (!control || !weight) {
    return null;
  }
  const current = finite(values?.[control.id], 0);
  const rest = handleRowValue(articulation, handle, values) - weight * current;
  return { id: control.id, value: clampControlValue(control, (finite(target, rest) - rest) / weight) };
}

/** The handle that drives a control's own row, when a joint row carries it as a term — what the
 * Position panel's slider for the control shows and writes through. */
export function handleForControl(articulation, controlId) {
  return articulationHandles(articulation).find((handle) => handle.id === String(controlId || "")) || null;
}

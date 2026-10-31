// An orthographic view draws the same picture from any distance along it, so where its eye
// stands is free — but a pick's ray and the depth range both start at the eye's plane: whatever
// lies behind it can be neither picked nor drawn. A framing about a small subject (a look-at, a
// zoom to a selection) can leave the eye inside the model; this steps it back along the view, out
// past the model, which changes nothing on screen.

// How far past the model's nearest corner the eye stands, as a share of the model's size.
const CLEARANCE = 0.1;

/**
 * Moves an orthographic `camera` back along its view, away from `target`, until every corner of
 * `bounds` lies in front of it. Anything else is left as it is.
 * @param {import("three").Camera} camera
 * @param {import("three").Vector3} target  The orbit centre: what the camera looks at.
 * @param {{ min: number[], max: number[] } | null} bounds
 * @returns {boolean} Whether the eye moved.
 */
export function keepOrthographicEyeOutside(camera, target, bounds) {
  if (!camera?.isOrthographicCamera || !target || !bounds?.min || !bounds?.max) return false;
  const toEye = camera.position.clone().sub(target);
  const distance = toEye.length();
  if (!(distance > 0)) return false;
  toEye.divideScalar(distance);
  const size = Math.hypot(...bounds.max.map((value, axis) => value - bounds.min[axis]));
  if (!(size > 0)) return false;
  // The farthest a corner reaches toward the eye, from the target.
  let reach = -Infinity;
  for (const x of [bounds.min[0], bounds.max[0]]) for (const y of [bounds.min[1], bounds.max[1]]) for (const z of [bounds.min[2], bounds.max[2]]) {
    reach = Math.max(reach, (x - target.x) * toEye.x + (y - target.y) * toEye.y + (z - target.z) * toEye.z);
  }
  const needed = reach + size * CLEARANCE;
  if (distance >= needed) return false;
  camera.position.copy(target).addScaledVector(toEye, needed);
  camera.updateMatrixWorld();
  return true;
}

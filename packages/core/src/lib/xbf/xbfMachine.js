// A machine's twin: which of a mechanism's joints is each machine axis, and the pose a controller's
// reading puts them at (the engine's `cad_server/machines`: `reading.axes`, millimetres for X Y Z U V W,
// degrees for A B C, in machine coordinates).
//
// A joint is an axis's when its name is the axis's letter, or `<letter>_axis` or `axis_<letter>`, in
// any case, and it moves the way the axis does: a prismatic joint for a linear axis, a revolute one for
// a rotary axis. A joint's value is the machine's coordinate as it is: the twin is modelled at the
// machine's zero, so a joint at 0 is the axis at 0. Two joints that both name one axis are refused,
// never one chosen.
import { xbfCoupledPairs, xbfUnposable } from "./xbfKinematics.js";

export const MACHINE_AXES = Object.freeze(["X", "Y", "Z", "U", "V", "W", "A", "B", "C"]);
const ROTARY = new Set(["A", "B", "C"]);

function axisNamed(label) {
  const name = String(label || "").trim().toUpperCase().replace(/[\s-]+/g, "_");
  const match = /^(?:AXIS_)?([XYZUVWABC])(?:_AXIS)?$/.exec(name);
  return match && !(name.startsWith("AXIS_") && name.endsWith("_AXIS")) ? match[1] : null;
}

/**
 * Each machine axis's joint in `kinematics`.
 * @returns {{ joints: Record<string, { pair: string, min: number | null, max: number | null }>,
 *   refused: { axis: string, reason: string }[] }}
 *   `joints`: by axis letter, the joint it poses and its limits. `refused`: each axis a joint names
 *   that cannot be its joint, and why.
 */
export function xbfMachineJoints(kinematics) {
  const coupled = xbfCoupledPairs(kinematics);
  const unposable = xbfUnposable(kinematics);
  const found = new Map();
  const refused = [];
  for (const pair of kinematics?.pairs || []) {
    const axis = axisNamed(pair.label);
    if (!axis) continue;
    const wanted = ROTARY.has(axis) ? "revolute" : "prismatic";
    if (pair.type !== wanted) {
      refused.push({ axis, reason: `${pair.label} is a ${pair.type} joint; axis ${axis} needs a ${wanted} one` });
      continue;
    }
    if (coupled.has(pair.label) || unposable.has(pair.label)) {
      refused.push({ axis, reason: `${pair.label} moves only with another joint` });
      continue;
    }
    if (found.has(axis)) {
      refused.push({ axis, reason: `${found.get(axis).pair} and ${pair.label} both name axis ${axis}` });
      found.set(axis, null);
      continue;
    }
    const [min, max] = pair.limits?.[0] || [null, null];
    found.set(axis, { pair: pair.label, min: min ?? null, max: max ?? null });
  }
  const joints = {};
  for (const axis of MACHINE_AXES) if (found.get(axis)) joints[axis] = found.get(axis);
  return { joints, refused };
}

/**
 * The pose `reading` puts the twin at: `values` with each matched axis's joint at the reading's
 * coordinate, an axis past its joint's travel held at the limit, and what the page says beside it.
 * @param {ReturnType<typeof xbfMachineJoints>} mapping
 * @param {Record<string, number[]>} values  Every pair's values now.
 * @param {{ axes: Record<string, number> }} reading
 * @returns {{ values: Record<string, number[]>, unmatched: string[], idle: string[], past: string[] }}
 *   `unmatched`: axes the machine reported that no joint is; `idle`: joints of axes it did not
 *   report, left where they were; `past`: axes beyond their joint's limits, shown at them.
 */
export function xbfMachinePose(mapping, values, reading) {
  const next = { ...values };
  const unmatched = [];
  const past = [];
  const axes = reading?.axes || {};
  for (const axis of MACHINE_AXES) {
    if (!(axis in axes)) continue;
    const joint = mapping.joints[axis];
    const value = Number(axes[axis]);
    if (!joint) {
      unmatched.push(axis);
      continue;
    }
    if (!Number.isFinite(value)) continue;
    // A pose holds every joint inside its limits (`xbfPoseValues` refuses one past them), so an axis
    // past its joint's travel is shown at the limit, and said: the model's travel is not the machine's.
    const low = joint.min ?? -Infinity;
    const high = joint.max ?? Infinity;
    next[joint.pair] = [Math.min(Math.max(value, low), high)];
    if (value < low || value > high) past.push(axis);
  }
  const idle = Object.keys(mapping.joints).filter(axis => !(axis in axes));
  return { values: next, unmatched, idle, past };
}

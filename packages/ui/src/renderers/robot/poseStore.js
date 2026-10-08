import { URDF_JOINT_VALUE_EPSILON } from "@text-to-cad/core/lib/urdf/jointValues.js";
import { clampJointValueDeg } from "@text-to-cad/core/lib/urdf/kinematics.js";
import { robotOpeningPose, srdfGroupStateJointValuesToDisplay } from "@text-to-cad/core/lib/urdf/motion.js";
import { cloneJointValueMap, findBestMatchingJointValueState } from "./robotMotion.js";

// A robot's pose: the value of every joint a person can drive (degrees, or metres for a
// prismatic joint), outside React. There is ONE write path, and every write is where the
// robot IS from that frame on: a slider, a typed number, a Pose knob, a named pose and
// Reset alike. Listeners hear about a write synchronously: the scene poses itself on it,
// and only what draws joint VALUES (the Position section) subscribes a component.

function groupStatesOf(description) {
  const states = Array.isArray(description?.srdf?.groupStates) ? description.srdf.groupStates
    : Array.isArray(description?.motion?.groupStates) ? description.motion.groupStates : [];
  const counts = new Map();
  for (const state of states) {
    const name = String(state?.name || "").trim();
    if (name) counts.set(name, (counts.get(name) || 0) + 1);
  }
  return states.map((state) => {
    const name = String(state?.name || "").trim();
    const group = String(state?.group || "").trim();
    if (!name || !group) return null;
    // SRDF values are radians and metres; the pose is degrees and metres.
    const jointValuesByName = srdfGroupStateJointValuesToDisplay(description, state?.jointValuesByName || state?.jointValuesByNameRad);
    return { ...state, id: `${group}/${name}`, label: counts.get(name) > 1 ? `${name} (${group})` : name, jointValuesByName };
  }).filter(Boolean);
}

/** The joints a Position slider exists for: not fixed, not a mimic follower. */
export function movableJoints(description) {
  return (Array.isArray(description?.joints) ? description.joints : [])
    .filter(joint => String(joint?.type || "") !== "fixed" && !joint?.mimic && String(joint?.name || ""));
}

/**
 * What a robot's pose is made of, as one comparable string: each joint a person drives — its name,
 * type, range and default — and the named poses (an SRDF's group states, `home` included). A new
 * revision of the file with the same keeps the pose it was left in; one with anything else opens at
 * its own opening pose, since a pose is never fitted onto joints that changed.
 */
export function poseLogic(description) {
  return JSON.stringify([
    movableJoints(description).map(joint => [joint.name, String(joint.type || ""), joint.minValueDeg ?? null, joint.maxValueDeg ?? null, joint.defaultValueDeg ?? null]),
    groupStatesOf(description).map(state => [state.id, Object.entries(state.jointValuesByName || {}).sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))]),
  ]);
}

/**
 * @param {object} description  A parsed URDF or SDF (an SRDF's is its URDF's, with `srdf` on it).
 * @param {Record<string, number> | null} [initial]  Values to open at (a restored record, or the pose a
 *   previous revision with the same pose logic was left in): known joints are kept, clamped to THIS
 *   description's limits.
 * @param {string} [trackedId]  The named pose those values were chosen as, which the store shows until
 *   a joint is moved (a revision with the same pose logic carries it over).
 */
export function createPoseStore(description, initial = null, trackedId = "") {
  const joints = movableJoints(description);
  const jointByName = new Map(joints.map(joint => [joint.name, joint]));
  // The opening pose (core's, so a snapshot renders the robot where this opens it): every
  // joint at its declared default, then the SRDF group state(s) named "home".
  const defaults = Object.freeze(robotOpeningPose(description));
  const groupStates = groupStatesOf(description);
  const listeners = new Set();
  const clampKnown = values => Object.fromEntries(Object.entries(cloneJointValueMap(values))
    .filter(([name]) => jointByName.has(name)).map(([name, value]) => [name, clampJointValueDeg(jointByName.get(name), value)]));

  let values = Object.freeze({ ...defaults, ...clampKnown(initial) });
  let trackedGroupStateId = String(trackedId || "");
  let snapshot = null;
  // A named pose is shown while it was the last thing chosen; otherwise the one the
  // joints happen to match, with every other joint at its default.
  const read = () => (snapshot ||= Object.freeze({
    values,
    groupStateId: groupStates.some(state => state.id === trackedGroupStateId) ? trackedGroupStateId
      : findBestMatchingJointValueState(groupStates, values, defaults)?.id || ""
  }));
  function commit(nextValues, nextTracked) {
    values = Object.freeze(nextValues);
    trackedGroupStateId = nextTracked;
    snapshot = null;
    for (const listener of [...listeners]) listener();
  }

  return {
    joints, defaults, groupStates,
    /** `poseLogic(description)`: what decides whether a new revision keeps this pose. */
    logic: poseLogic(description),
    getSnapshot: read,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    /** One joint moved by hand: clamped, ignored under the epsilon, and the tracked named pose released. */
    write(joint, value) {
      const name = String(joint?.name || "").trim();
      const known = jointByName.get(name);
      if (!known) return false;
      const next = clampJointValueDeg(known, value);
      if (Math.abs(next - (Number.isFinite(values[name]) ? values[name] : Number(known.defaultValueDeg) || 0)) <= URDF_JOINT_VALUE_EPSILON) return false;
      commit({ ...values, [name]: next }, "");
      return true;
    },
    /** A named pose MERGES its joints over the pose as it is, and is tracked until a joint is moved. */
    selectGroupState(state) {
      // As the SRDF wrote them: the solver and the sliders clamp on reading, and a state
      // keeps matching itself (`groupStateId`) even where it sits outside a limit.
      const stateValues = cloneJointValueMap(state?.jointValuesByName);
      if (!Object.keys(stateValues).length) return false;
      commit({ ...values, ...stateValues }, String(state?.id || "").trim());
      return true;
    },
    reset() { commit({ ...defaults }, ""); },
  };
}

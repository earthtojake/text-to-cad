import {
  articulationControls, clampControlValue, openingControlValues
} from "@text-to-cad/core/common/articulation.js";
import { cloneJointValueMap, findBestMatchingJointValueState, JOINT_VALUE_EPSILON } from "./robotMotion.js";

// A robot's pose: the value of every control of its articulation (degrees, or metres for
// a prismatic joint), outside React. There is ONE write path, and every write is where the
// robot IS from that frame on: a slider, a typed number, a Pose knob, a named pose and
// Reset alike. Listeners hear about a write synchronously: the scene poses itself on it,
// and only what draws control VALUES (the Position section) subscribes a component.
//
// Everything here is read off the articulation cadgen resolved (`cadgen.robot_payload`):
// the controls and their limits, the opening pose (every control at rest, then an SRDF's
// `home` state) and the named poses (an SRDF's group states). Nothing is decided here.

const text = value => String(value ?? "").trim();

/** An SRDF's group states as the Pose row lists them: id, name, label (the group named where a name repeats), values. */
export function robotGroupStates(robot) {
  const articulation = robot?.articulation || null;
  const states = Array.isArray(robot?.srdf?.groupStates) ? robot.srdf.groupStates : [];
  const counts = new Map();
  for (const state of states) counts.set(text(state?.name), (counts.get(text(state?.name)) || 0) + 1);
  return states.map((state) => {
    const id = text(state?.id), name = text(state?.name), group = text(state?.group);
    if (!id || !name) return null;
    return { id, name, group, label: counts.get(name) > 1 ? `${name} (${group})` : name, values: cloneJointValueMap(articulation?.poses?.[id]) };
  }).filter(Boolean);
}

/**
 * What a robot's pose is made of, as one comparable string: each control — its id, unit, range
 * and rest value — and the named poses. A new revision of the file with the same keeps the pose it
 * was left in; one with anything else opens at its own opening pose, since a pose is never fitted
 * onto controls that changed.
 */
export function poseLogic(robot) {
  const articulation = robot?.articulation || null;
  return JSON.stringify([
    articulationControls(articulation).map(control => [control.id, control.unit, control.min ?? null, control.max ?? null, control.default ?? null]),
    robotGroupStates(robot).map(state => [state.id, Object.entries(state.values).sort(([left], [right]) => (left < right ? -1 : left > right ? 1 : 0))]),
    openingControlValues(articulation)
  ]);
}

/**
 * @param {object} robot  The payload cadgen resolved.
 * @param {Record<string, number> | null} [initial]  Values to open at (a restored record, or the pose a
 *   previous revision with the same pose logic was left in): known controls are kept, clamped to THIS
 *   articulation's limits.
 * @param {string} [trackedId]  The named pose those values were chosen as, which the store shows until
 *   a control is moved (a revision with the same pose logic carries it over).
 */
export function createPoseStore(robot, initial = null, trackedId = "") {
  const articulation = robot?.articulation || null;
  const controls = articulationControls(articulation);
  const controlById = new Map(controls.map(control => [control.id, control]));
  // The opening pose (cadgen's, so a snapshot renders the robot where this opens it).
  const defaults = Object.freeze(openingControlValues(articulation));
  const groupStates = robotGroupStates(robot);
  const listeners = new Set();
  const clampKnown = values => Object.fromEntries(Object.entries(cloneJointValueMap(values))
    .filter(([id]) => controlById.has(id)).map(([id, value]) => [id, clampControlValue(controlById.get(id), value)]));

  let values = Object.freeze({ ...defaults, ...clampKnown(initial) });
  let trackedGroupStateId = String(trackedId || "");
  let snapshot = null;
  // A named pose is shown while it was the last thing chosen; otherwise the one the
  // controls happen to match, with every other control at its opening value.
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
    articulation, controls, defaults, groupStates,
    /** `poseLogic(robot)`: what decides whether a new revision keeps this pose. */
    logic: poseLogic(robot),
    getSnapshot: read,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    /** One control moved by hand: clamped, ignored under the epsilon, and the tracked named pose released. */
    write(id, value) {
      const control = controlById.get(String(id || "").trim());
      if (!control) return false;
      const next = clampControlValue(control, value);
      if (Math.abs(next - (Number.isFinite(values[control.id]) ? values[control.id] : defaults[control.id])) <= JOINT_VALUE_EPSILON) return false;
      commit({ ...values, [control.id]: next }, "");
      return true;
    },
    /** A named pose MERGES its controls over the pose as it is (a group state speaks for its group's
     * joints and no other), and is tracked until a control is moved. */
    selectGroupState(state) {
      const stateValues = clampKnown(state?.values);
      if (!Object.keys(stateValues).length) return false;
      commit({ ...values, ...stateValues }, String(state?.id || "").trim());
      return true;
    },
    reset() { commit({ ...defaults }, ""); },
  };
}

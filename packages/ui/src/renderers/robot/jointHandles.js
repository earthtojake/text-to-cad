import {
  articulationHandles, controlWriteForHandle, handleRowValue
} from "@text-to-cad/core/common/articulation.js";
import { armOffset, normalize, subtract, wrapTurn } from "../kit/tools/pose/jointHandleMath.js";

// What the Position tool can take hold of on a robot, as the kit's plain handle list
// (`kit/tools/pose`), in the robot's own space:
//
//   { id, label, kind: "revolute" | "continuous" | "prismatic", pivot, axis, toward,
//     value, min, max, unit, onChange(value) }
//
// The articulation cadgen resolved says what there is to hold and what a drag writes
// (`handles`: one per moving joint row; a mimic follower's writes its leader, and the
// player solves the write, `controlWriteForHandle`). This file only places each one: a
// joint's axis is written in rest space, and its node's world matrix in the scene — the
// joint's delta (its parents' motion, then its own) — carries pivot, axis and arm to where
// the joint now is. A turning joint's arm points at the carried link's geometry, or along
// a perpendicular fixed in the joint's frame when that geometry is centred on the axis (a
// wheel, a roll joint). Nothing is solved here.

// A null limit is no limit (a continuous joint): `Number(null)` is 0, so it is asked first.
const isLimit = (value) => value != null && Number.isFinite(Number(value));

/** The handles of a robot's articulation: one per moving joint row, with the kit's kind. */
export function robotPosableHandles(robot) {
  const articulation = robot?.articulation || null;
  const joints = new Map((articulation?.joints || []).map((joint) => [joint.id, joint]));
  return articulationHandles(articulation)
    .filter((handle) => (handle.dof === "turn" || handle.dof === "travel") && joints.get(handle.joint)?.axis && joints.get(handle.joint)?.origin)
    .map((handle) => {
      const limited = isLimit(handle.min) && isLimit(handle.max);
      return { ...handle, node: joints.get(handle.joint), kind: handle.dof === "travel" ? "prismatic" : limited ? "revolute" : "continuous", limited };
    });
}

/**
 * The per-handle constants of the list: everything that does not change with the pose,
 * computed once per scene.
 *
 * @param {typeof import("three")} THREE
 * @param {object} robot  The payload.
 * @param {ReturnType<typeof import("@text-to-cad/core/lib/urdf/robotScene.js").createRobotScene>} scene
 */
export function prepareRobotJointHandles(THREE, robot, scene) {
  const articulation = robot?.articulation || null;
  const prepared = [];
  for (const handle of robotPosableHandles(robot)) {
    const axis = normalize(handle.node.axis.map(Number));
    const origin = handle.node.origin.map(Number);
    if (!axis || origin.length !== 3 || !scene.motionFrame(handle.joint)) continue;
    // The carried link's centre, in rest space, seen from the joint's origin.
    const centre = (articulation?.carries?.[handle.joint] || []).map((link) => scene.linkCentre(link)).find(Boolean) || null;
    const prismatic = handle.kind === "prismatic";
    prepared.push({
      articulation, handle, axis, origin, prismatic,
      arm: prismatic ? null : armOffset(axis, centre ? subtract(centre, origin) : null),
      min: handle.limited ? Number(handle.min) : null,
      max: handle.limited ? Number(handle.max) : null
    });
  }
  return prepared;
}

/**
 * The handle list for the pose ON SCREEN: read from the scene's joint matrices, so whatever
 * moved the robot (a slider, a named pose, Reset, a knob further up the chain) moved these.
 *
 * @param {typeof import("three")} THREE
 * @param {ReturnType<typeof prepareRobotJointHandles>} prepared
 * @param {ReturnType<typeof import("@text-to-cad/core/lib/urdf/robotScene.js").createRobotScene>} scene
 * @param {Record<string, number>} values  The pose store's control values.
 * @param {(id: string, value: number) => void} onControlChange  The pose store's one write path.
 */
export function robotJointHandles(THREE, prepared, scene, values, onControlChange) {
  const point = new THREE.Vector3();
  return prepared.map(({ articulation, handle, axis, origin, prismatic, arm, min, max }) => {
    const delta = scene.motionFrame(handle.joint);
    return {
      id: handle.id,
      label: handle.label || handle.id,
      kind: handle.kind,
      pivot: point.set(...origin).applyMatrix4(delta).toArray(),
      axis: normalize(point.set(...axis).transformDirection(delta).toArray()),
      toward: prismatic ? null : point.set(origin[0] + arm[0], origin[1] + arm[1], origin[2] + arm[2]).applyMatrix4(delta).toArray(),
      // The row's value at the pose, as the player reads it, so the label agrees with the pose on screen.
      value: handleRowValue(articulation, handle, values),
      min, max,
      unit: String(handle.unit || (prismatic ? "m" : "deg")),
      // A continuous joint's drag winds freely and is stored as one turn, which is what its slider spans.
      onChange: (value) => {
        const write = controlWriteForHandle(articulation, handle, values, handle.limited ? value : wrapTurn(value));
        if (write) onControlChange(write.id, write.value);
      }
    };
  });
}

import { clampJointValueDeg } from "@hardcore/core/lib/urdf/kinematics.js";
import { armOffset, normalize, wrapTurn } from "../kit/tools/pose/jointHandleMath.js";

// What the Pose tool can take hold of on a robot, as the kit's plain handle list
// (`kit/tools/pose`), in the robot's own space:
//
//   { id, label, kind: "revolute" | "continuous" | "prismatic", pivot, axis, toward,
//     value, min, max, unit, onChange(value) }
//
// A joint's frame AFTER its motion is its motion group's world matrix, so there is
// nothing to solve here: the pivot is that frame's origin, the axis is the joint's axis
// carried by it, and a turning joint's arm points at the child link's geometry (through
// an SDF joint's static child offset), or along a perpendicular fixed in the child's
// frame when that geometry is centred on the axis (a wheel, a roll joint).

const HANDLE_KINDS = new Set(["revolute", "continuous", "prismatic"]);

/** The joints of a description a person can drive by a knob: turning or sliding, and not a mimic follower. */
export function robotPosableJoints(description) {
  return (Array.isArray(description?.joints) ? description.joints : [])
    .filter(joint => HANDLE_KINDS.has(String(joint?.type || "")) && !joint?.mimic && String(joint?.name || ""));
}

/**
 * The per-joint constants of the handle list: everything that does not change with the
 * pose, computed once per scene.
 *
 * @param {typeof import("three")} THREE
 * @param {object} description
 * @param {ReturnType<typeof import("@hardcore/core/lib/urdf/robotScene.js").createRobotScene>} scene
 */
export function prepareRobotJointHandles(THREE, description, scene) {
  const prepared = [];
  for (const joint of robotPosableJoints(description)) {
    const axis = normalize(Array.isArray(joint.axis) ? joint.axis.map(Number) : []);
    if (!axis || !scene.motionFrame(joint.name)) continue;
    const childCentre = scene.linkCentre(String(joint.childLink || ""));
    // The child's centre seen from the joint frame: an SDF child link sits at a static offset from it.
    const centre = childCentre && joint.postMotionTransform
      ? new THREE.Vector3(...childCentre).applyMatrix4(new THREE.Matrix4().set(...joint.postMotionTransform)).toArray()
      : childCentre;
    const prismatic = joint.type === "prismatic";
    const limited = joint.type !== "continuous";
    prepared.push({
      joint, axis, prismatic, limited,
      arm: prismatic ? null : armOffset(axis, centre),
      min: limited && Number.isFinite(Number(joint.minValueDeg)) ? Number(joint.minValueDeg) : null,
      max: limited && Number.isFinite(Number(joint.maxValueDeg)) ? Number(joint.maxValueDeg) : null
    });
  }
  return prepared;
}

/**
 * The handle list for the pose ON SCREEN: read from the scene's matrices, so whatever
 * moved the robot (a slider, a named pose, Reset, a knob further up the chain) moved these.
 *
 * @param {typeof import("three")} THREE
 * @param {ReturnType<typeof prepareRobotJointHandles>} prepared
 * @param {ReturnType<typeof import("@hardcore/core/lib/urdf/robotScene.js").createRobotScene>} scene
 * @param {Record<string, number>} values  The pose store's values.
 * @param {(joint: object, value: number) => void} onJointValueChange  The pose store's one write path.
 */
export function robotJointHandles(THREE, prepared, scene, values, onJointValueChange) {
  const point = new THREE.Vector3();
  return prepared.map(({ joint, axis, prismatic, limited, arm, min, max }) => {
    const frame = scene.motionFrame(joint.name);
    const pivot = point.set(0, 0, 0).applyMatrix4(frame).toArray();
    return {
      id: joint.name,
      label: joint.name,
      kind: joint.type,
      pivot,
      axis: normalize(point.set(...axis).transformDirection(frame).toArray()),
      toward: prismatic ? null : point.set(...arm).applyMatrix4(frame).toArray(),
      // As the solver reads it, so the label agrees with the pose on screen.
      value: clampJointValueDeg(joint, values?.[joint.name]),
      min, max,
      unit: prismatic ? "m" : "deg",
      // A continuous joint's drag winds freely and is stored as one turn, which is what its slider spans.
      onChange: value => onJointValueChange(joint, limited ? value : wrapTurn(value))
    };
  });
}

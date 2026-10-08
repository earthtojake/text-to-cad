/**
 * What the Position tool can take hold of in a STEP with kinematics. (A robot
 * description has its own adapter, in its own renderer.)
 *
 * The adapter turns the articulation cadgen resolved and the CURRENT pose into
 * the kit's plain list, in the space the model's parts are in:
 *
 *   { id, label, kind: "revolute" | "continuous" | "prismatic", pivot, axis,
 *     toward, value, min, max, unit, onChange(value) }
 *
 * The articulation's `handles` say what there is to hold and what a drag writes
 * (`core/common/articulation.js` solves the write); this file only places each
 * one: `pivot` rides the moving part (a slider's pivot is where its child now
 * is), `toward` is a point on the carried parts that gives a turning joint's arm
 * its direction, and `onChange` is the Position section's own change handler,
 * so limits and persistence are decided in one place. The viewer consumes the
 * list and knows nothing about the format.
 */

import * as THREE from "three";
import {
  articulationHandles,
  controlWriteForHandle,
  handleRowValue,
  jointCarries,
  jointDeltas
} from "@text-to-cad/core/common/articulation.js";

import {
  add,
  armOffset,
  dot,
  length,
  normalize,
  rotateAboutAxis,
  scale,
  subtract
} from "../../kit/tools/pose/jointHandleMath.js";

const HANDLE_KIND_BY_DOF = { turn: "revolute", travel: "prismatic" };

function articulationOf(definition) {
  return definition?.articulation || null;
}

/** The handles of a STEP's articulation a person can drive: one per movable joint row. */
export function stepPosableHandles(definition) {
  const articulation = articulationOf(definition);
  const joints = new Map((articulation?.joints || []).map((joint) => [joint.id, joint]));
  return articulationHandles(articulation)
    .filter((handle) => HANDLE_KIND_BY_DOF[handle.dof] && joints.get(handle.joint)?.axis && joints.get(handle.joint)?.origin)
    .map((handle) => ({ ...handle, kind: HANDLE_KIND_BY_DOF[handle.dof], joint: joints.get(handle.joint) }));
}

function jointAxis(joint) {
  const origin = Array.isArray(joint?.origin) ? joint.origin.map(Number) : [];
  const dir = normalize(Array.isArray(joint?.axis) ? joint.axis.map(Number) : []);
  return origin.length === 3 && origin.every(Number.isFinite) && dir ? { origin, dir } : null;
}

// The centre of the parts a joint carries, in the REST mesh (the viewer poses display
// records, never this data): where a turning joint's arm points.
function carriedCentre(articulation, jointId, meshData) {
  const parts = new Map((Array.isArray(meshData?.parts) ? meshData.parts : []).map((part) => [String(part?.id || part?.occurrenceId || ""), part]));
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  let found = false;
  for (const partId of jointCarries(articulation, jointId)) {
    const bounds = parts.get(partId)?.bounds;
    if (!Array.isArray(bounds?.min) || !Array.isArray(bounds?.max)) continue;
    found = true;
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], Number(bounds.min[axis]));
      max[axis] = Math.max(max[axis], Number(bounds.max[axis]));
    }
  }
  return found ? [0, 1, 2].map((axis) => (min[axis] + max[axis]) / 2) : null;
}

// Concentric members (a sun gear and the carrier round it) would stack their
// knobs on one spot. The k-th of n arms that coincide is turned k/n of the way
// round the shared axis, decided AT REST so a drag never reshuffles them.
function spreadCoincidentArms(arms) {
  const coincide = (a, b) => length(subtract(a.origin, b.origin)) <= 1e-6 * (1 + length(a.origin)) &&
    Math.abs(dot(a.dir, b.dir)) > 0.9999 && dot(a.arm, b.arm) > 0.98;
  return arms.map((arm) => {
    const group = arms.filter((other) => coincide(arm, other));
    const place = group.indexOf(arm);
    return place > 0 ? rotateAboutAxis(arm.arm, arm.dir, (2 * Math.PI * place) / group.length) : arm.arm;
  });
}

function carriedPoint(delta, point) {
  return new THREE.Vector3(...point).applyMatrix4(delta).toArray();
}

function carriedDirection(delta, direction) {
  return normalize(new THREE.Vector3(...direction).transformDirection(delta).toArray());
}

/**
 * Handles for a posed STEP. A joint's axis is written in rest numbers; its
 * world delta (its parents' motion, then its own) carries pivot, axis and arm
 * to where the child now is, for a chain of any depth.
 */
export function stepJointHandles({ definition, parameterValues, meshData, onParameterChange }) {
  const articulation = articulationOf(definition);
  const posable = stepPosableHandles(definition);
  if (!posable.length) return [];
  const deltas = jointDeltas(THREE, articulation, parameterValues);
  const located = posable.map((handle) => ({ handle, axis: jointAxis(handle.joint) })).filter(({ axis }) => axis);
  const arms = spreadCoincidentArms(located.map(({ handle, axis }) => {
    const centre = carriedCentre(articulation, handle.joint.id, meshData);
    return { ...axis, arm: handle.kind === "prismatic" ? axis.dir : armOffset(axis.dir, centre ? subtract(centre, axis.origin) : null) };
  }));
  return located.map(({ handle, axis }, index) => {
    const delta = deltas.get(handle.joint.id) || new THREE.Matrix4();
    const prismatic = handle.kind === "prismatic";
    return {
      id: handle.id,
      label: handle.label || handle.id,
      kind: handle.kind,
      pivot: carriedPoint(delta, axis.origin),
      axis: carriedDirection(delta, axis.dir),
      toward: prismatic ? null : carriedPoint(delta, add(axis.origin, arms[index])),
      value: handleRowValue(articulation, handle, parameterValues),
      min: Number.isFinite(Number(handle.min)) ? Number(handle.min) : null,
      max: Number.isFinite(Number(handle.max)) ? Number(handle.max) : null,
      unit: String(handle.unit || (prismatic ? "mm" : "deg")),
      onChange: (value) => {
        const write = controlWriteForHandle(articulation, handle, parameterValues, value);
        if (write) onParameterChange(write.id, write.value);
      }
    };
  });
}

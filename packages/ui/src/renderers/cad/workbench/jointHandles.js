/**
 * What the Pose tool can take hold of, for the two formats that have joints.
 *
 * Each adapter turns a description and its CURRENT pose into the same plain
 * list, in the space the model's parts are in:
 *
 *   { id, label, kind: "revolute" | "continuous" | "prismatic", pivot, axis,
 *     toward, value, min, max, unit, onChange(value) }
 *
 * `pivot` rides the moving part (a slider's pivot is where its child now is),
 * `toward` is a point on the child that gives a turning joint's arm its
 * direction, and `onChange` is the Kinematics tab's own change handler, so
 * limits, mimic followers, couplings and persistence are decided in one place.
 * The viewer consumes the list and knows nothing about either format.
 */

import { effectiveDofValues, kinematicsDofs, kinematicsMates } from "@hardcore/core/common/kinematicsRuntime.js";
import {
  axisAngleTransform,
  clampJointValueDeg,
  invertRigidTransform,
  mergeBounds,
  multiplyTransforms,
  transformBounds,
  transformPoint,
  translationTransform
} from "@hardcore/core/lib/urdf/kinematics.js";

import {
  add,
  dot,
  length,
  normalize,
  rejectFromAxis,
  rotateAboutAxis,
  scale,
  stablePerpendicular,
  subtract
} from "../../kit/tools/pose/jointHandleMath.js";
import { poseControlWrite, poseDrivenDofs } from "./poseDrivenControls.js";

const URDF_HANDLE_KINDS = new Set(["revolute", "continuous", "prismatic"]);
const STEP_HANDLE_KIND_BY_DOF_KIND = { revolute: "revolute", slider: "prismatic" };
// A child whose centre is this close to the axis (against its own reach from the
// pivot) gives the arm no direction worth following: a wheel, a roll joint.
const ON_AXIS_RATIO = 0.05;

// A continuous joint is an angle, not a count of turns: the sliders span one turn
// and the pose transitions already take the short way round, so a drag that has
// wound past it is stored as the same angle inside (-180, 180].
function wrapTurn(valueDeg) {
  return 180 - ((((180 - valueDeg) % 360) + 360) % 360);
}

function transformDirection(transform, direction) {
  return subtract(transformPoint(transform, direction), transformPoint(transform, [0, 0, 0]));
}

function boundsCenter(bounds) {
  return scale(add(bounds.min, bounds.max), 0.5);
}

// The arm's direction in a frame whose origin is on the axis: toward the child's
// centre where that is off the axis, else any perpendicular. It is a direction in
// the CHILD's frame either way, so it turns with the joint.
function armOffset(axis, centre) {
  const offset = centre ? rejectFromAxis(centre, axis) : null;
  return offset && length(offset) > ON_AXIS_RATIO * length(centre) ? normalize(offset) : stablePerpendicular(axis);
}

/** The joints of a robot description a person can drive: not fixed, not a mimic follower. */
export function urdfPosableJoints(urdfData) {
  return (Array.isArray(urdfData?.joints) ? urdfData.joints : [])
    .filter((joint) => URDF_HANDLE_KINDS.has(String(joint?.type || "")) && !joint?.mimic && String(joint?.name || ""));
}

/** Each link's geometry centre in its own frame, from the robot's mesh parts. Links without geometry are absent. */
export function urdfLinkCentres(parts) {
  const boundsByLink = new Map();
  for (const part of Array.isArray(parts) ? parts : []) {
    const linkName = String(part?.linkName || "");
    if (!linkName || !part?.sourceBounds) continue;
    boundsByLink.set(linkName, [
      ...(boundsByLink.get(linkName) || []),
      transformBounds(part.sourceBounds, part.localTransform)
    ]);
  }
  return new Map([...boundsByLink].map(([linkName, bounds]) => [linkName, boundsCenter(mergeBounds(bounds))]));
}

/**
 * Handles for a posed robot. `linkWorldTransforms` is the solved pose
 * (`solveUrdfLinkWorldTransforms`), so whatever moved the robot moved these.
 */
export function urdfJointHandles({ urdfData, jointValues, linkWorldTransforms, linkCentres, onJointValueChange }) {
  const handles = [];
  for (const joint of urdfPosableJoints(urdfData)) {
    const childWorld = linkWorldTransforms?.get?.(String(joint.childLink || ""));
    const axis = normalize(Array.isArray(joint.axis) ? joint.axis.map(Number) : []);
    if (!childWorld || !axis) continue;
    // The joint frame AFTER its motion: the child's frame, less an SDF joint's
    // static child offset. Its origin is on the axis and it carries the child.
    const childOffset = joint.postMotionTransform || null;
    const movedJointWorld = childOffset ? multiplyTransforms(childWorld, invertRigidTransform(childOffset)) : childWorld;
    const childCentre = linkCentres?.get?.(String(joint.childLink || ""));
    const centre = childCentre && childOffset ? transformPoint(childOffset, childCentre) : childCentre;
    const prismatic = joint.type === "prismatic";
    const limited = joint.type !== "continuous";
    handles.push({
      id: joint.name,
      label: joint.name,
      kind: joint.type,
      pivot: transformPoint(movedJointWorld, [0, 0, 0]),
      axis: normalize(transformDirection(movedJointWorld, axis)),
      toward: prismatic ? null : transformPoint(movedJointWorld, armOffset(axis, centre)),
      // As the solver reads it, so the label agrees with the pose on screen.
      value: clampJointValueDeg(joint, jointValues?.[joint.name]),
      min: limited && Number.isFinite(Number(joint.minValueDeg)) ? Number(joint.minValueDeg) : null,
      max: limited && Number.isFinite(Number(joint.maxValueDeg)) ? Number(joint.maxValueDeg) : null,
      unit: prismatic ? "m" : "deg",
      // The Kinematics tab's slider path: clamped, written at once, the group state released.
      onChange: (value) => onJointValueChange(joint, limited ? value : wrapTurn(value))
    });
  }
  return handles;
}

function stepKinematicsBlock(definition) {
  const block = definition?.manifest?.kinematics;
  return block && typeof block === "object" && !Array.isArray(block) ? block : null;
}

function mateDofs(mate) {
  return mate.kind === "cylindrical"
    ? [{ id: `${mate.name}.turn`, kind: "revolute" }, { id: `${mate.name}.travel`, kind: "prismatic" }]
    : [{ id: String(mate.name || ""), kind: STEP_HANDLE_KIND_BY_DOF_KIND[mate.kind] }];
}

/**
 * The mate DOFs of a STEP's kinematics a person can drive. A DOF a coupling
 * drives is one of them: a coupling has no axis to hang a handle on, so a geared
 * member keeps its handle and writes THROUGH its coupling, as its slider does.
 */
export function stepPosableDofs(definition) {
  return kinematicsMates(stepKinematicsBlock(definition))
    .flatMap((mate) => mateDofs(mate).map((dof) => ({ ...dof, mate })))
    .filter((dof) => dof.id && dof.kind && definition?.parameterMap?.[dof.id]);
}

function mateAxis(mate) {
  const origin = Array.isArray(mate?.axis?.origin) ? mate.axis.origin.map(Number) : [];
  const dir = normalize(Array.isArray(mate?.axis?.dir) ? mate.axis.dir.map(Number) : []);
  return origin.length === 3 && origin.every(Number.isFinite) && dir ? { origin, dir } : null;
}

// D(axis, q) in world-at-rest space, as `kinematicsRuntime.js` builds it: the
// turn about the axis line, then the travel along it.
function mateMotion(mate, effective) {
  const axis = mateAxis(mate);
  if (!axis || mate.kind === "fastened") return translationTransform(0, 0, 0);
  const dofValue = (kind) => Number(effective[mateDofs(mate).find((dof) => dof.kind === kind)?.id]) || 0;
  const turnDeg = dofValue("revolute");
  const travel = dofValue("prismatic");
  const turn = multiplyTransforms(
    multiplyTransforms(translationTransform(...axis.origin), axisAngleTransform(axis.dir, (turnDeg * Math.PI) / 180)),
    translationTransform(...scale(axis.origin, -1))
  );
  return multiplyTransforms(translationTransform(...scale(axis.dir, travel)), turn);
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

/**
 * Handles for a posed STEP. A mate's axis is written in world-at-rest numbers;
 * the accumulated delta of its child (its parents' motion, then its own)
 * carries pivot, axis and arm to where the child now is, for a chain of any depth.
 * `features` are the definition's resolved features (`resolveStepModuleFeatures`
 * over the REST mesh): a mated child's label names its parts, hence its centre.
 */
export function stepJointHandles({ definition, parameterValues, features, onParameterChange }) {
  const block = stepKinematicsBlock(definition);
  const dofs = stepPosableDofs(definition);
  if (!dofs.length) return [];
  const effective = effectiveDofValues(block, parameterValues);
  const driven = poseDrivenDofs(definition);
  const limits = new Map(kinematicsDofs(block).map((dof) => [dof.id, dof.limits]));
  const mateByChild = new Map(kinematicsMates(block).map((mate) => [mate.child, mate]));
  const deltas = new Map();
  const deltaFor = (mate, visiting = new Set()) => {
    if (deltas.has(mate)) return deltas.get(mate);
    const parent = mateByChild.get(mate.parent);
    // The authoring layer guarantees a tree; a cycle here must not hang the viewer.
    const parentDelta = parent && !visiting.has(parent) ? deltaFor(parent, new Set(visiting).add(mate)) : null;
    const motion = mateMotion(mate, effective);
    const delta = parentDelta ? multiplyTransforms(parentDelta, motion) : motion;
    deltas.set(mate, delta);
    return delta;
  };
  const located = dofs.map((dof) => ({ dof, axis: mateAxis(dof.mate) })).filter(({ axis }) => axis);
  const arms = spreadCoincidentArms(located.map(({ dof, axis }) => {
    const feature = features?.[String(dof.mate.child || "").replace(/^#/, "")];
    const centre = feature && !feature.missing && Array.isArray(feature.center) ? subtract(feature.center, axis.origin) : null;
    return { ...axis, arm: dof.kind === "prismatic" ? axis.dir : armOffset(axis.dir, centre) };
  }));
  const handles = [];
  for (const [index, { dof, axis }] of located.entries()) {
    const delta = deltaFor(dof.mate);
    const prismatic = dof.kind === "prismatic";
    const dofLimits = limits.get(dof.id);
    handles.push({
      id: dof.id,
      label: dof.id,
      kind: dof.kind,
      pivot: transformPoint(delta, axis.origin),
      axis: normalize(transformDirection(delta, axis.dir)),
      toward: prismatic ? null : transformPoint(delta, add(axis.origin, arms[index])),
      value: Number(effective[dof.id]) || 0,
      min: Array.isArray(dofLimits) ? Math.min(...dofLimits.map(Number)) : null,
      max: Array.isArray(dofLimits) ? Math.max(...dofLimits.map(Number)) : null,
      unit: prismatic ? "mm" : "deg",
      onChange: (value) => {
        const write = poseControlWrite({ driven, values: parameterValues, parameterId: dof.id, value });
        onParameterChange(write.id, write.value);
      }
    });
  }
  return handles;
}

import { clampJointValueDeg, linkOriginInFrame } from "./kinematics.js";

const MOTION_LIMIT_EPSILON = 1e-6;

function isPlainObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function isAngularJoint(joint) {
  const jointType = String(joint?.type || "fixed");
  return jointType === "continuous" || jointType === "revolute";
}

export function nativeJointValueToDisplay(joint, value) {
  const numericValue = toFiniteNumber(value, 0);
  return isAngularJoint(joint) ? (numericValue * 180) / Math.PI : numericValue;
}

// Used by jointValuesByNameToNative below; exported for tests.
export function displayJointValueToNative(joint, value) {
  const numericValue = toFiniteNumber(value, 0);
  return isAngularJoint(joint) ? (numericValue * Math.PI) / 180 : numericValue;
}

export function jointValuesByNameToNative(urdfData, jointValuesByName) {
  const joints = Array.isArray(urdfData?.joints) ? urdfData.joints : [];
  const jointByName = new Map(joints.map((joint) => [String(joint?.name || ""), joint]).filter(([name]) => name));
  const nativeValues = {};
  for (const [name, value] of Object.entries(jointValuesByName || {})) {
    const jointName = String(name || "").trim();
    const joint = jointByName.get(jointName);
    if (jointName && joint) {
      nativeValues[jointName] = displayJointValueToNative(joint, value);
    }
  }
  return nativeValues;
}

export function normalizeMotionTargetPosition(value, fallback = [0, 0, 0]) {
  const source = Array.isArray(value) ? value : fallback;
  return [0, 1, 2].map((index) => toFiniteNumber(source[index], fallback[index] ?? 0));
}

// Used by measureUrdfMotionResult below; exported for tests.
export function positionDistance(left, right) {
  const a = normalizeMotionTargetPosition(left);
  const b = normalizeMotionTargetPosition(right);
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

export function validateUrdfMotionJointValues(urdfData, jointValuesByName, { native = false } = {}) {
  if (!isPlainObject(jointValuesByName)) {
    throw new Error("motion result jointValuesByName must be an object");
  }
  const joints = Array.isArray(urdfData?.joints) ? urdfData.joints : [];
  const jointByName = new Map(joints.map((joint) => [String(joint?.name || ""), joint]).filter(([name]) => name));
  const validated = {};
  for (const [name, rawValue] of Object.entries(jointValuesByName)) {
    const jointName = String(name || "").trim();
    if (!jointName) {
      throw new Error("motion result includes an empty joint name");
    }
    const joint = jointByName.get(jointName);
    if (!joint) {
      throw new Error(`motion result references unknown joint ${jointName}`);
    }
    const jointType = String(joint?.type || "fixed");
    if (jointType === "fixed") {
      throw new Error(`motion result cannot set fixed joint ${jointName}`);
    }
    if (joint?.mimic) {
      throw new Error(`motion result cannot set mimic joint ${jointName}`);
    }
    const rawNumericValue = Number(rawValue);
    if (!Number.isFinite(rawNumericValue)) {
      throw new Error(`motion result joint ${jointName} must be a finite number`);
    }
    const numericValue = native ? nativeJointValueToDisplay(joint, rawNumericValue) : rawNumericValue;
    const clampedValue = clampJointValueDeg(joint, numericValue);
    if (jointType !== "continuous" && Math.abs(clampedValue - numericValue) > MOTION_LIMIT_EPSILON) {
      throw new Error(`motion result joint ${jointName} must stay within joint limits`);
    }
    validated[jointName] = numericValue;
  }
  return validated;
}

export function validateUrdfMotionTrajectory(urdfData, trajectory) {
  if (!isPlainObject(trajectory)) {
    throw new Error("motion result trajectory must be an object");
  }
  const rawJointNames = Array.isArray(trajectory.jointNames) ? trajectory.jointNames : [];
  const jointNames = rawJointNames.map((name) => String(name || "").trim()).filter(Boolean);
  if (!jointNames.length) {
    throw new Error("motion result trajectory.jointNames must be a non-empty array");
  }
  const rawPoints = Array.isArray(trajectory.points) ? trajectory.points : [];
  if (!rawPoints.length) {
    throw new Error("motion result trajectory.points must be a non-empty array");
  }
  let previousTime = -Number.EPSILON;
  const points = rawPoints.map((point, pointIndex) => {
    if (!isPlainObject(point)) {
      throw new Error(`motion result trajectory point ${pointIndex + 1} must be an object`);
    }
    const timeFromStartSec = Number(point.timeFromStartSec);
    if (!Number.isFinite(timeFromStartSec) || timeFromStartSec < 0 || timeFromStartSec < previousTime) {
      throw new Error("motion result trajectory times must be finite, non-negative, and sorted");
    }
    previousTime = timeFromStartSec;
    const hasNativePositions = Array.isArray(point.positions);
    const nativePositions = hasNativePositions ? point.positions.map((value) => Number(value)) : [];
    if (hasNativePositions && (nativePositions.length !== jointNames.length || nativePositions.some((value) => !Number.isFinite(value)))) {
      throw new Error("motion result trajectory positions must match trajectory.jointNames");
    }
    const positionsDeg = hasNativePositions
      ? nativePositions.map((value, index) => {
        const joint = (Array.isArray(urdfData?.joints) ? urdfData.joints : []).find((candidate) => String(candidate?.name || "") === jointNames[index]);
        return nativeJointValueToDisplay(joint, value);
      })
      : (Array.isArray(point.positionsDeg) ? point.positionsDeg.map((value) => Number(value)) : []);
    if (positionsDeg.length !== jointNames.length || positionsDeg.some((value) => !Number.isFinite(value))) {
      throw new Error("motion result trajectory positions must match trajectory.jointNames");
    }
    const positionsByNameDeg = Object.fromEntries(jointNames.map((jointName, index) => [jointName, positionsDeg[index]]));
    validateUrdfMotionJointValues(urdfData, positionsByNameDeg);
    return {
      timeFromStartSec,
      positions: hasNativePositions ? nativePositions : null,
      positionsDeg,
      positionsByName: hasNativePositions ? Object.fromEntries(jointNames.map((jointName, index) => [jointName, nativePositions[index]])) : null,
      positionsByNameDeg
    };
  });
  return {
    jointNames,
    points
  };
}

export function measureUrdfMotionResult(urdfData, jointValuesByName, endEffector, targetPosition) {
  const actualPosition = linkOriginInFrame(
    urdfData,
    jointValuesByName,
    endEffector?.link,
    endEffector?.frame
  );
  if (!actualPosition) {
    return {
      actualPosition: null,
      positionError: Number.POSITIVE_INFINITY
    };
  }
  return {
    actualPosition,
    positionError: positionDistance(actualPosition, targetPosition)
  };
}

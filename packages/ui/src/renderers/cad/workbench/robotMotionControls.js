import { jointValueMapsClose } from "@hardcore/core/lib/urdf/jointAnimation.js";
import { nativeJointValueToDisplay } from "@hardcore/core/lib/urdf/motion.js";
import { toFiniteNumber } from "./valueUtils.js";

export function cloneJointValueMap(values) {
  if (!values || typeof values !== "object") {
    return {};
  }
  return Object.fromEntries(
    Object.entries(values)
      .map(([name, value]) => [String(name || "").trim(), toFiniteNumber(value, 0)])
      .filter(([name]) => name)
  );
}

export function srdfGroupStateJointValuesToDisplay(urdfData, jointValuesByName) {
  if (!jointValuesByName || typeof jointValuesByName !== "object") {
    return {};
  }
  const joints = Array.isArray(urdfData?.joints) ? urdfData.joints : [];
  const jointByName = new Map(joints.map((joint) => [String(joint?.name || ""), joint]).filter(([name]) => name));
  return Object.fromEntries(
    Object.entries(jointValuesByName)
      .map(([name, value]) => {
        const jointName = String(name || "").trim();
        const joint = jointByName.get(jointName);
        return jointName && joint ? [jointName, nativeJointValueToDisplay(joint, value)] : null;
      })
      .filter(Boolean)
  );
}

export function srdfHomeGroupStateJointValuesToDisplay(urdfData) {
  const groupStates = Array.isArray(urdfData?.srdf?.groupStates)
    ? urdfData.srdf.groupStates
    : Array.isArray(urdfData?.motion?.groupStates)
      ? urdfData.motion.groupStates
      : [];
  return groupStates.reduce((homeValues, state) => {
    if (String(state?.name || "").trim().toLowerCase() !== "home") {
      return homeValues;
    }
    const jointValuesByName = srdfGroupStateJointValuesToDisplay(
      urdfData,
      state?.jointValuesByName || state?.jointValuesByNameRad
    );
    return {
      ...homeValues,
      ...jointValuesByName
    };
  }, {});
}

export function jointValueSubsetClose(values, subset) {
  const targetValues = cloneJointValueMap(subset);
  const targetNames = Object.keys(targetValues);
  if (!targetNames.length) {
    return false;
  }
  const currentValues = Object.fromEntries(targetNames.map((name) => [name, values?.[name]]));
  return jointValueMapsClose(currentValues, targetValues);
}

export function findBestMatchingJointValueState(states, currentValues, defaultValues = {}) {
  const normalizedStates = Array.isArray(states) ? states : [];
  const normalizedCurrentValues = cloneJointValueMap(currentValues);
  const normalizedDefaultValues = cloneJointValueMap(defaultValues);
  const defaultJointNames = new Set([
    ...Object.keys(normalizedCurrentValues),
    ...Object.keys(normalizedDefaultValues)
  ]);
  let bestState = null;
  let bestJointCount = 0;

  for (const state of normalizedStates) {
    const stateValues = cloneJointValueMap(state?.jointValuesByName);
    const stateJointNames = Object.keys(stateValues);
    if (!stateJointNames.length || !jointValueSubsetClose(normalizedCurrentValues, stateValues)) {
      continue;
    }
    const outsideJointNames = [...defaultJointNames].filter((name) => !Object.hasOwn(stateValues, name));
    const outsideCurrentValues = Object.fromEntries(outsideJointNames.map((name) => [name, normalizedCurrentValues[name] ?? 0]));
    const outsideDefaultValues = Object.fromEntries(outsideJointNames.map((name) => [name, normalizedDefaultValues[name] ?? 0]));
    if (!jointValueMapsClose(outsideCurrentValues, outsideDefaultValues)) {
      continue;
    }
    if (stateJointNames.length > bestJointCount) {
      bestState = state;
      bestJointCount = stateJointNames.length;
    }
  }

  return bestState;
}

export function interpolateTrajectoryJointValues(trajectory, elapsedSec, fallbackValues = {}) {
  const points = Array.isArray(trajectory?.points) ? trajectory.points : [];
  if (!points.length) {
    return cloneJointValueMap(fallbackValues);
  }
  const firstPoint = points[0];
  if (elapsedSec <= toFiniteNumber(firstPoint.timeFromStartSec, 0)) {
    return {
      ...cloneJointValueMap(fallbackValues),
      ...cloneJointValueMap(firstPoint.positionsByNameDeg)
    };
  }
  for (let index = 1; index < points.length; index += 1) {
    const previousPoint = points[index - 1];
    const nextPoint = points[index];
    const previousTime = toFiniteNumber(previousPoint.timeFromStartSec, 0);
    const nextTime = toFiniteNumber(nextPoint.timeFromStartSec, previousTime);
    if (elapsedSec > nextTime) {
      continue;
    }
    const span = Math.max(nextTime - previousTime, 1e-6);
    const progress = Math.min(Math.max((elapsedSec - previousTime) / span, 0), 1);
    const previousValues = cloneJointValueMap(previousPoint.positionsByNameDeg);
    const nextValues = cloneJointValueMap(nextPoint.positionsByNameDeg);
    const interpolated = {};
    for (const [jointName, nextValue] of Object.entries(nextValues)) {
      const previousValue = Object.hasOwn(previousValues, jointName) ? previousValues[jointName] : nextValue;
      interpolated[jointName] = previousValue + ((nextValue - previousValue) * progress);
    }
    return {
      ...cloneJointValueMap(fallbackValues),
      ...interpolated
    };
  }
  return {
    ...cloneJointValueMap(fallbackValues),
    ...cloneJointValueMap(points[points.length - 1].positionsByNameDeg)
  };
}

export function roundedUrdfJointValue(value) {
  const numericValue = toFiniteNumber(value, 0);
  const rounded = Math.round(numericValue * 1000) / 1000;
  return Object.is(rounded, -0) ? 0 : rounded;
}

export function normalizePoint3(value) {
  if (!Array.isArray(value) || value.length < 3) {
    return null;
  }
  const point = [Number(value[0]), Number(value[1]), Number(value[2])];
  return point.every(Number.isFinite) ? point : null;
}

export function buildUrdfJointAnglesCopyText(joints, jointValues) {
  const movableJoints = Array.isArray(joints) ? joints : [];
  return JSON.stringify(
    Object.fromEntries(
      movableJoints.map((joint) => {
        const jointName = String(joint?.name || "").trim();
        const value = roundedUrdfJointValue(jointValues?.[jointName] ?? joint?.defaultValueDeg ?? 0);
        return [jointName, value];
      }).filter(([name]) => name)
    ),
    null,
    2
  );
}

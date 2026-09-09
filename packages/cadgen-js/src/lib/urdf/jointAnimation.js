export const URDF_JOINT_ANIMATION_DURATION_MS = 840;
export const URDF_JOINT_ANIMATION_FOLLOW_MS = 240;
export const URDF_JOINT_ANIMATION_EPSILON = 0.001;

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function clampUnit(value) {
  return Math.min(Math.max(toFiniteNumber(value, 1), 0), 1);
}

function normalizedJointValueEntries(values) {
  if (!values || typeof values !== "object") {
    return [];
  }
  return Object.entries(values)
    .map(([name, value]) => [String(name || "").trim(), toFiniteNumber(value, 0)])
    .filter(([name]) => name)
    .sort(([leftName], [rightName]) => leftName.localeCompare(rightName));
}

function wrappedJointSetHas(wrappedJointNames, name) {
  if (!name || !wrappedJointNames) {
    return false;
  }
  if (wrappedJointNames instanceof Set || wrappedJointNames instanceof Map) {
    return wrappedJointNames.has(name);
  }
  return !!wrappedJointNames?.[name];
}

function wrapAngleDeltaDeg(deltaDeg) {
  const numericDelta = toFiniteNumber(deltaDeg, 0);
  const wrapped = ((((numericDelta + 180) % 360) + 360) % 360) - 180;
  return wrapped === -180 && numericDelta > 0 ? 180 : wrapped;
}

function animatedJointDeltaDeg(name, currentValue, targetValue, wrappedJointNames) {
  const numericCurrent = toFiniteNumber(currentValue, 0);
  const numericTarget = toFiniteNumber(targetValue, numericCurrent);
  if (!wrappedJointSetHas(wrappedJointNames, name)) {
    return numericTarget - numericCurrent;
  }
  return wrapAngleDeltaDeg(numericTarget - numericCurrent);
}

export function easeUrdfJointAnimation(progress) {
  const t = clampUnit(progress);
  return (t * t * t) * (t * ((6 * t) - 15) + 10);
}

export function jointValueMapsClose(left, right, epsilon = URDF_JOINT_ANIMATION_EPSILON) {
  const leftEntries = normalizedJointValueEntries(left);
  const rightEntries = normalizedJointValueEntries(right);
  if (leftEntries.length !== rightEntries.length) {
    return false;
  }
  for (let index = 0; index < rightEntries.length; index += 1) {
    const [leftName, leftValue] = leftEntries[index];
    const [rightName, rightValue] = rightEntries[index];
    if (leftName !== rightName || Math.abs(leftValue - rightValue) > epsilon) {
      return false;
    }
  }
  return true;
}

export function interpolateUrdfJointValues(
  startValues,
  targetValues,
  progress,
  epsilon = URDF_JOINT_ANIMATION_EPSILON,
  wrappedJointNames = null
) {
  const targetEntries = normalizedJointValueEntries(targetValues);
  const startByName = new Map(normalizedJointValueEntries(startValues));
  const easedProgress = easeUrdfJointAnimation(progress);
  const values = {};
  let done = true;

  for (const [name, targetValue] of targetEntries) {
    const startValue = startByName.has(name) ? startByName.get(name) : targetValue;
    const deltaValue = animatedJointDeltaDeg(name, startValue, targetValue, wrappedJointNames);
    const interpolatedValue = startValue + (deltaValue * easedProgress);
    if (Math.abs(deltaValue * (1 - easedProgress)) <= epsilon || easedProgress >= 1) {
      values[name] = targetValue;
    } else {
      values[name] = interpolatedValue;
      done = false;
    }
  }

  return { values, done };
}

export function advanceUrdfJointValues(
  currentValues,
  targetValues,
  deltaMs,
  smoothingMs = URDF_JOINT_ANIMATION_FOLLOW_MS,
  epsilon = URDF_JOINT_ANIMATION_EPSILON,
  wrappedJointNames = null
) {
  const targetEntries = normalizedJointValueEntries(targetValues);
  const currentByName = new Map(normalizedJointValueEntries(currentValues));
  const safeDeltaMs = Math.max(toFiniteNumber(deltaMs, 0), 0);
  const safeSmoothingMs = Math.max(toFiniteNumber(smoothingMs, URDF_JOINT_ANIMATION_FOLLOW_MS), 1);
  const alpha = clampUnit(1 - Math.exp(-safeDeltaMs / safeSmoothingMs));
  const values = {};
  let done = true;

  for (const [name, targetValue] of targetEntries) {
    const currentValue = currentByName.has(name) ? currentByName.get(name) : targetValue;
    const deltaValue = animatedJointDeltaDeg(name, currentValue, targetValue, wrappedJointNames);
    const nextValue = currentValue + (deltaValue * alpha);
    if (Math.abs(deltaValue * (1 - alpha)) <= epsilon || alpha >= 1) {
      values[name] = targetValue;
    } else {
      values[name] = nextValue;
      done = false;
    }
  }

  return { values, done };
}

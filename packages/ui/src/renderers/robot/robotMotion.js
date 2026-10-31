// Two control values closer than this are the same value: below what a slider
// shows, above what float arithmetic leaves behind.
export const JOINT_VALUE_EPSILON = 0.001;

const toFiniteNumber = (value, fallback = 0) => (Number.isFinite(Number(value)) ? Number(value) : fallback);

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

function sortedEntries(values) {
  return Object.entries(cloneJointValueMap(values)).sort(([left], [right]) => left.localeCompare(right));
}

export function jointValueMapsClose(left, right, epsilon = JOINT_VALUE_EPSILON) {
  const leftEntries = sortedEntries(left);
  const rightEntries = sortedEntries(right);
  if (leftEntries.length !== rightEntries.length) return false;
  return leftEntries.every(([name, value], index) => name === rightEntries[index][0] && Math.abs(value - rightEntries[index][1]) <= epsilon);
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

/** The named pose (`{ id, values }`) the controls are IN: the largest one whose controls match, with
 * every other control at its default; null when none does. */
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
    const stateValues = cloneJointValueMap(state?.values);
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

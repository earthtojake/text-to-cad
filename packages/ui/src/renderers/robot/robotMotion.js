import { jointValueMapsClose } from "@hardcore/core/lib/urdf/jointValues.js";

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

import {
  normalizeStepModuleParameterValues
} from "./stepModule.js";

function isObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function rawParamsUseEnvelope(rawParams) {
  return isObject(rawParams) && isObject(rawParams.values);
}

export function hasStepParameterRenderValues(value) {
  return value !== undefined && value !== null;
}

function parameterMapForDefinition(definition) {
  return definition?.parameterMap && typeof definition.parameterMap === "object"
    ? definition.parameterMap
    : {};
}

function assertKnownParameterIds(definition, values, label) {
  const parameterMap = parameterMapForDefinition(definition);
  for (const key of Object.keys(isObject(values) ? values : {})) {
    if (!parameterMap[key]) {
      throw new Error(`Unknown STEP parameter in ${label}: ${key}`);
    }
  }
}

export function normalizeStepParameterRenderValues(definition, rawParams = {}) {
  if (!isObject(rawParams)) {
    throw new Error("STEP parameters must be a JSON object");
  }
  const rawValues = rawParamsUseEnvelope(rawParams) ? rawParams.values : rawParams;
  if (!isObject(rawValues)) {
    throw new Error("STEP parameters.values must be a JSON object");
  }
  assertKnownParameterIds(definition, rawValues, "kinematics");
  return {
    values: normalizeStepModuleParameterValues(definition, rawValues)
  };
}

export function stepParameterRenderValues(params) {
  return { ...(params?.values || {}) };
}

// A still render is a paused clip at t=0: modules that gate effects on
// playback state (meshing pulses, orbit guides) stay quiescent in stills.
export function stepParameterRenderState() {
  return {
    activeId: "params",
    playing: false,
    elapsedSec: 0,
    duration: 0,
    speed: 1,
    loop: false
  };
}

import {
  normalizeParameterAnimations,
  normalizeParameterDefinitions,
  normalizeParameterValues,
  parameterMapForDefinitions
} from "../../common/parameters.js";
import { createImplicitCadSdfEvaluator } from "./sdfEvaluator.js";
export {
  IMPLICIT_CAD_EXTENSIONS,
  IMPLICIT_CAD_KIND,
  IMPLICIT_CAD_SCHEMA,
  IMPLICIT_EXTENSIONS,
  IMPLICIT_KIND,
  IMPLICIT_SCHEMA
} from "./schema.js";
import {
  IMPLICIT_CAD_EXTENSIONS,
  IMPLICIT_CAD_KIND,
  IMPLICIT_CAD_SCHEMA
} from "./schema.js";

const DEFAULT_BOUNDS = Object.freeze({
  min: [-50, -50, -50],
  max: [50, 50, 50]
});
const AUTO_BOUNDS_RADII = Object.freeze([4, 8, 16, 32, 64, 128, 256, 512]);
const AUTO_BOUNDS_SCAN_SAMPLES = 5;
const AUTO_BOUNDS_REFINE_SAMPLES = 9;
const AUTO_BOUNDS_CACHE_LIMIT = 32;
const DEFAULT_COLOR = "#f4f4f5";
const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;
const GLSL_IDENTIFIER_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;
const UNIFORM_TYPES = Object.freeze(new Set(["float", "int", "bool", "vec2", "vec3", "vec4"]));
const PARAM_UNIFORM_TYPES = Object.freeze({
  number: "float",
  boolean: "bool",
  color: "vec3",
  button: "int"
});

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function finitePositiveNumber(value, fallback) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : fallback;
}

function finiteVec3(value, fallback) {
  const source = Array.isArray(value) || ArrayBuffer.isView(value) ? value : [];
  return [0, 1, 2].map((index) => finiteNumber(source[index], fallback[index] || 0));
}

function finiteVector(value, length, fallback = []) {
  const source = Array.isArray(value) || ArrayBuffer.isView(value) ? value : [];
  return Array.from({ length }, (_, index) => finiteNumber(source[index], fallback[index] || 0));
}

function normalizeBounds(value, fallback = DEFAULT_BOUNDS) {
  const radius = finitePositiveNumber(value, null);
  const raw = radius
    ? { min: [-radius, -radius, -radius], max: [radius, radius, radius] }
    : Array.isArray(value) && value.length >= 2
      ? { min: value[0], max: value[1] }
      : isObject(value)
        ? value
        : fallback;
  const min = finiteVec3(raw.min, DEFAULT_BOUNDS.min);
  const max = finiteVec3(raw.max, DEFAULT_BOUNDS.max);
  for (let axis = 0; axis < 3; axis += 1) {
    if (max[axis] <= min[axis]) {
      const center = (min[axis] + max[axis]) / 2;
      min[axis] = center - 0.5;
      max[axis] = center + 0.5;
    }
  }
  return { min, max };
}

function cloneBounds(bounds) {
  return {
    min: [...bounds.min],
    max: [...bounds.max]
  };
}

function hasExplicitBounds(value) {
  if (value === undefined || value === null) {
    return false;
  }
  if (String(value).trim().toLowerCase() === "auto") {
    return false;
  }
  return !(isObject(value) && value.auto === true);
}

function boundsSize(bounds) {
  return [
    bounds.max[0] - bounds.min[0],
    bounds.max[1] - bounds.min[1],
    bounds.max[2] - bounds.min[2],
  ];
}

function expandBounds(min, max, margin) {
  const safeMargin = Math.max(finiteNumber(margin, 0), 0.25);
  return normalizeBounds({
    min: [min[0] - safeMargin, min[1] - safeMargin, min[2] - safeMargin],
    max: [max[0] + safeMargin, max[1] + safeMargin, max[2] + safeMargin]
  });
}

function sampleAutoBounds(sdf, bounds, samples) {
  const size = boundsSize(bounds);
  const steps = size.map((axisSize) => axisSize / Math.max(samples - 1, 1));
  const threshold = Math.max(Math.min(...steps) * 0.35, 0.002);
  const hitMin = [Infinity, Infinity, Infinity];
  const hitMax = [-Infinity, -Infinity, -Infinity];
  let hitCount = 0;
  let boundaryTouch = false;

  for (let iz = 0; iz < samples; iz += 1) {
    const z = bounds.min[2] + steps[2] * iz;
    for (let iy = 0; iy < samples; iy += 1) {
      const y = bounds.min[1] + steps[1] * iy;
      for (let ix = 0; ix < samples; ix += 1) {
        const x = bounds.min[0] + steps[0] * ix;
        const value = finiteNumber(sdf(x, y, z), 1e6);
        if (value > threshold) {
          continue;
        }
        hitCount += 1;
        hitMin[0] = Math.min(hitMin[0], x);
        hitMin[1] = Math.min(hitMin[1], y);
        hitMin[2] = Math.min(hitMin[2], z);
        hitMax[0] = Math.max(hitMax[0], x);
        hitMax[1] = Math.max(hitMax[1], y);
        hitMax[2] = Math.max(hitMax[2], z);
        if (value <= 0 && (
          ix === 0 || iy === 0 || iz === 0 ||
          ix === samples - 1 || iy === samples - 1 || iz === samples - 1
        )) {
          boundaryTouch = true;
        }
      }
    }
  }

  return {
    hitCount,
    hitMin,
    hitMax,
    boundaryTouch,
    step: steps,
    threshold
  };
}

function estimateAutoBoundsStartRadius(definition, params) {
  const largest = definition.parameters
    .filter((parameter) => parameter.type === "number")
    .filter((parameter) => !likelyPoseParameter(parameter))
    .reduce((maxValue, parameter) => {
      const value = Math.abs(finiteNumber(params[parameter.id], 0));
      return Math.max(maxValue, value);
    }, 1);
  const target = Math.max(largest * 3, 4);
  return AUTO_BOUNDS_RADII.find((radius) => radius >= target) || AUTO_BOUNDS_RADII[AUTO_BOUNDS_RADII.length - 1];
}

function estimateImplicitCadAutoBounds(partialModel, definition, context) {
  let sdf = null;
  try {
    sdf = createImplicitCadSdfEvaluator(partialModel);
  } catch {
    return cloneBounds(DEFAULT_BOUNDS);
  }

  let candidate = null;
  const startRadius = estimateAutoBoundsStartRadius(definition, context.params);
  for (const radius of AUTO_BOUNDS_RADII.filter((candidateRadius) => candidateRadius >= startRadius)) {
    const bounds = normalizeBounds(radius);
    const scan = sampleAutoBounds(sdf, bounds, AUTO_BOUNDS_SCAN_SAMPLES);
    if (!scan.hitCount) {
      continue;
    }
    const margin = Math.max(Math.max(...scan.step) * 1.5, radius * 0.06, 0.5);
    candidate = expandBounds(scan.hitMin, scan.hitMax, margin);
    if (!scan.boundaryTouch) {
      break;
    }
  }

  if (!candidate) {
    return cloneBounds(DEFAULT_BOUNDS);
  }

  for (let pass = 0; pass < 1; pass += 1) {
    const scan = sampleAutoBounds(sdf, candidate, AUTO_BOUNDS_REFINE_SAMPLES);
    if (!scan.hitCount) {
      break;
    }
    const margin = Math.max(Math.max(...scan.step) * 1.1, Math.max(...boundsSize(candidate)) * 0.025, 0.25);
    candidate = expandBounds(scan.hitMin, scan.hitMax, margin);
  }

  return candidate;
}

function likelyPoseParameter(parameter) {
  const unit = String(parameter?.unit || "").trim().toLowerCase();
  if (unit === "deg" || unit === "rad") {
    return true;
  }
  const text = `${parameter?.id || ""} ${parameter?.label || ""}`.toLowerCase();
  return [
    "angle",
    "phase",
    "rotation",
    "rotate",
    "orbit",
    "spin",
    "yaw",
    "pitch",
    "roll"
  ].some((token) => text.includes(token));
}

function autoBoundsCacheKey(definition, params, glslSource) {
  const values = definition.parameters
    .filter((parameter) => !likelyPoseParameter(parameter))
    .filter((parameter) => PARAM_UNIFORM_TYPES[parameter.type])
    .filter((parameter) => parameter.type !== "color")
    .map((parameter) => {
      const value = params[parameter.id];
      if (typeof value === "number") {
        return `${parameter.id}:${Number.isFinite(value) ? value.toPrecision(8) : "0"}`;
      }
      if (typeof value === "boolean") {
        return `${parameter.id}:${value ? "1" : "0"}`;
      }
      return `${parameter.id}:${String(value ?? "")}`;
    })
    .join(";");
  return `${glslSource.length}:${values}`;
}

function readCachedAutoBounds(cache, key, animationPlaying) {
  if (!cache) {
    return null;
  }
  if (cache.map.has(key)) {
    return cloneBounds(cache.map.get(key));
  }
  if (animationPlaying && cache.last) {
    return cloneBounds(cache.last);
  }
  return null;
}

function rememberAutoBounds(cache, key, bounds) {
  if (!cache) {
    return;
  }
  const cloned = cloneBounds(bounds);
  cache.map.set(key, cloned);
  cache.last = cloned;
  while (cache.map.size > AUTO_BOUNDS_CACHE_LIMIT) {
    const oldestKey = cache.map.keys().next().value;
    cache.map.delete(oldestKey);
  }
}

function resolveImplicitCadBounds(value, partialModel, definition, context, cache) {
  if (hasExplicitBounds(value)) {
    return {
      bounds: normalizeBounds(value),
      source: "explicit"
    };
  }
  const key = autoBoundsCacheKey(definition, context.params, partialModel.glslSource);
  const cached = readCachedAutoBounds(cache, key, context.animationState.playing);
  if (cached) {
    return {
      bounds: cached,
      source: "auto"
    };
  }
  const estimated = estimateImplicitCadAutoBounds(partialModel, definition, context);
  rememberAutoBounds(cache, key, estimated);
  return {
    bounds: estimated,
    source: "auto"
  };
}

function normalizeHexColor(value, fallback = DEFAULT_COLOR) {
  const color = String(value || "").trim();
  return HEX_COLOR_PATTERN.test(color) ? color : fallback;
}

function hexToRgb01(hex, fallback = DEFAULT_COLOR) {
  const value = normalizeHexColor(hex, fallback);
  const expanded = value.length === 4
    ? `${value[1]}${value[1]}${value[2]}${value[2]}${value[3]}${value[3]}`
    : value.slice(1);
  return [
    parseInt(expanded.slice(0, 2), 16) / 255,
    parseInt(expanded.slice(2, 4), 16) / 255,
    parseInt(expanded.slice(4, 6), 16) / 255,
  ];
}

function evaluateValue(value, context) {
  return typeof value === "function" ? value(context) : value;
}

function normalizeMaterial() {
  const material = {};
  return {
    color: normalizeHexColor(material.color, DEFAULT_COLOR),
    roughness: Math.min(Math.max(finiteNumber(material.roughness, 0.75), 0), 1),
    metalness: Math.min(Math.max(finiteNumber(material.metalness, 0.02), 0), 1),
  };
}

function unwrapModuleExports(moduleValue) {
  if (typeof moduleValue === "function") {
    return moduleValue();
  }
  if (!isObject(moduleValue)) {
    return moduleValue;
  }
  if (moduleValue.default !== undefined) {
    return typeof moduleValue.default === "function" ? moduleValue.default() : moduleValue.default;
  }
  if (moduleValue.model !== undefined) {
    return typeof moduleValue.model === "function" ? moduleValue.model() : moduleValue.model;
  }
  return moduleValue;
}

function normalizeUniformValue(rawValue, context = {}) {
  const raw = evaluateValue(rawValue, context);
  const value = isObject(raw) && Object.hasOwn(raw, "value")
    ? evaluateValue(raw.value, context)
    : raw;
  const explicitType = isObject(raw) ? String(raw.type || raw.kind || "").trim().toLowerCase() : "";
  const type = UNIFORM_TYPES.has(explicitType)
    ? explicitType
    : typeof value === "boolean"
      ? "bool"
      : typeof value === "number"
        ? "float"
        : typeof value === "string" && HEX_COLOR_PATTERN.test(value)
          ? "vec3"
          : Array.isArray(value) || ArrayBuffer.isView(value)
            ? `vec${Math.min(Math.max(value.length, 2), 4)}`
            : "";
  if (!UNIFORM_TYPES.has(type)) {
    return null;
  }
  if (type === "bool") {
    return { type, value: value === true };
  }
  if (type === "int") {
    return { type, value: Math.trunc(finiteNumber(value, 0)) };
  }
  if (type === "float") {
    return { type, value: finiteNumber(value, 0) };
  }
  if (typeof value === "string" && HEX_COLOR_PATTERN.test(value)) {
    return { type, value: hexToRgb01(value) };
  }
  const length = Number(type.slice(3));
  const fallback = Array.from({ length }, () => 0);
  return {
    type,
    value: finiteVector(value, length, fallback)
  };
}

function uniformsFromParams(parameters = [], params = {}) {
  return Object.fromEntries(
    parameters
      .map((parameter) => {
        const uniformName = String(parameter?.id || "").trim();
        if (!GLSL_IDENTIFIER_PATTERN.test(uniformName) || uniformName.startsWith("gl_")) {
          throw new Error(`Implicit CAD param "${uniformName}" is not a valid GLSL uniform identifier.`);
        }
        const type = PARAM_UNIFORM_TYPES[parameter.type];
        if (!type) {
          return null;
        }
        const uniform = normalizeUniformValue({ type, value: params[parameter.id] });
        return uniform ? [uniformName, uniform] : null;
      })
      .filter(Boolean)
  );
}

function glslSourceFromModel(model, context = {}) {
  return String(evaluateValue(model.glsl ?? model.glslSource, context) || "").trim();
}

export function pathIsImplicitCadSource(value = "") {
  const pathname = String(value || "").split(/[?#]/, 1)[0].toLowerCase();
  return IMPLICIT_CAD_EXTENSIONS.some((extension) => pathname.endsWith(extension));
}

function normalizeAnimationState(value = {}) {
  const activeId = String(value?.activeId || "").trim();
  return {
    activeId,
    playing: value?.playing === true,
    elapsedSec: Math.max(finiteNumber(value?.elapsedSec ?? value?.elapsed, 0), 0),
    speed: Math.min(Math.max(finiteNumber(value?.speed, 1), 0.1), 5)
  };
}

function findAnimation(definition, animationId) {
  const animations = Array.isArray(definition?.animations) ? definition.animations : [];
  if (!animations.length) {
    return null;
  }
  const normalizedId = String(animationId || "").trim();
  return animations.find((animation) => animation.id === normalizedId) || animations[0] || null;
}

function buildImplicitCadContext(definition, parameterValues = {}, animationState = {}) {
  const params = normalizeParameterValues(definition, parameterValues);
  const normalizedAnimationState = normalizeAnimationState(animationState);
  const animation = findAnimation(definition, normalizedAnimationState.activeId);
  const duration = Math.max(Number(animation?.duration) || 0, 0.001);
  const elapsedSec = Math.min(normalizedAnimationState.elapsedSec, duration);
  const progress = animation ? Math.min(Math.max(elapsedSec / duration, 0), 1) : 0;
  return {
    ...params,
    params,
    parameterValues: params,
    animation,
    animationState: {
      ...normalizedAnimationState,
      activeId: animation?.id || normalizedAnimationState.activeId,
      duration: animation?.duration || 0,
      loop: animation?.loop !== false
    },
    elapsed: elapsedSec,
    elapsedSec,
    duration: animation?.duration || 0,
    progress,
    cycle: duration > 0 ? elapsedSec / duration : 0,
    t: elapsedSec,
    time: elapsedSec
  };
}

function normalizeImplicitCadRuntimeModel(rawModel, definition, parameterValues = {}, animationState = {}, { sourceUrl = "", autoBoundsCache = null } = {}) {
  const context = buildImplicitCadContext(definition, parameterValues, animationState);
  const model = rawModel;
  if (!isObject(model)) {
    throw new Error("Implicit CAD module must export an object, or a function returning an object.");
  }
  const uniforms = uniformsFromParams(definition.parameters, context.params);
  const glslSource = glslSourceFromModel(model, context);
  if (!glslSource) {
    throw new Error("Implicit CAD module must export GLSL code in glsl.");
  }
  const resolvedBounds = resolveImplicitCadBounds(
    evaluateValue(model.bounds, context),
    { glslSource, uniforms },
    definition,
    context,
    autoBoundsCache
  );
  const bounds = resolvedBounds.bounds;
  const size = [
    bounds.max[0] - bounds.min[0],
    bounds.max[1] - bounds.min[1],
    bounds.max[2] - bounds.min[2],
  ];
  const center = [
    (bounds.min[0] + bounds.max[0]) / 2,
    (bounds.min[1] + bounds.max[1]) / 2,
    (bounds.min[2] + bounds.max[2]) / 2,
  ];
  const radius = Math.max(Math.hypot(size[0], size[1], size[2]) / 2, 1e-3);
  const evaluatedRender = evaluateValue(model.render, context);
  const render = isObject(evaluatedRender) ? evaluatedRender : {};
  const epsilon = finitePositiveNumber(evaluateValue(render.epsilon, context), Math.max(radius * 0.0007, 0.002));
  const normalEpsilon = finitePositiveNumber(
    evaluateValue(render.normalEpsilon, context),
    Math.max(epsilon * 2.5, radius * 0.001)
  );
  const stepScale = Math.min(
    Math.max(finiteNumber(evaluateValue(render.stepScale, context), 0.45), 0.05),
    1
  );
  const maxStep = finitePositiveNumber(
    evaluateValue(render.maxStep, context),
    Math.max(radius * 0.035, epsilon * 10)
  );
  return {
    schema: String(model.schema || IMPLICIT_CAD_SCHEMA),
    kind: IMPLICIT_CAD_KIND,
    name: String(model.name || model.title || "Implicit CAD").trim() || "Implicit CAD",
    description: String(model.description || "").trim(),
    units: String(model.units || "mm").trim() || "mm",
    sourceUrl: String(sourceUrl || model.sourceUrl || "").trim(),
    parameters: definition.parameters,
    parameterMap: definition.parameterMap,
    defaultParameterValues: definition.defaultParameterValues,
    parameterValues: context.params,
    animations: definition.animations,
    animationState: context.animationState,
    glslSource,
    distanceSource: glslSource,
    colorSource: /\bvec3\s+color\s*\(/.test(glslSource) ? glslSource : "",
    uniforms,
    uniformSignature: Object.entries(uniforms)
      .map(([name, uniform]) => `${name}:${uniform.type}`)
      .sort()
      .join(";"),
    bounds,
    boundsSource: resolvedBounds.source,
    center,
    size,
    radius,
    material: normalizeMaterial(),
    background: {},
    maxSteps: Math.max(16, Math.min(Math.floor(finiteNumber(evaluateValue(render.steps, context), 192)), 768)),
    maxDistance: finitePositiveNumber(evaluateValue(render.maxDistance, context), radius * 8),
    stepScale,
    maxStep,
    epsilon,
    normalEpsilon,
  };
}

export function normalizeImplicitCadDefinition(moduleValue, { sourceUrl = "" } = {}) {
  const model = unwrapModuleExports(moduleValue);
  if (!isObject(model)) {
    throw new Error("Implicit CAD module must export an object, or a function returning an object.");
  }
  if (model.kind === IMPLICIT_CAD_KIND && model.glslSource && Array.isArray(model.parameters)) {
    return model.definition ? model : { ...model, definition: null };
  }
  const parameters = normalizeParameterDefinitions(model.params);
  const parameterMap = parameterMapForDefinitions(parameters);
  const autoBoundsCache = {
    map: new Map(),
    last: null
  };
  const definition = {
    schema: String(model.schema || IMPLICIT_CAD_SCHEMA),
    kind: IMPLICIT_CAD_KIND,
    name: String(model.name || model.title || "Implicit CAD").trim() || "Implicit CAD",
    description: String(model.description || "").trim(),
    units: String(model.units || "mm").trim() || "mm",
    sourceUrl: String(sourceUrl || model.sourceUrl || "").trim(),
    parameters,
    parameterMap,
    defaultParameterValues: {},
    animations: normalizeParameterAnimations(model.animations),
    buildModel(parameterValues = {}, animationState = {}) {
      return normalizeImplicitCadRuntimeModel(model, definition, parameterValues, animationState, { sourceUrl, autoBoundsCache });
    }
  };
  definition.defaultParameterValues = normalizeParameterValues(
    definition,
    model.values || {}
  );
  const defaultModel = definition.buildModel(definition.defaultParameterValues);
  return {
    ...defaultModel,
    definition
  };
}

export function normalizeImplicitCadModel(moduleValue, { sourceUrl = "" } = {}) {
  return normalizeImplicitCadDefinition(moduleValue, { sourceUrl });
}

export function implicitCadBoundsCenterAndRadius(model) {
  let normalized = null;
  try {
    normalized = isObject(model) || typeof model === "function" ? normalizeImplicitCadModel(model) : null;
  } catch {
    normalized = null;
  }
  if (normalized) {
    return {
      center: normalized.center,
      radius: normalized.radius,
      bounds: normalized.bounds,
    };
  }
  return {
    center: [0, 0, 0],
    radius: 1,
    bounds: { ...DEFAULT_BOUNDS },
  };
}

export const pathIsImplicitSource = pathIsImplicitCadSource;
export const normalizeImplicitDefinition = normalizeImplicitCadDefinition;
export const normalizeImplicitModel = normalizeImplicitCadModel;
export const implicitBoundsCenterAndRadius = implicitCadBoundsCenterAndRadius;

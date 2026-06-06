import {
  buildCadRefToken,
  normalizeCadPath,
  normalizeCadRefSelectors,
  parseCadRefSelector,
  parseCadRefToken
} from "../lib/cadRefs.js";

export const STEP_MODULE_SCHEMA_VERSION = 1;

const HEX_COLOR_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

function isObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function normalizeString(value, fallback = "") {
  const text = String(value ?? fallback).trim();
  return text || fallback;
}

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeParameterType(value) {
  const type = normalizeString(value, "number").toLowerCase();
  if (["number", "boolean", "enum", "select", "color", "string", "button"].includes(type)) {
    return type === "select" ? "enum" : type;
  }
  return "number";
}

function normalizeParameterOptions(value) {
  return (Array.isArray(value) ? value : [])
    .map((option) => {
      if (isObject(option)) {
        const valueText = normalizeString(option.value);
        return valueText ? {
          value: valueText,
          label: normalizeString(option.label, valueText)
        } : null;
      }
      const valueText = normalizeString(option);
      return valueText ? { value: valueText, label: valueText } : null;
    })
    .filter(Boolean);
}

function normalizeParameterDefinition(id, rawDefinition) {
  const raw = isObject(rawDefinition) ? rawDefinition : {};
  const type = normalizeParameterType(raw.type);
  const min = toFiniteNumber(raw.min, 0);
  const max = Math.max(toFiniteNumber(raw.max, type === "number" ? 1 : min), min);
  const options = normalizeParameterOptions(raw.options || raw.values);
  const fallbackDefault = type === "boolean"
    ? false
    : type === "color"
      ? "#ffffff"
      : type === "enum"
        ? options[0]?.value || ""
        : type === "string"
          ? ""
          : 0;
  return {
    id,
    type,
    label: normalizeString(raw.label, id),
    description: normalizeString(raw.description),
    unit: normalizeString(raw.unit),
    min,
    max,
    step: Math.max(toFiniteNumber(raw.step, type === "number" ? 0.01 : 1), 0),
    defaultValue: normalizeParameterValue({ type, min, max, options }, raw.default ?? raw.defaultValue ?? fallbackDefault),
    options
  };
}

export function normalizeParameterValue(definition, value) {
  const type = normalizeParameterType(definition?.type);
  if (type === "boolean") {
    return value === true;
  }
  if (type === "color") {
    const color = normalizeString(value, normalizeString(definition?.defaultValue, "#ffffff"));
    return HEX_COLOR_RE.test(color) ? color : "#ffffff";
  }
  if (type === "enum") {
    const options = Array.isArray(definition?.options) ? definition.options : [];
    const valueText = normalizeString(value, options[0]?.value || "");
    return options.some((option) => option.value === valueText) ? valueText : (options[0]?.value || "");
  }
  if (type === "string") {
    return String(value ?? "");
  }
  if (type === "button") {
    return Math.max(0, Math.floor(toFiniteNumber(value, 0)));
  }
  const min = toFiniteNumber(definition?.min, 0);
  const max = Math.max(toFiniteNumber(definition?.max, min), min);
  return clamp(toFiniteNumber(value, toFiniteNumber(definition?.defaultValue, min)), min, max);
}

function normalizeParameters(value) {
  return Object.entries(isObject(value) ? value : {})
    .map(([id, rawDefinition]) => normalizeParameterDefinition(normalizeString(id), rawDefinition))
    .filter((definition) => definition.id);
}

function inferCadPathFromStepModuleUrl(url) {
  let pathname = String(url || "").split("?")[0].split("#")[0].replace(/\\/g, "/").trim();
  if (!pathname) {
    return "";
  }
  try {
    pathname = new URL(pathname, "http://localhost").pathname;
  } catch {
    // Keep the raw path for relative module URLs.
  }
  const normalizedPath = pathname.replace(/^\/+|\/+$/g, "");
  const slashIndex = normalizedPath.lastIndexOf("/");
  const directory = slashIndex >= 0 ? normalizedPath.slice(0, slashIndex) : "";
  const fileName = slashIndex >= 0 ? normalizedPath.slice(slashIndex + 1) : normalizedPath;
  const match = fileName.match(/^\.?(.+)\.step\.js$/);
  if (!match?.[1]) {
    return "";
  }
  return normalizeCadPath([directory, match[1]].filter(Boolean).join("/"));
}

function normalizeRelativeStepPath(value) {
  const rawPath = normalizeString(value).replace(/\\/g, "/");
  if (!rawPath || rawPath.startsWith("/") || /^[A-Za-z]:\//.test(rawPath) || /^[a-z][a-z0-9+.-]*:/i.test(rawPath)) {
    return "";
  }
  const parts = rawPath.split("/").filter((part) => part && part !== ".");
  if (!parts.length || parts.some((part) => part === "..")) {
    return "";
  }
  const normalizedPath = parts.join("/");
  return /\.(step|stp)$/i.test(normalizedPath) ? normalizedPath : "";
}

function cadPathFromStepPath(stepPath) {
  return normalizeCadPath(String(stepPath || "").replace(/\.(step|stp)$/i, ""));
}

function normalizeStepLink(value) {
  const raw = isObject(value) ? value : {};
  return {
    ...raw,
    path: normalizeRelativeStepPath(raw.path)
  };
}

function normalizeManifestStep(value, normalizedStep) {
  if (!isObject(value) && !normalizedStep.path) {
    return null;
  }
  const step = isObject(value) ? { ...value } : {};
  if (normalizedStep.path) {
    step.path = normalizedStep.path;
  } else {
    delete step.path;
  }
  return Object.keys(step).length ? step : null;
}

function normalizeFeatureRef(rawFeature, cadPath = "") {
  const raw = isObject(rawFeature) ? rawFeature : {};
  const ref = normalizeString(raw.ref);
  void cadPath;
  const fullToken = parseCadRefToken(ref);
  if (fullToken) {
    return buildCadRefToken({ selectors: fullToken.selectors });
  }

  const rawSelectors = ref.startsWith("#") ? ref.slice(1) : "";
  const selectors = normalizeCadRefSelectors(
    rawSelectors ||
    raw.selector ||
    raw.selectors ||
    raw.occurrence ||
    raw.occurrences ||
    []
  );
  return selectors.length
    ? buildCadRefToken({ selectors })
    : ref;
}

function normalizeFeatures(value, { cadPath = "" } = {}) {
  return Object.entries(isObject(value) ? value : {})
    .map(([id, rawFeature]) => {
      const raw = isObject(rawFeature) ? rawFeature : {};
      const featureId = normalizeString(id);
      return featureId ? {
        id: featureId,
        label: normalizeString(raw.label, featureId),
        description: normalizeString(raw.description),
        ref: normalizeFeatureRef(raw, cadPath),
        partIds: Array.isArray(raw.partIds)
          ? raw.partIds.map((partId) => normalizeString(partId)).filter(Boolean)
          : [],
        axis: normalizeVector3(raw.axis, [0, 0, 1]),
        origin: normalizePoint3(raw.origin, null)
      } : null;
    })
    .filter(Boolean);
}

function normalizeAnimations(value) {
  return Object.entries(isObject(value) ? value : {})
    .map(([id, rawAnimation]) => {
      const raw = isObject(rawAnimation) ? rawAnimation : {};
      const animationId = normalizeString(id);
      return animationId ? {
        id: animationId,
        label: normalizeString(raw.label, animationId),
        description: normalizeString(raw.description),
        duration: Math.max(toFiniteNumber(raw.duration ?? raw.durationSeconds, 1), 0.001),
        loop: raw.loop !== false,
        update: typeof raw.update === "function" ? raw.update : null,
        raw
      } : null;
    })
    .filter(Boolean);
}

function normalizeVector3(value, fallback = [0, 0, 0]) {
  const source = Array.isArray(value) ? value : fallback;
  return [
    toFiniteNumber(source?.[0], fallback[0] || 0),
    toFiniteNumber(source?.[1], fallback[1] || 0),
    toFiniteNumber(source?.[2], fallback[2] || 0)
  ];
}

function normalizePoint3(value, fallback = [0, 0, 0]) {
  if (!Array.isArray(value) && fallback === null) {
    return null;
  }
  return normalizeVector3(value, fallback || [0, 0, 0]);
}

export function normalizeStepModuleDefinition(rawModule, { url = "", cadPath = "" } = {}) {
  if (!isObject(rawModule)) {
    throw new Error("STEP runtime module must export an object");
  }
  const manifest = isObject(rawModule.manifest) ? rawModule.manifest : rawModule;
  const schemaVersion = Number(manifest.schemaVersion || rawModule.schemaVersion || 1);
  if (schemaVersion !== STEP_MODULE_SCHEMA_VERSION) {
    throw new Error(`Unsupported STEP runtime module schemaVersion ${schemaVersion || "unknown"}`);
  }
  const step = normalizeStepLink(manifest.step);
  const stepCadPath = cadPathFromStepPath(step.path);
  const normalizedCadPath = stepCadPath || normalizeCadPath(cadPath) || inferCadPathFromStepModuleUrl(url);
  const parameters = normalizeParameters(manifest.parameters);
  const parameterMap = Object.fromEntries(parameters.map((definition) => [definition.id, definition]));
  const defaultParameterValues = Object.fromEntries(
    parameters.map((definition) => [definition.id, definition.defaultValue])
  );
  const normalizedManifestStep = normalizeManifestStep(manifest.step, step);
  const normalizedManifest = {
    ...manifest,
    schemaVersion: STEP_MODULE_SCHEMA_VERSION
  };
  if (normalizedManifestStep) {
    normalizedManifest.step = normalizedManifestStep;
  } else {
    delete normalizedManifest.step;
  }
  return {
    url: normalizeString(url),
    cadPath: normalizedCadPath,
    step: {
      path: step.path,
      cadPath: stepCadPath || normalizedCadPath,
      explicit: Boolean(step.path),
      inferred: !step.path && Boolean(normalizedCadPath)
    },
    module: rawModule,
    manifest: normalizedManifest,
    features: normalizeFeatures(manifest.features, { cadPath: normalizedCadPath }),
    parameters,
    parameterMap,
    defaultParameterValues,
    animations: normalizeAnimations(manifest.animations)
  };
}

export async function loadStepModuleDefinition(url, options = {}) {
  const namespace = await import(/* webpackIgnore: true */ /* @vite-ignore */ url);
  return normalizeStepModuleDefinition(namespace?.default ?? namespace, { url, ...options });
}

export function normalizeStepModuleParameterValues(definition, values = {}) {
  const parameterMap = definition?.parameterMap || {};
  return Object.fromEntries(
    Object.values(parameterMap).map((parameter) => [
      parameter.id,
      normalizeParameterValue(parameter, isObject(values) && Object.hasOwn(values, parameter.id)
        ? values[parameter.id]
        : parameter.defaultValue)
    ])
  );
}

const STEP_MODULE_ZERO_STATE_EPSILON = 1e-6;

function stepModuleValueMatchesZeroState(parameter, value, zeroValue) {
  const type = normalizeParameterType(parameter?.type);
  if (type === "number" || type === "button") {
    const numericValue = Number(value);
    const numericZeroValue = Number(zeroValue);
    return Number.isFinite(numericValue) &&
      Number.isFinite(numericZeroValue) &&
      Math.abs(numericValue - numericZeroValue) <= STEP_MODULE_ZERO_STATE_EPSILON;
  }
  if (type === "color") {
    return String(value || "").toLowerCase() === String(zeroValue || "").toLowerCase();
  }
  return value === zeroValue;
}

export function stepModuleParameterValuesAtZeroState(definition, values = {}) {
  const parameters = Array.isArray(definition?.parameters) ? definition.parameters : [];
  if (!parameters.length) {
    return true;
  }
  const normalizedValues = normalizeStepModuleParameterValues(definition, values);
  const zeroValues = normalizeStepModuleParameterValues(definition, definition?.defaultParameterValues || {});
  return parameters.every((parameter) => (
    stepModuleValueMatchesZeroState(parameter, normalizedValues[parameter.id], zeroValues[parameter.id])
  ));
}

export function stepModuleAnimationStateAtZeroState(animationState = {}) {
  return animationState?.playing !== true &&
    Math.abs(toFiniteNumber(animationState?.elapsedSec, 0)) <= STEP_MODULE_ZERO_STATE_EPSILON;
}

export function stepModuleRuntimeAtZeroState(definition, runtimeState = {}) {
  return stepModuleParameterValuesAtZeroState(definition, runtimeState?.parameterValues) &&
    stepModuleAnimationStateAtZeroState(runtimeState?.animationState);
}

function boundsCenter(bounds) {
  const min = Array.isArray(bounds?.min) ? bounds.min : [0, 0, 0];
  const max = Array.isArray(bounds?.max) ? bounds.max : min;
  return [
    (toFiniteNumber(min[0]) + toFiniteNumber(max[0])) / 2,
    (toFiniteNumber(min[1]) + toFiniteNumber(max[1])) / 2,
    (toFiniteNumber(min[2]) + toFiniteNumber(max[2])) / 2
  ];
}

function mergeBounds(boundsList) {
  const validBounds = (Array.isArray(boundsList) ? boundsList : [])
    .filter((bounds) => Array.isArray(bounds?.min) && Array.isArray(bounds?.max));
  if (!validBounds.length) {
    return null;
  }
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (const bounds of validBounds) {
    for (let index = 0; index < 3; index += 1) {
      min[index] = Math.min(min[index], toFiniteNumber(bounds.min[index]));
      max[index] = Math.max(max[index], toFiniteNumber(bounds.max[index]));
    }
  }
  return { min, max };
}

function partIdsForSelector(selector, meshData) {
  const normalizedSelector = normalizeString(selector);
  const parts = Array.isArray(meshData?.parts) ? meshData.parts : [];
  if (!normalizedSelector || !parts.length) {
    return [];
  }
  return parts
    .filter((part) => {
      const ids = [part?.id, part?.occurrenceId]
        .map((id) => normalizeString(id))
        .filter(Boolean);
      return ids.some((id) => (
        id === normalizedSelector ||
        id.startsWith(`${normalizedSelector}.`) ||
        normalizedSelector.startsWith(`${id}.`)
      ));
    })
    .map((part) => normalizeString(part.id || part.occurrenceId))
    .filter(Boolean);
}

function referenceForSelector(selector, selectorRuntime) {
  const normalizedSelector = normalizeString(selector);
  if (!normalizedSelector || !selectorRuntime) {
    return null;
  }
  return selectorRuntime.referenceByNormalizedSelector?.get(normalizedSelector)
    || selectorRuntime.referenceByDisplaySelector?.get(normalizedSelector)
    || selectorRuntime.referenceMap?.get(normalizedSelector)
    || null;
}

function uniqueStrings(values) {
  return [...new Set((Array.isArray(values) ? values : [])
    .map((value) => normalizeString(value))
    .filter(Boolean))];
}

function featureSelectors(feature) {
  const token = parseCadRefToken(feature?.ref);
  if (!token) {
    return [];
  }
  return token.selectors.length ? token.selectors : ["__model__"];
}

export function resolveStepModuleFeatures(definition, {
  meshData = null,
  selectorRuntime = null
} = {}) {
  const parts = Array.isArray(meshData?.parts) ? meshData.parts : [];
  const partMap = new Map(parts.map((part) => [normalizeString(part.id || part.occurrenceId), part]));
  const allPartIds = parts.length
    ? parts.map((part) => normalizeString(part.id || part.occurrenceId)).filter(Boolean)
    : ["__model__"];
  return Object.fromEntries(
    (Array.isArray(definition?.features) ? definition.features : []).map((feature) => {
      const selectors = featureSelectors(feature);
      const references = selectors
        .map((selector) => selector === "__model__" ? null : referenceForSelector(selector, selectorRuntime))
        .filter(Boolean);
      const selectorPartIds = selectors.flatMap((selector) => {
        if (selector === "__model__") {
          return allPartIds;
        }
        const parsedSelector = parseCadRefSelector(selector);
        if (parsedSelector?.occurrenceId) {
          return partIdsForSelector(parsedSelector.occurrenceId, meshData);
        }
        const reference = referenceForSelector(selector, selectorRuntime);
        return partIdsForSelector(reference?.partId || reference?.occurrenceId || selector, meshData);
      });
      const partIds = uniqueStrings([
        ...feature.partIds,
        ...selectorPartIds
      ]);
      const partsForFeature = partIds.map((partId) => partMap.get(partId)).filter(Boolean);
      const bounds = mergeBounds(partsForFeature.map((part) => part.bounds)) || meshData?.bounds || null;
      return [feature.id, {
        ...feature,
        selectors,
        references,
        partIds,
        parts: partsForFeature,
        bounds,
        center: feature.origin || boundsCenter(bounds),
        transform: partsForFeature.length === 1 ? partsForFeature[0]?.transform || null : null,
        transforms: partsForFeature.map((part) => part?.transform || null),
        missing: selectors.length > 0 && partIds.length === 0 && selectors[0] !== "__model__"
      }];
    })
  );
}

export function stepModuleTargetPartIds(target, features, meshData) {
  if (Array.isArray(target)) {
    return uniqueStrings(target.flatMap((item) => stepModuleTargetPartIds(item, features, meshData)));
  }
  if (isObject(target)) {
    if (Array.isArray(target.partIds)) {
      return uniqueStrings(target.partIds);
    }
    if (target.partId) {
      return uniqueStrings([target.partId]);
    }
    if (target.feature) {
      return stepModuleTargetPartIds(target.feature, features, meshData);
    }
    if (target.ref) {
      return stepModuleTargetPartIds(target.ref, features, meshData);
    }
  }
  const normalizedTarget = normalizeString(target);
  if (!normalizedTarget) {
    return [];
  }
  if (normalizedTarget === "*" || normalizedTarget === "all" || normalizedTarget === "__all__") {
    const parts = Array.isArray(meshData?.parts) ? meshData.parts : [];
    return parts.length
      ? uniqueStrings(parts.map((part) => part?.id || part?.occurrenceId))
      : ["__model__"];
  }
  const feature = features?.[normalizedTarget];
  if (feature) {
    return uniqueStrings(feature.partIds);
  }
  const token = parseCadRefToken(normalizedTarget);
  if (token) {
    const selectors = token.selectors.length ? token.selectors : ["*"];
    return uniqueStrings(selectors.flatMap((selector) => stepModuleTargetPartIds(selector, features, meshData)));
  }
  return uniqueStrings(partIdsForSelector(normalizedTarget, meshData));
}

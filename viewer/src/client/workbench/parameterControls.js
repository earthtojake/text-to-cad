import {
  normalizeParameterValue,
  normalizeParameterValues
} from "implicitjs/common/parameters.js";

const DEFAULT_NUMBER_CONTROL_STEP = 0.01;
const MIN_NUMBER_CONTROL_STEP = 0.000001;
const TARGET_NUMBER_SLIDER_STEPS = 1000;

function isObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function positiveNumber(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) && numericValue > 0 ? numericValue : 0;
}

function compactNumber(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue)
    ? Number(numericValue.toPrecision(12))
    : DEFAULT_NUMBER_CONTROL_STEP;
}

function parseJsonText(text, label = "parameters") {
  const trimmed = String(text ?? "").trim();
  if (!trimmed) {
    throw new Error(`Clipboard does not contain ${label}`);
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    const firstBrace = trimmed.indexOf("{");
    const lastBrace = trimmed.lastIndexOf("}");
    if (firstBrace >= 0 && lastBrace > firstBrace) {
      return JSON.parse(trimmed.slice(firstBrace, lastBrace + 1));
    }
    throw new Error(`${label} paste must be JSON`);
  }
}

export function resolveParameterNumberControlStep(parameter) {
  const declaredStep = positiveNumber(parameter?.step);
  const min = toFiniteNumber(parameter?.min, 0);
  const max = toFiniteNumber(parameter?.max, min);
  const range = Math.abs(max - min);
  const rangeStep = range > 0
    ? Math.max(
        10 ** Math.floor(Math.log10(range / TARGET_NUMBER_SLIDER_STEPS)),
        MIN_NUMBER_CONTROL_STEP
      )
    : DEFAULT_NUMBER_CONTROL_STEP;
  return compactNumber(declaredStep > 0 ? Math.min(declaredStep, rangeStep) : rangeStep);
}

export function buildParameterValuesCopyText(definition, values = {}) {
  const parameters = Array.isArray(definition?.parameters) ? definition.parameters : [];
  if (!parameters.length) {
    return "{}";
  }
  const normalizedValues = normalizeParameterValues(definition, values);
  const orderedValues = Object.fromEntries(
    parameters.map((parameter) => [parameter.id, normalizedValues[parameter.id]])
  );
  return JSON.stringify(orderedValues, null, 2);
}

export function parseParameterValuesPasteText(definition, text, { label = "parameters", unknownLabel = "parameter" } = {}) {
  const parameterMap = isObject(definition?.parameterMap) ? definition.parameterMap : {};
  const parsed = parseJsonText(text, label);
  const rawValues = isObject(parsed?.values) ? parsed.values : parsed;
  if (!isObject(rawValues)) {
    throw new Error(`${label} paste must be a JSON object`);
  }

  const unknownIds = [];
  const values = {};
  for (const [rawId, rawValue] of Object.entries(rawValues)) {
    const id = String(rawId || "").trim();
    if (!id) {
      continue;
    }
    const parameter = parameterMap[id];
    if (!parameter) {
      unknownIds.push(id);
      continue;
    }
    values[id] = normalizeParameterValue(parameter, rawValue);
  }

  if (unknownIds.length) {
    throw new Error(`Unknown ${unknownLabel}${unknownIds.length === 1 ? "" : "s"}: ${unknownIds.join(", ")}`);
  }
  const count = Object.keys(values).length;
  if (!count) {
    throw new Error(`No known ${unknownLabel}s found`);
  }
  return { values, count };
}

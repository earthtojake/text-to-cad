import {
  articulationControl,
  articulationControls,
  clampControlValue,
  normalizeControlValues
} from "@text-to-cad/core/common/articulation.js";

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

// A slider's step from its range: about a thousand steps across it, never coarser than a
// hundredth, so a control over a few degrees and one over thousands both drag finely.
export function resolveParameterNumberControlStep(control) {
  const min = toFiniteNumber(control?.min, 0);
  const max = toFiniteNumber(control?.max, min);
  const range = Math.abs(max - min);
  const rangeStep = range > 0
    ? Math.max(
        10 ** Math.floor(Math.log10(range / TARGET_NUMBER_SLIDER_STEPS)),
        MIN_NUMBER_CONTROL_STEP
      )
    : DEFAULT_NUMBER_CONTROL_STEP;
  return compactNumber(rangeStep);
}

export function buildParameterValuesCopyText(definition, values = {}) {
  const articulation = definition?.articulation || null;
  const controls = articulationControls(articulation);
  if (!controls.length) {
    return "{}";
  }
  const normalizedValues = normalizeControlValues(articulation, values);
  return JSON.stringify(Object.fromEntries(controls.map((control) => [control.id, normalizedValues[control.id]])), null, 2);
}

export function parseParameterValuesPasteText(definition, text, { label = "parameters", unknownLabel = "parameter" } = {}) {
  const articulation = definition?.articulation || null;
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
    const control = articulationControl(articulation, id);
    if (!control) {
      unknownIds.push(id);
      continue;
    }
    values[id] = clampControlValue(control, rawValue);
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

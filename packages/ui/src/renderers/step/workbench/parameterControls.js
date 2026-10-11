import {
  normalizeParameterValue,
  normalizeParameterValues
} from "@text-to-cad/core/common/parameters.js";

// The slider step is every parameter panel's, Position's and an FEA result's alike.
export { resolveParameterNumberControlStep } from "../../kit/inspector/parameterNumbers.js";

function isObject(value) {
  return !!value && typeof value === "object" && !Array.isArray(value);
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

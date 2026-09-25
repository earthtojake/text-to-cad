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

export function normalizeParameterValues(definition, values = {}) {
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

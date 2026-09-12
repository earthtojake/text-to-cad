export const PARAMETER_SCHEMA_VERSION = 1;

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

export function normalizeParameterType(value) {
  const type = normalizeString(value, "number").toLowerCase();
  if (["number", "boolean", "enum", "select", "color", "string", "button"].includes(type)) {
    return type === "select" ? "enum" : type;
  }
  return "number";
}

export function normalizeParameterOptions(value) {
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

export function normalizeParameterDefinition(id, rawDefinition) {
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

export function normalizeParameterDefinitions(value) {
  const entries = Array.isArray(value)
    ? value.map((definition) => [definition?.id, definition])
    : Object.entries(isObject(value) ? value : {});
  return entries
    .map(([id, rawDefinition]) => normalizeParameterDefinition(normalizeString(id), rawDefinition))
    .filter((definition) => definition.id);
}

export function parameterMapForDefinitions(parameters) {
  return Object.fromEntries(
    (Array.isArray(parameters) ? parameters : [])
      .filter((parameter) => parameter?.id)
      .map((parameter) => [parameter.id, parameter])
  );
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

export function normalizeParameterAnimations(value) {
  const entries = Array.isArray(value)
    ? value.map((animation) => [animation?.id, animation])
    : Object.entries(isObject(value) ? value : {});
  return entries
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

import {
  DEFAULT_STEP_CLIP_SETTINGS,
  normalizeStepClipSettings
} from "../lib/viewer/clipPlane.js";
import {
  CAMERA_PROJECTION,
  normalizeCameraProjection
} from "../lib/perspective.js";
export { CAMERA_PROJECTION, normalizeCameraProjection };

export const CAD_DISPLAY_MODE = Object.freeze({
  HIDDEN_EDGES: "hidden_edges",
  HIDDEN_LINES_REMOVED: "hidden_lines_removed",
  SHADED: "shaded",
  SHADED_EDGES: "shaded_edges",
  TRANSPARENT: "transparent",
  UNSHADED: "unshaded",
  WIREFRAME: "wireframe"
});

export const CAD_DISPLAY_MODE_VALUES = Object.freeze(Object.values(CAD_DISPLAY_MODE));

const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;

export const CAD_EDGE_HIGHLIGHT_COLOR = "#8dc5ff";
export const CAD_EDGE_CLASS_IDS = Object.freeze(["feature", "tangent", "seam", "degenerate"]);

// Persist only CAD visibility choices; ink is a renderer policy.
export const DEFAULT_DISPLAY_EDGE_SETTINGS = Object.freeze({
  enabled: true,
  silhouette: false
});

export const CAD_PART_COLOR_MODE = Object.freeze({
  ORIGINAL: "original",
  SINGLE: "single",
  BY_PART: "by_part"
});

export const CAD_PART_COLOR_MODE_VALUES = Object.freeze(Object.values(CAD_PART_COLOR_MODE));

export const DEFAULT_DISPLAY_GUIDE_SETTINGS = Object.freeze({
  grid: Object.freeze({
    enabled: true
  }),
  axis: Object.freeze({
    enabled: true,
    color: "#6b7280",
    opacity: 0.28
  })
});

export const DEFAULT_PART_COLOR_SETTINGS = Object.freeze({
  mode: CAD_PART_COLOR_MODE.ORIGINAL,
  color: "#b6c4ce",
  colors: Object.freeze([
    "#b6c4ce",
    "#f4a7a7",
    "#f8c77e",
    "#f7e38d",
    "#b9e88f",
    "#8fe3c0",
    "#92d7f5",
    "#a9b8ff",
    "#c7a8ff",
    "#f2a7d9"
  ])
});

// The exploded view is a single slider: `amount` is the 0..1 spread and 0
// means assembled (`enabled` mirrors amount > 0 for consumers that gate on
// it). The layout itself is always computed automatically (see
// lib/viewer/explodedView.js) — there is nothing else to configure.
export const DEFAULT_EXPLODED_VIEW_SETTINGS = Object.freeze({
  enabled: false,
  amount: 0
});

export const DEFAULT_DISPLAY_SETTINGS = Object.freeze({
  mode: CAD_DISPLAY_MODE.SHADED_EDGES,
  clip: DEFAULT_STEP_CLIP_SETTINGS,
  exploded: DEFAULT_EXPLODED_VIEW_SETTINGS,
  edges: DEFAULT_DISPLAY_EDGE_SETTINGS,
  guides: DEFAULT_DISPLAY_GUIDE_SETTINGS,
  partColor: DEFAULT_PART_COLOR_SETTINGS
});

export const DISPLAY_SETTINGS_KEYS = Object.freeze([
  "mode",
  "clip",
  "exploded",
  "edges",
  "guides",
  "partColor",
  "surfaces"
]);

export const DISPLAY_EDGE_SETTINGS_KEYS = Object.freeze(["enabled", "silhouette", "visibility", "color"]);
export const DISPLAY_GUIDE_SETTINGS_KEYS = Object.freeze(["grid", "axis"]);
export const DISPLAY_GRID_GUIDE_SETTINGS_KEYS = Object.freeze(["enabled", "color", "opacity", "density"]);
export const DISPLAY_AXIS_GUIDE_SETTINGS_KEYS = Object.freeze(["enabled", "color", "opacity"]);
export const DISPLAY_PART_COLOR_SETTINGS_KEYS = Object.freeze(["mode", "color", "colors"]);
export const DISPLAY_EXPLODED_SETTINGS_KEYS = Object.freeze(["enabled", "amount"]);
export const DISPLAY_CLIP_SETTINGS_KEYS = Object.freeze(["enabled", "axis", "at", "invert", "partColors"]);

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeNumber(value, fallback, min = -Infinity, max = Infinity) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return fallback;
  }
  return clamp(numericValue, min, max);
}

function normalizeColor(value, fallback) {
  const normalized = String(value || "").trim();
  if (!HEX_COLOR_PATTERN.test(normalized)) {
    return fallback;
  }
  return normalized.length === 4
    ? `#${normalized[1]}${normalized[1]}${normalized[2]}${normalized[2]}${normalized[3]}${normalized[3]}`.toLowerCase()
    : normalized.toLowerCase();
}

function normalizeBoolean(value, fallback = false) {
  return typeof value === "boolean" ? value : fallback;
}

export function normalizeDisplayEdgeSettings(value = null, fallback = DEFAULT_DISPLAY_EDGE_SETTINGS) {
  const source = isObject(value) ? value : {};
  return {
    enabled: normalizeBoolean(source.enabled, fallback.enabled),
    silhouette: normalizeBoolean(source.silhouette, fallback.silhouette || false),
    ...(source.visibility != null || fallback.visibility != null ? { visibility: source.visibility ?? fallback.visibility } : {}),
    ...(source.color != null || fallback.color != null ? { color: normalizeColor(source.color, fallback.color) } : {})
  };
}

function normalizeModeText(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
}

export function normalizeDisplayMode(value, { fallback = CAD_DISPLAY_MODE.SHADED_EDGES } = {}) {
  const normalized = normalizeModeText(value);
  if (!normalized) {
    return fallback;
  }
  if (!CAD_DISPLAY_MODE_VALUES.includes(normalized)) {
    throw new Error(`Unknown display mode '${value}'. Expected one of: ${CAD_DISPLAY_MODE_VALUES.join(", ")}`);
  }
  return normalized;
}

export function normalizeExplodedViewSettings(value = null, fallback = DEFAULT_EXPLODED_VIEW_SETTINGS) {
  const source = isObject(value) ? value : {};
  return {
    enabled: normalizeBoolean(source.enabled, fallback.enabled),
    amount: normalizeNumber(source.amount, source.enabled === true ? 0.5 : fallback.amount, 0, 1)
  };
}

function validateObjectKeys(source, allowedKeys, fieldName) {
  const unknownKeys = Object.keys(source).filter((key) => !allowedKeys.includes(key));
  if (unknownKeys.length) {
    throw new Error(`Unsupported ${fieldName} fields: ${unknownKeys.join(", ")}`);
  }
}

function validateStrictObject(value, fieldName) {
  if (!isObject(value)) {
    throw new Error(`${fieldName} must be an object`);
  }
  return value;
}

function validateStrictBoolean(value, fieldName) {
  if (typeof value !== "boolean") {
    throw new Error(`${fieldName} must be a boolean`);
  }
}

function validateStrictNumber(value, fieldName, min, max) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) {
    throw new Error(`${fieldName} must be a finite number between ${min} and ${max}`);
  }
}

function validateStrictColor(value, fieldName) {
  if (typeof value !== "string" || !HEX_COLOR_PATTERN.test(value.trim())) {
    throw new Error(`${fieldName} must be a hex color`);
  }
}

function validatePresent(source, keys, validator, prefix) {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(source, key)) {
      validator(source[key], `${prefix}.${key}`);
    }
  }
}

export function validateDisplaySettings(value) {
  const source = validateStrictObject(value, "display");
  validateObjectKeys(source, DISPLAY_SETTINGS_KEYS, "display");
  if (Object.prototype.hasOwnProperty.call(source, "mode")) {
    if (typeof source.mode !== "string" || !source.mode.trim()) {
      throw new Error("display.mode must be a non-empty string");
    }
    normalizeDisplayMode(source.mode);
  }
  if (Object.prototype.hasOwnProperty.call(source, "clip")) {
    const clip = validateStrictObject(source.clip, "display.clip");
    validateObjectKeys(clip, DISPLAY_CLIP_SETTINGS_KEYS, "display.clip");
    validatePresent(clip, ["enabled", "invert", "partColors"], validateStrictBoolean, "display.clip");
    if (Object.prototype.hasOwnProperty.call(clip, "axis") && !["x", "y", "z"].includes(clip.axis)) {
      throw new Error("display.clip.axis must be 'x', 'y', or 'z'");
    }
    if (Object.prototype.hasOwnProperty.call(clip, "at")) {
      // The plane's coordinate on its axis, in millimetres in the model's frame.
      if (typeof clip.at !== "number" || !Number.isFinite(clip.at)) {
        throw new Error("display.clip.at must be a finite number: the plane's coordinate on its axis, in millimetres");
      }
    }
  }
  if (Object.prototype.hasOwnProperty.call(source, "exploded")) {
    const exploded = validateStrictObject(source.exploded, "display.exploded");
    validateObjectKeys(exploded, DISPLAY_EXPLODED_SETTINGS_KEYS, "display.exploded");
    validatePresent(exploded, ["enabled"], validateStrictBoolean, "display.exploded");
    validatePresent(exploded, ["amount"],
      (entry, fieldName) => validateStrictNumber(entry, fieldName, 0, 1), "display.exploded");
  }
  if (Object.prototype.hasOwnProperty.call(source, "edges")) {
    const edges = validateStrictObject(source.edges, "display.edges");
    validateObjectKeys(edges, DISPLAY_EDGE_SETTINGS_KEYS, "display.edges");
    validatePresent(edges, ["enabled", "silhouette"], validateStrictBoolean, "display.edges");
    validatePresent(edges, ["color"], validateStrictColor, "display.edges");
    if (Object.hasOwn(edges, "visibility") && !["visible", "all"].includes(edges.visibility)) {
      throw new Error("display.edges.visibility must be 'visible' or 'all'");
    }
  }
  if (Object.prototype.hasOwnProperty.call(source, "guides")) {
    const guides = validateStrictObject(source.guides, "display.guides");
    validateObjectKeys(guides, DISPLAY_GUIDE_SETTINGS_KEYS, "display.guides");
    if (Object.prototype.hasOwnProperty.call(guides, "grid")) {
      const grid = validateStrictObject(guides.grid, "display.guides.grid");
      validateObjectKeys(grid, DISPLAY_GRID_GUIDE_SETTINGS_KEYS, "display.guides.grid");
      validatePresent(grid, ["enabled"], validateStrictBoolean, "display.guides.grid");
      validatePresent(grid, ["color"], validateStrictColor, "display.guides.grid");
      validatePresent(grid, ["opacity"],
        (entry, fieldName) => validateStrictNumber(entry, fieldName, 0, 1), "display.guides.grid");
      validatePresent(grid, ["density"],
        (entry, fieldName) => validateStrictNumber(entry, fieldName, 0.25, 4), "display.guides.grid");
    }
    if (Object.prototype.hasOwnProperty.call(guides, "axis")) {
      const axis = validateStrictObject(guides.axis, "display.guides.axis");
      validateObjectKeys(axis, DISPLAY_AXIS_GUIDE_SETTINGS_KEYS, "display.guides.axis");
      validatePresent(axis, ["enabled"], validateStrictBoolean, "display.guides.axis");
      validatePresent(axis, ["color"], validateStrictColor, "display.guides.axis");
      validatePresent(axis, ["opacity"],
        (entry, fieldName) => validateStrictNumber(entry, fieldName, 0, 1), "display.guides.axis");
    }
  }
  if (Object.prototype.hasOwnProperty.call(source, "partColor")) {
    const partColor = validateStrictObject(source.partColor, "display.partColor");
    validateObjectKeys(partColor, DISPLAY_PART_COLOR_SETTINGS_KEYS, "display.partColor");
    validatePresent(partColor, ["color"], validateStrictColor, "display.partColor");
    if (Object.prototype.hasOwnProperty.call(partColor, "colors")) {
      if (!Array.isArray(partColor.colors) || partColor.colors.length < 1 || partColor.colors.length > 50) {
        throw new Error("display.partColor.colors must contain 1 to 50 hex colors");
      }
      partColor.colors.forEach((color, index) => validateStrictColor(color, `display.partColor.colors[${index}]`));
    }
    normalizePartColorSettings(partColor);
  }
  return true;
}

export function normalizeDisplayGuideSettings(value = null, fallback = DEFAULT_DISPLAY_GUIDE_SETTINGS) {
  const source = isObject(value) ? value : {};
  validateObjectKeys(source, ["grid", "axis"], "display.guides");
  const grid = isObject(source.grid) ? source.grid : {};
  const axis = isObject(source.axis) ? source.axis : {};
  validateObjectKeys(grid, DISPLAY_GRID_GUIDE_SETTINGS_KEYS, "display.guides.grid");
  validateObjectKeys(axis, ["enabled", "color", "opacity"], "display.guides.axis");
  return {
    grid: {
      enabled: normalizeBoolean(grid.enabled, fallback.grid.enabled),
      ...(grid.color != null || fallback.grid.color != null
        ? { color: normalizeColor(grid.color, fallback.grid.color) } : {}),
      ...(grid.opacity != null || fallback.grid.opacity != null
        ? { opacity: normalizeNumber(grid.opacity, fallback.grid.opacity, 0, 1) } : {}),
      ...(grid.density != null || fallback.grid.density != null
        ? { density: normalizeNumber(grid.density, fallback.grid.density ?? 1, 0.25, 4) } : {})
    },
    axis: {
      enabled: normalizeBoolean(axis.enabled, fallback.axis.enabled),
      color: normalizeColor(axis.color, fallback.axis.color),
      opacity: normalizeNumber(axis.opacity, fallback.axis.opacity, 0, 1)
    }
  };
}

export function normalizePartColorSettings(value = null, fallback = DEFAULT_PART_COLOR_SETTINGS) {
  const source = typeof value === "string"
    ? { mode: value }
    : isObject(value) ? value : {};
  validateObjectKeys(source, ["mode", "color", "colors"], "display.partColor");
  const mode = String(source.mode || fallback.mode).trim().toLowerCase().replace(/-/g, "_");
  if (!CAD_PART_COLOR_MODE_VALUES.includes(mode)) {
    throw new Error(`Unknown display part color mode '${source.mode}'. Expected one of: ${CAD_PART_COLOR_MODE_VALUES.join(", ")}`);
  }
  const colors = (Array.isArray(source.colors) ? source.colors : fallback.colors)
    .map((entry) => normalizeColor(entry, ""))
    .filter(Boolean)
    .slice(0, 50);
  return {
    mode,
    color: normalizeColor(source.color, fallback.color),
    colors: colors.length ? colors : [...DEFAULT_PART_COLOR_SETTINGS.colors]
  };
}

export function normalizeDisplaySettings(value = null, { fallback = DEFAULT_DISPLAY_SETTINGS } = {}) {
  const source = isObject(value) ? value : {};
  validateObjectKeys(source, DISPLAY_SETTINGS_KEYS, "display");
  const mode = normalizeDisplayMode(source.mode, { fallback: fallback.mode });
  return {
    mode,
    ...(source.surfaces != null || fallback.surfaces != null ? { surfaces: structuredClone(source.surfaces ?? fallback.surfaces) } : {}),
    clip: normalizeStepClipSettings(source.clip ?? fallback.clip),
    exploded: normalizeExplodedViewSettings(source.exploded, fallback.exploded),
    edges: normalizeDisplayEdgeSettings(source.edges, fallback.edges),
    guides: normalizeDisplayGuideSettings(source.guides, fallback.guides),
    partColor: normalizePartColorSettings(source.partColor, fallback.partColor)
  };
}

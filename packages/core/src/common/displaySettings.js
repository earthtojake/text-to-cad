import {
  DEFAULT_STEP_CLIP_SETTINGS,
  normalizeStepClipSettings,
  stepClipSettingsEqual
} from "../lib/viewer/clipPlane.js";
import {
  CAMERA_PROJECTION,
  normalizeCameraProjection
} from "../lib/perspective.js";
export { CAMERA_PROJECTION, normalizeCameraProjection };

export const CAD_DISPLAY_MODE = Object.freeze({
  HIDDEN_EDGES: "hidden_edges",
  HIDDEN_LINES_REMOVED: "hidden_lines_removed",
  RENDER: "render",
  SHADED: "shaded",
  SHADED_EDGES: "shaded_edges",
  TRANSPARENT: "transparent",
  UNSHADED: "unshaded",
  WIREFRAME: "wireframe"
});

export const CAD_DISPLAY_MODE_VALUES = Object.freeze(Object.values(CAD_DISPLAY_MODE));

const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;

export const CAD_EDGE_COLOR = "#132232";
export const CAD_EDGE_HIGHLIGHT_COLOR = "#8dc5ff";
export const CAD_EDGE_CLASS_IDS = Object.freeze(["feature", "tangent", "seam", "degenerate"]);

// Persist only CAD visibility choices; ink is a renderer policy.
export const DEFAULT_DISPLAY_EDGE_SETTINGS = Object.freeze({
  enabled: true,
  silhouette: false
});

export const DISABLED_DISPLAY_EDGE_SETTINGS = Object.freeze({
  ...DEFAULT_DISPLAY_EDGE_SETTINGS,
  enabled: false
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

export const DISABLED_DISPLAY_GUIDE_SETTINGS = Object.freeze({
  grid: Object.freeze({
    ...DEFAULT_DISPLAY_GUIDE_SETTINGS.grid,
    enabled: false
  }),
  axis: Object.freeze({
    ...DEFAULT_DISPLAY_GUIDE_SETTINGS.axis,
    enabled: false
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
  "render",
  "clip",
  "exploded",
  "edges",
  "guides",
  "partColor",
  "surfaces"
]);

export const DISPLAY_RENDER_SETTINGS_KEYS = Object.freeze([
  "studio",
  "quality",
  "exposure",
  "lighting",
  "backdrop"
]);
export const DISPLAY_RENDER_LIGHTING_KEYS = Object.freeze(["rotation", "size", "fill"]);
export const DISPLAY_RENDER_BACKDROP_KEYS = Object.freeze(["color", "transparent", "ground", "groundPlacement", "groundColor", "groundOpacity"]);

export const DISPLAY_EDGE_SETTINGS_KEYS = Object.freeze(["enabled", "silhouette", "visibility", "color"]);
export const DISPLAY_GUIDE_SETTINGS_KEYS = Object.freeze(["grid", "axis"]);
export const DISPLAY_GRID_GUIDE_SETTINGS_KEYS = Object.freeze(["enabled", "color", "opacity"]);
export const DISPLAY_AXIS_GUIDE_SETTINGS_KEYS = Object.freeze(["enabled", "color", "opacity"]);
export const DISPLAY_PART_COLOR_SETTINGS_KEYS = Object.freeze(["mode", "color", "colors"]);
export const DISPLAY_EXPLODED_SETTINGS_KEYS = Object.freeze(["enabled", "amount"]);
export const DISPLAY_CLIP_SETTINGS_KEYS = Object.freeze(["enabled", "axis", "offset", "offsets", "invert"]);

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
  if (normalized === "rendered") {
    throw new Error("Display mode 'rendered' was removed; use 'shaded'.");
  }
  if (normalized === "solid") {
    throw new Error("Display mode 'solid' was removed; use 'shaded_edges'.");
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
  if (Object.prototype.hasOwnProperty.call(source, "render")) {
    validateDisplayRenderSettings(source.render);
    if (normalizeDisplayMode(source.mode) !== CAD_DISPLAY_MODE.RENDER) {
      throw new Error("display.render requires display.mode 'render'");
    }
  }
  if (Object.prototype.hasOwnProperty.call(source, "clip")) {
    const clip = validateStrictObject(source.clip, "display.clip");
    validateObjectKeys(clip, DISPLAY_CLIP_SETTINGS_KEYS, "display.clip");
    validatePresent(clip, ["enabled", "invert"], validateStrictBoolean, "display.clip");
    if (Object.prototype.hasOwnProperty.call(clip, "axis") && !["x", "y", "z"].includes(clip.axis)) {
      throw new Error("display.clip.axis must be 'x', 'y', or 'z'");
    }
    if (Object.prototype.hasOwnProperty.call(clip, "offset")) {
      validateStrictNumber(clip.offset, "display.clip.offset", 0, 1);
    }
    if (Object.prototype.hasOwnProperty.call(clip, "offsets")) {
      const offsets = validateStrictObject(clip.offsets, "display.clip.offsets");
      validateObjectKeys(offsets, ["x", "y", "z"], "display.clip.offsets");
      validatePresent(offsets, ["x", "y", "z"],
        (entry, fieldName) => validateStrictNumber(entry, fieldName, 0, 1), "display.clip.offsets");
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

export function validateDisplayRenderSettings(value) {
  const render = validateStrictObject(value, "display.render");
  validateObjectKeys(render, DISPLAY_RENDER_SETTINGS_KEYS, "display.render");
  if (Object.hasOwn(render, "studio") && !["light", "dark"].includes(render.studio)) {
    throw new Error("display.render.studio must be 'light' or 'dark'");
  }
  if (Object.hasOwn(render, "quality") && !["preview", "final"].includes(render.quality)) {
    throw new Error("display.render.quality must be 'preview' or 'final'");
  }
  if (Object.hasOwn(render, "exposure")) validateStrictNumber(render.exposure, "display.render.exposure", -5, 5);
  if (Object.hasOwn(render, "lighting")) {
    const lighting = validateStrictObject(render.lighting, "display.render.lighting");
    validateObjectKeys(lighting, DISPLAY_RENDER_LIGHTING_KEYS, "display.render.lighting");
    validatePresent(lighting, ["rotation"],
      (entry, fieldName) => validateStrictNumber(entry, fieldName, -180, 180), "display.render.lighting");
    validatePresent(lighting, ["size"],
      (entry, fieldName) => validateStrictNumber(entry, fieldName, 0.25, 3), "display.render.lighting");
    validatePresent(lighting, ["fill"],
      (entry, fieldName) => validateStrictNumber(entry, fieldName, 0, 1), "display.render.lighting");
  }
  if (Object.hasOwn(render, "backdrop")) {
    const backdrop = validateStrictObject(render.backdrop, "display.render.backdrop");
    validateObjectKeys(backdrop, DISPLAY_RENDER_BACKDROP_KEYS, "display.render.backdrop");
    validatePresent(backdrop, ["color", "groundColor"], validateStrictColor, "display.render.backdrop");
    validatePresent(backdrop, ["transparent", "ground"], validateStrictBoolean, "display.render.backdrop");
    validatePresent(backdrop, ["groundOpacity"],
      (entry, fieldName) => validateStrictNumber(entry, fieldName, 0, 1), "display.render.backdrop");
    if (Object.hasOwn(backdrop, "groundPlacement") && !["origin", "lowest"].includes(backdrop.groundPlacement)) {
      throw new Error("display.render.backdrop.groundPlacement must be 'origin' or 'lowest'");
    }
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
        ? { opacity: normalizeNumber(grid.opacity, fallback.grid.opacity, 0, 1) } : {})
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
  const render = source.render == null
    ? (mode === CAD_DISPLAY_MODE.RENDER && isObject(fallback.render) ? structuredClone(fallback.render) : null)
    : { ...source.render };
  if (render != null) {
    validateDisplayRenderSettings(render);
    if (mode !== CAD_DISPLAY_MODE.RENDER) throw new Error("display.render requires display.mode 'render'");
  }
  return {
    mode,
    ...(render != null ? { render } : {}),
    ...(source.surfaces != null || fallback.surfaces != null ? { surfaces: structuredClone(source.surfaces ?? fallback.surfaces) } : {}),
    clip: normalizeStepClipSettings(source.clip ?? fallback.clip),
    exploded: normalizeExplodedViewSettings(source.exploded, fallback.exploded),
    edges: normalizeDisplayEdgeSettings(source.edges, fallback.edges),
    guides: normalizeDisplayGuideSettings(source.guides, fallback.guides),
    partColor: normalizePartColorSettings(source.partColor, fallback.partColor)
  };
}

export function cloneDisplaySettings(value = DEFAULT_DISPLAY_SETTINGS) {
  return normalizeDisplaySettings(value);
}

export function displaySettingsEqual(left, right) {
  const a = normalizeDisplaySettings(left);
  const b = normalizeDisplaySettings(right);
  return a.mode === b.mode &&
    JSON.stringify(a.surfaces) === JSON.stringify(b.surfaces) &&
    JSON.stringify(a.render) === JSON.stringify(b.render) &&
    stepClipSettingsEqual(a.clip, b.clip) &&
    JSON.stringify(a.exploded) === JSON.stringify(b.exploded) &&
    JSON.stringify(a.edges) === JSON.stringify(b.edges) &&
    JSON.stringify(a.guides) === JSON.stringify(b.guides) &&
    JSON.stringify(a.partColor) === JSON.stringify(b.partColor);
}

export function resolveDisplayMode(displaySettings) {
  return normalizeDisplaySettings(displaySettings).mode;
}

export function resolveDisplayEdgeSettings(displaySettings) {
  return normalizeDisplaySettings(displaySettings).edges;
}

export function displayModeIsWireframe(value) {
  return normalizeDisplayMode(value) === CAD_DISPLAY_MODE.WIREFRAME;
}

export function displayModeForcesEdges(value) {
  return [
    CAD_DISPLAY_MODE.SHADED_EDGES,
    CAD_DISPLAY_MODE.TRANSPARENT,
    CAD_DISPLAY_MODE.HIDDEN_EDGES,
    CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED
  ].includes(normalizeDisplayMode(value));
}

export function displayModeAllowsEdges(value) {
  return ![
    CAD_DISPLAY_MODE.RENDER,
    CAD_DISPLAY_MODE.SHADED,
    CAD_DISPLAY_MODE.UNSHADED
  ].includes(normalizeDisplayMode(value));
}

// The MODE decides whether CAD linework is drawn at all, and nothing else does:
// `shaded_edges` is shaded-with-edges (so is `transparent`, `hidden_edges`,
// `hidden_lines_removed`), `wireframe` is linework only, and `shaded`/`unshaded`
// draw none. This took an `edgeSettings` argument it never read, which read as a
// bug at every call site; `edges` styles the linework the mode has decided to draw.
export function displayModeShowsEdges(value) {
  const mode = normalizeDisplayMode(value);
  return mode === CAD_DISPLAY_MODE.WIREFRAME ||
    displayModeForcesEdges(mode);
}

export function displayModeShowsThroughEdges(value) {
  return [
    CAD_DISPLAY_MODE.TRANSPARENT,
    CAD_DISPLAY_MODE.HIDDEN_EDGES
  ].includes(normalizeDisplayMode(value));
}

export function displayModeUsesTransparentSurfaces(value) {
  return [
    CAD_DISPLAY_MODE.TRANSPARENT,
    CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED,
    CAD_DISPLAY_MODE.WIREFRAME
  ].includes(normalizeDisplayMode(value));
}

export function displayModeUsesUnlitSurfaces(value) {
  return [
    CAD_DISPLAY_MODE.UNSHADED,
    CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED,
    CAD_DISPLAY_MODE.WIREFRAME
  ].includes(normalizeDisplayMode(value));
}

export function displayModeSurfaceOpacity(value, fallback = 1) {
  const mode = normalizeDisplayMode(value);
  if (mode === CAD_DISPLAY_MODE.WIREFRAME) {
    return 0.035;
  }
  if (mode === CAD_DISPLAY_MODE.TRANSPARENT) {
    return 0.22;
  }
  if (mode === CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED) {
    return 0.045;
  }
  const numericFallback = Number(fallback);
  return Number.isFinite(numericFallback) ? numericFallback : 1;
}

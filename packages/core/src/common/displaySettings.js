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
  RENDERED: "rendered",
  SOLID: "solid",
  TRANSPARENT: "transparent",
  UNSHADED: "unshaded",
  WIREFRAME: "wireframe"
});

export const CAD_DISPLAY_MODE_VALUES = Object.freeze(Object.values(CAD_DISPLAY_MODE));

const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;

export const CAD_EDGE_COLOR = "#132232";
export const CAD_EDGE_HIGHLIGHT_COLOR = "#8dc5ff";
export const CAD_EDGE_CLASS_IDS = Object.freeze(["feature", "tangent", "seam", "degenerate"]);

export const DEFAULT_DISPLAY_EDGE_CLASS_SETTINGS = Object.freeze({
  feature: Object.freeze({
    color: CAD_EDGE_COLOR,
    opacity: 1,
    thickness: 1.15
  }),
  tangent: Object.freeze({
    color: CAD_EDGE_COLOR,
    opacity: 0.5,
    thickness: 1.15
  }),
  seam: Object.freeze({
    color: CAD_EDGE_COLOR,
    opacity: 0.85,
    thickness: 1.15
  }),
  degenerate: Object.freeze({
    color: CAD_EDGE_COLOR,
    opacity: 1,
    thickness: 0
  })
});

export const DEFAULT_DISPLAY_EDGE_SETTINGS = Object.freeze({
  enabled: true,
  color: CAD_EDGE_COLOR,
  thickness: 1,
  classes: DEFAULT_DISPLAY_EDGE_CLASS_SETTINGS,
  highlightColor: CAD_EDGE_HIGHLIGHT_COLOR,
  highlightOpacity: 1,
  highlightThickness: 3,
  silhouette: false,
  silhouetteScale: 0
});

export const DISABLED_DISPLAY_EDGE_SETTINGS = Object.freeze({
  ...DEFAULT_DISPLAY_EDGE_SETTINGS,
  enabled: false
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
  mode: CAD_DISPLAY_MODE.SOLID,
  clip: DEFAULT_STEP_CLIP_SETTINGS,
  exploded: DEFAULT_EXPLODED_VIEW_SETTINGS,
  edges: DEFAULT_DISPLAY_EDGE_SETTINGS
});

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

export function normalizeDisplayEdgeClassSettings(
  value = {},
  fallback = DEFAULT_DISPLAY_EDGE_CLASS_SETTINGS,
  colorFallback = CAD_EDGE_COLOR
) {
  const source = isObject(value) ? value : {};
  const fallbackColor = normalizeColor(colorFallback, CAD_EDGE_COLOR);
  return Object.fromEntries(CAD_EDGE_CLASS_IDS.map((classId) => {
    const classSource = isObject(source[classId]) ? source[classId] : {};
    const classFallback = fallback?.[classId] || DEFAULT_DISPLAY_EDGE_CLASS_SETTINGS[classId];
    return [classId, {
      color: normalizeColor(classSource.color, fallbackColor),
      opacity: normalizeNumber(classSource.opacity, classFallback.opacity, 0, 1),
      thickness: normalizeNumber(classSource.thickness, classFallback.thickness, 0, 6)
    }];
  }));
}

export function normalizeDisplayEdgeSettings(value = null, fallback = DEFAULT_DISPLAY_EDGE_SETTINGS) {
  const source = isObject(value) ? value : {};
  const color = normalizeColor(source.color, fallback.color);
  const normalized = {
    enabled: normalizeBoolean(source.enabled, fallback.enabled),
    color,
    thickness: normalizeNumber(source.thickness, fallback.thickness, 0.5, 6),
    classes: normalizeDisplayEdgeClassSettings(source.classes, fallback.classes, color),
    highlightColor: normalizeColor(source.highlightColor, fallback.highlightColor || CAD_EDGE_HIGHLIGHT_COLOR),
    highlightOpacity: normalizeNumber(source.highlightOpacity, fallback.highlightOpacity || 1, 0, 1),
    highlightThickness: normalizeNumber(source.highlightThickness, fallback.highlightThickness || 3, 0.5, 6),
    silhouette: normalizeBoolean(source.silhouette, fallback.silhouette || false),
    silhouetteScale: normalizeNumber(source.silhouetteScale, fallback.silhouetteScale || 0, 0, 0.04)
  };
  if (typeof source.depthTest === "boolean") {
    normalized.depthTest = source.depthTest;
  }
  return normalized;
}

function normalizeModeText(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
}

export function normalizeDisplayMode(value) {
  const normalized = normalizeModeText(value);
  if (!normalized) {
    return CAD_DISPLAY_MODE.SOLID;
  }
  if (normalized === "wire" || normalized === "wire_frame") {
    return CAD_DISPLAY_MODE.WIREFRAME;
  }
  if (
    normalized === "edges" ||
    normalized === "edge" ||
    normalized === "shaded_edges" ||
    normalized === "shaded_with_edges" ||
    normalized === "with_edges"
  ) {
    return CAD_DISPLAY_MODE.SOLID;
  }
  if (
    normalized === "shaded" ||
    normalized === "shaded_without_edges" ||
    normalized === "without_edges"
  ) {
    return CAD_DISPLAY_MODE.RENDERED;
  }
  if (
    normalized === "translucent" ||
    normalized === "xray" ||
    normalized === "x_ray" ||
    normalized === "see_through"
  ) {
    return CAD_DISPLAY_MODE.TRANSPARENT;
  }
  if (
    normalized === "hidden_edge" ||
    normalized === "hidden_edges_visible" ||
    normalized === "hidden_edge_display" ||
    normalized === "shaded_hidden_edges"
  ) {
    return CAD_DISPLAY_MODE.HIDDEN_EDGES;
  }
  if (
    normalized === "visible_edges" ||
    normalized === "visible_edges_only" ||
    normalized === "hidden_lines" ||
    normalized === "hidden_line_removed" ||
    normalized === "hidden_lines_removed" ||
    normalized === "hidden_edges_removed"
  ) {
    return CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED;
  }
  if (normalized === "flat") {
    return CAD_DISPLAY_MODE.UNSHADED;
  }
  if (normalized === "theme" || normalized === "material" || normalized === "materials") {
    return CAD_DISPLAY_MODE.RENDERED;
  }
  return CAD_DISPLAY_MODE_VALUES.includes(normalized)
    ? normalized
    : CAD_DISPLAY_MODE.SOLID;
}

export function normalizeExplodedViewSettings(value = null) {
  const source = isObject(value) ? value : {};
  return {
    enabled: Boolean(source.enabled),
    amount: normalizeNumber(source.amount, DEFAULT_EXPLODED_VIEW_SETTINGS.amount, 0, 1)
  };
}

export function normalizeDisplaySettings(value = null) {
  const source = isObject(value) ? value : {};
  return {
    mode: normalizeDisplayMode(source.mode),
    clip: normalizeStepClipSettings(source.clip),
    exploded: normalizeExplodedViewSettings(source.exploded),
    edges: normalizeDisplayEdgeSettings(source.edges)
  };
}

export function cloneDisplaySettings(value = DEFAULT_DISPLAY_SETTINGS) {
  return normalizeDisplaySettings(value);
}

export function displaySettingsEqual(left, right) {
  const a = normalizeDisplaySettings(left);
  const b = normalizeDisplaySettings(right);
  return a.mode === b.mode &&
    stepClipSettingsEqual(a.clip, b.clip) &&
    JSON.stringify(a.exploded) === JSON.stringify(b.exploded) &&
    JSON.stringify(a.edges) === JSON.stringify(b.edges);
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
    CAD_DISPLAY_MODE.SOLID,
    CAD_DISPLAY_MODE.TRANSPARENT,
    CAD_DISPLAY_MODE.HIDDEN_EDGES,
    CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED
  ].includes(normalizeDisplayMode(value));
}

export function displayModeAllowsEdges(value) {
  return ![
    CAD_DISPLAY_MODE.RENDERED,
    CAD_DISPLAY_MODE.UNSHADED
  ].includes(normalizeDisplayMode(value));
}

export function displayModeShowsEdges(value, edgeSettings = null) {
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

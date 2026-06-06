import {
  DEFAULT_STEP_CLIP_SETTINGS,
  normalizeStepClipSettings,
  stepClipSettingsEqual
} from "../lib/viewer/clipPlane.js";

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

export const DEFAULT_DISPLAY_SETTINGS = Object.freeze({
  mode: CAD_DISPLAY_MODE.SOLID,
  clip: DEFAULT_STEP_CLIP_SETTINGS
});

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function normalizeDisplayMode(value) {
  const normalized = String(value || "").trim().toLowerCase().replace(/\s+/g, "_").replace(/-/g, "_");
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
  if (normalized === "appearance" || normalized === "material" || normalized === "materials") {
    return CAD_DISPLAY_MODE.RENDERED;
  }
  return CAD_DISPLAY_MODE_VALUES.includes(normalized)
    ? normalized
    : CAD_DISPLAY_MODE.SOLID;
}

export function normalizeDisplaySettings(value = null) {
  const source = isObject(value) ? value : {};
  return {
    mode: normalizeDisplayMode(source.mode),
    clip: normalizeStepClipSettings(source.clip)
  };
}

export function cloneDisplaySettings(value = DEFAULT_DISPLAY_SETTINGS) {
  return normalizeDisplaySettings(value);
}

export function displaySettingsEqual(left, right) {
  const a = normalizeDisplaySettings(left);
  const b = normalizeDisplaySettings(right);
  return a.mode === b.mode && stepClipSettingsEqual(a.clip, b.clip);
}

export function resolveDisplayMode(displaySettings) {
  return normalizeDisplaySettings(displaySettings).mode;
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

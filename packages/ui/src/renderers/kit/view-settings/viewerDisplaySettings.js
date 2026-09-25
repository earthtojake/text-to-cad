import {
  normalizeViewSettings,
  resetViewSettings,
  resolveViewSettings
} from "@hardcore/core/common/viewSettings.js";

import { buildStepClipPatch } from "@hardcore/core/lib/viewer/clipPlane.js";

const GROUPS = ["camera", "surfaces", "edges", "lighting", "background", "floor", "grid", "axes", "clip", "exploded"];
const LEGACY_MODES = {
  shaded: "solid", shaded_edges: "solid", unshaded: "solid", hidden_edges: "xray",
  transparent: "xray", hidden_lines_removed: "hidden-line"
};
const object = value => value && typeof value === "object" && !Array.isArray(value);

export const normalizeViewerDisplaySettings = normalizeViewSettings;
export const resetViewerDisplaySettings = resetViewSettings;
export const normalizeViewerDisplayMode = value => normalizeViewSettings({ mode: value }).mode;

// Patches merge groups, while a preset selection clears visual overrides. Tools
// remain outside the preset so changing the view never moves a clipping plane.
export function mergeViewerDisplaySettings(current, patch) {
  const normalized = normalizeViewSettings(patch);
  const base = Object.hasOwn(patch, "mode")
    ? viewerDisplaySettingsForMode(current, normalized.mode) : normalizeViewSettings(current);
  const next = { ...base, ...normalized };
  if (!Object.hasOwn(patch, "mode")) next.mode = base.mode;
  for (const group of GROUPS) {
    if (Object.hasOwn(patch, group)) next[group] = { ...base[group], ...normalized[group] };
  }
  if (normalized.clip) next.clip = buildStepClipPatch(base.clip, normalized.clip);
  return normalizeViewSettings(next);
}

export function viewerDisplaySettingsForMode(current, mode) {
  const source = normalizeViewSettings(current);
  return { mode: normalizeViewerDisplayMode(mode),
    ...(source.clip ? { clip: source.clip } : {}),
    ...(source.exploded ? { exploded: source.exploded } : {}) };
}

// A camera command carries both pose and optional View controls. Explicit lens
// or projection edits activate their group; a pose-only command leaves it alone.
export function viewerDisplaySettingsForCamera(current, camera) {
  const controls = {
    ...(camera?.projection ? { projection: camera.projection } : {}),
    ...(camera?.focalLength != null ? { focalLength: camera.focalLength } : {})
  };
  return Object.keys(controls).length
    ? mergeViewerDisplaySettings(current, { camera: { ...controls, enabled: true } })
    : normalizeViewSettings(current);
}

export function cameraForViewSettings(camera, display, options) {
  if (!camera) return null;
  const settings = resolveViewSettings(display, options).camera;
  return { ...camera, projection: settings.projection, focalLength: settings.focalLength };
}

// Persisted sessions are the sole migration boundary. Live commands and new
// display state use the closed grouped schema directly.
export function migrateViewerDisplaySettings(value, renderSession = null) {
  const source = object(value) ? value : {};
  const legacy = Object.hasOwn(LEGACY_MODES, source.mode) ||
    ["guides", "partColor", "render"].some(key => Object.hasOwn(source, key)) ||
    Object.hasOwn(renderSession || {}, "enabled") || Object.hasOwn(renderSession || {}, "payload");
  if (!legacy) {
    try { return normalizeViewSettings(source); } catch { return recoverGroups(source); }
  }
  const mode = renderSession?.enabled === true ? "render" : (LEGACY_MODES[source.mode] || source.mode || "solid");
  const next = { mode, ...(Object.hasOwn(source, "appearance") ? { appearance: source.appearance } : {}) };
  for (const group of ["clip", "exploded"]) if (object(source[group])) next[group] = source[group];
  if (object(source.edges)) next.edges = { enabled: source.edges.enabled };
  if (object(source.guides?.grid)) next.grid = source.guides.grid;
  if (object(source.guides?.axis)) next.axes = source.guides.axis;
  if (object(source.partColor)) {
    const { mode: colorMode, color, colors } = source.partColor;
    next.surfaces = { colorMode: colorMode === "by_part" ? "by-part" : colorMode, color, colors };
  }
  const payload = object(renderSession?.payload) ? renderSession.payload : (source.render || {});
  if (mode === "render") {
    next.lighting = { ...payload.lighting, quality: payload.quality, exposure: payload.exposure };
    if (object(payload.backdrop)) {
      const backdrop = payload.backdrop;
      next.background = { color: backdrop.color, opacity: backdrop.transparent === true ? 0 : undefined };
      next.floor = { enabled: backdrop.ground, placement: backdrop.groundPlacement,
        color: backdrop.groundColor, opacity: backdrop.groundOpacity };
    }
  }
  const camera = renderSession?.enabled && payload.camera ? payload.camera : renderSession?.cadCamera;
  next.camera = { projection: camera?.projection || renderSession?.cadProjection, focalLength: camera?.focalLength };
  return recoverGroups(next);
}

function recoverGroups(source) {
  let next;
  try { next = normalizeViewSettings({ mode: source.mode }); } catch { next = normalizeViewSettings(); }
  if (Object.hasOwn(source, "appearance")) {
    try { next = normalizeViewSettings({ ...next, appearance: source.appearance }); } catch { /* Invalid persisted appearance. */ }
  }
  for (const group of GROUPS) {
    if (!object(source[group])) continue;
    // Recover valid fields independently; a corrupt colour must not discard a
    // user's camera, clipping plane, or other settings in the same group.
    for (const [key, value] of Object.entries(source[group])) {
      if (value === undefined) continue;
      try { next = normalizeViewSettings({ ...next, [group]: { ...next[group], [key]: value } }); } catch { /* Invalid persisted field. */ }
    }
  }
  return next;
}

/** Presentation suspends model effects without changing the per-file settings. */
export function presentationDisplaySettings(display) {
  return { ...display, clip: { ...display.clip, enabled: false },
    exploded: { ...display.exploded, enabled: false, amount: 0 } };
}

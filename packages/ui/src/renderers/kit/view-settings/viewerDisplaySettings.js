import { normalizeViewSettings, resolveViewSettings } from "@hardcore/core/common/viewSettings.js";

import { buildStepClipPatch } from "@hardcore/core/lib/viewer/clipPlane.js";

const GROUPS = ["camera", "surfaces", "edges", "lighting", "background", "floor", "grid", "axes", "clip", "exploded"];
const normalizeViewerDisplayMode = value => normalizeViewSettings({ mode: value }).mode;

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

/** Presentation suspends model effects without changing the per-file settings. */
export function presentationDisplaySettings(display) {
  return { ...display, clip: { ...display.clip, enabled: false },
    exploded: { ...display.exploded, enabled: false, amount: 0 } };
}

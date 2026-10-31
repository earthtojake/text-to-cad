import { normalizePreviewSettings, normalizeViewSettings, resolveViewSettings } from "@text-to-cad/core/common/viewSettings.js";

import { buildStepClipPatch } from "@text-to-cad/core/lib/viewer/clipPlane.js";

// A patch merges into what is there, in the same shape: `mode` picks the mode and `grid` switches
// the grid; the shared groups merge field by field.
export function mergeViewerDisplaySettings(current, patch) {
  const normalized = normalizeViewSettings(patch);
  const base = normalizeViewSettings(current);
  const next = { ...base };
  if (Object.hasOwn(patch, "mode")) next.mode = normalized.mode;
  // The grid is off unless said: switched off, it is left unsaid, so a display stays sparse.
  if (Object.hasOwn(patch, "grid")) { if (normalized.grid) next.grid = true; else delete next.grid; }
  if (normalized.appearance) next.appearance = normalized.appearance;
  if (normalized.camera) next.camera = { ...base.camera, ...normalized.camera };
  if (normalized.exploded) next.exploded = { ...base.exploded, ...normalized.exploded };
  if (normalized.clip) next.clip = buildStepClipPatch(base.clip, normalized.clip);
  return normalizeViewSettings(next);
}

/** Preview's settings with `patch` merged in, each group field by field. */
export function mergePreviewSettings(current, patch) {
  const base = normalizePreviewSettings(current ?? {});
  const next = { ...base };
  for (const [group, values] of Object.entries(normalizePreviewSettings(patch))) next[group] = { ...base[group], ...values };
  return normalizePreviewSettings(next);
}

// A camera command carries both pose and optional View controls. Explicit lens
// or projection edits change the shared camera; a pose-only command leaves it alone. The tools
// view, where a camera command edits them, is never in Render (Preview's alone).
export function viewerDisplaySettingsForCamera(current, camera) {
  const controls = {
    ...(camera?.projection ? { projection: camera.projection } : {}),
    ...(camera?.focalLength != null ? { focalLength: camera.focalLength } : {})
  };
  return Object.keys(controls).length
    ? mergeViewerDisplaySettings(current, { camera: controls })
    : normalizeViewSettings(current);
}

export function cameraForViewSettings(camera, display, options) {
  if (!camera) return null;
  const settings = resolveViewSettings(display, options).camera;
  return { ...camera, projection: settings.projection, focalLength: settings.focalLength };
}

/** Presentation suspends model effects without changing the per-file settings. */
export function previewDisplaySettings(display) {
  return { ...display, clip: { ...display.clip, enabled: false },
    exploded: { ...display.exploded, enabled: false, amount: 0 } };
}

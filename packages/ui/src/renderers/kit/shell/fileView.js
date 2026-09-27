import { normalizeViewSettings } from "@hardcore/core/common/viewSettings.js";
import { annotatePerspectiveSnapshot, clonePerspectiveSnapshot } from "@hardcore/core/lib/perspective.js";
import { normalizePlayback } from "../tools/playbar/playbackPreferences.js";

// A file's view: the one record the host keeps for a file in its tab, under
// `[root, file path, renderer id]` (`@hardcore/ui/tab-store`). One flat, versioned object:
//
//   { version: 2, camera, display, playback, renderer }
//
//   camera    the renderer's own camera value, opaque here: a perspective snapshot for a scene
//             (`readShellCamera`), a plane transform for a drawing. Null is "fit the model".
//   display   the Display settings, every section of them.
//   playback  preview's Playback settings (`tools/playbar/playbackPreferences.js`): orbit on or
//             off and its speed, Autoplay, and the speed and loop chosen for the routine.
//   renderer  the renderer's own slices of view state, each `{ signature, value }`: what the
//             slice was written against. A slice comes back only while its signature still
//             matches the one the renderer declares for the file on screen — a rebuilt model
//             has different parts, so ids from the old one are not ids at all — while the
//             camera and the display are always kept.
//
// Reading is forgiving (a record another version wrote, or a slice that no longer fits, is
// simply not restored); writing is exact. Nothing here touches storage: the host owns that.
// What the view never holds: the tool in hand, a selection, measurements, ink, preview, a
// routine's time — every open starts those afresh.

export const FILE_VIEW_VERSION = 2;
/** The coordinate system a scoped camera (a live `setCamera`) is expressed in. */
export const SHELL_CAMERA_COORDINATES = "cad-z-up-v1";

const plainObject = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const text = value => String(value ?? "");

function readDisplay(value) {
  if (!plainObject(value)) return normalizeViewSettings({});
  // A record is never rewritten to fit: settings this build cannot read are the defaults.
  try { return normalizeViewSettings(value); } catch { return normalizeViewSettings({}); }
}

/**
 * What the viewport is asked to present, as one token. The viewport echoes it back
 * (`onPresentationChange`), so "what is on screen is what was asked for" is a string
 * comparison. A renderer that must answer that question itself — a live preview asking
 * whether its own result has landed — builds the same token from the same two parts.
 */
export function shellPresentationKey(modelKey, revisionKey = "") {
  return modelKey ? `${modelKey}:${revisionKey}:complete` : "";
}

/** A camera scoped to the model it frames, so it is never applied to another. */
export function scopeShellCamera(camera, modelKey, sceneScaleMode) {
  const snapshot = clonePerspectiveSnapshot(camera);
  return snapshot ? annotatePerspectiveSnapshot(snapshot, { modelKey, sceneScaleMode, coordinateSystem: SHELL_CAMERA_COORDINATES }) : null;
}

/** A scene camera as the record holds it: the pose, the lens and the projection, and no scope. */
export function plainShellCamera(camera) {
  const snapshot = clonePerspectiveSnapshot(camera);
  if (!snapshot) return null;
  const { modelKey, sceneScaleMode, coordinateSystem, ...plain } = snapshot;
  return plain;
}

/**
 * @param {unknown} raw  What the host handed back (`RendererViewProps.state`).
 * @param {Record<string, string>} [signatures]  Per renderer slice, what it must have been
 *   written against to come back; a slice declared without one comes back when it was
 *   written without one.
 * @returns {{ version: number, camera: unknown, display: object, playback: object, renderer: Record<string, unknown> }}
 */
export function readFileView(raw, signatures = {}) {
  const record = plainObject(raw) && raw.version === FILE_VIEW_VERSION ? raw : {};
  const renderer = {};
  for (const [slice, stored] of Object.entries(plainObject(record.renderer) ? record.renderer : {})) {
    if (!plainObject(stored) || text(stored.signature) !== text(signatures[slice])) continue;
    renderer[slice] = structuredClone(stored.value);
  }
  return {
    version: FILE_VIEW_VERSION,
    camera: plainObject(record.camera) ? structuredClone(record.camera) : null,
    display: readDisplay(record.display),
    playback: normalizePlayback(record.playback),
    renderer
  };
}

/**
 * The renderer's slices exactly as stored, whatever they were written against: what a renderer
 * that cannot yet say what its slices are hands back, so a write of the camera or the display
 * does not lose them.
 * @returns {{ values: Record<string, unknown>, signatures: Record<string, string> }}
 */
export function readFileViewSlices(raw) {
  const record = plainObject(raw) && raw.version === FILE_VIEW_VERSION ? raw : {};
  const values = {}, signatures = {};
  for (const [slice, stored] of Object.entries(plainObject(record.renderer) ? record.renderer : {})) {
    if (!plainObject(stored)) continue;
    values[slice] = structuredClone(stored.value);
    signatures[slice] = text(stored.signature);
  }
  return { values, signatures };
}

/**
 * The record for the view as it is now.
 * @param {{ camera?: unknown, display?: object, playback?: object, renderer?: Record<string, unknown>,
 *   signatures?: Record<string, string> }} view
 */
export function writeFileView({ camera = null, display = null, playback = null, renderer = {}, signatures = {} } = {}) {
  const slices = {};
  for (const [slice, value] of Object.entries(plainObject(renderer) ? renderer : {})) {
    if (value === undefined) continue;
    slices[slice] = { signature: text(signatures[slice]), value: structuredClone(value) };
  }
  return {
    version: FILE_VIEW_VERSION,
    camera: plainObject(camera) ? structuredClone(camera) : null,
    display: plainObject(display) ? structuredClone(display) : null,
    playback: normalizePlayback(playback),
    renderer: slices
  };
}

export function fileViewsEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

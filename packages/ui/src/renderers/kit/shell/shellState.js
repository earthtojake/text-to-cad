import { normalizeViewSettings } from "@hardcore/core/common/viewSettings.js";
import { annotatePerspectiveSnapshot, clonePerspectiveSnapshot } from "@hardcore/core/lib/perspective.js";

// The per-file record a shell renderer keeps in the host's state, keyed by the
// host as `[file path, renderer id]`. One flat, versioned object: the camera the
// file uses only while mounted, its Display settings, the tool a saved tab may record, and one
// slot that is the renderer's own business. Which panel is open is the host's, not
// the file's.
//
//   { version: 1, camera, display, tool, renderer }
//
// Reading is forgiving (a record another version wrote is simply not restored);
// writing is exact. Nothing here touches storage: the host owns that.

export const SHELL_STATE_VERSION = 1;
/** The coordinate system every stored camera is expressed in. */
export const SHELL_CAMERA_COORDINATES = "cad-z-up-v1";

const plainObject = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);

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

/** The stored camera, scoped to the model it frames so it is never applied to another. */
export function scopeShellCamera(camera, modelKey, sceneScaleMode) {
  const snapshot = clonePerspectiveSnapshot(camera);
  return snapshot ? annotatePerspectiveSnapshot(snapshot, { modelKey, sceneScaleMode, coordinateSystem: SHELL_CAMERA_COORDINATES }) : null;
}

/**
 * @param {unknown} raw  What the host handed back (`RendererViewProps.state`).
 * @returns {{ version: 1, camera: object | null, display: object, tool: string, renderer: object }}
 */
export function readShellState(raw) {
  const record = plainObject(raw) && raw.version === SHELL_STATE_VERSION ? raw : {};
  return {
    version: SHELL_STATE_VERSION,
    camera: null, // Camera framing is session-only; ignore cameras from older saved records.
    display: readDisplay(record.display),
    tool: typeof record.tool === "string" ? record.tool : "",
    renderer: plainObject(record.renderer) ? structuredClone(record.renderer) : {}
  };
}

/** The record for the view as it is now. `tool` is what `toolModes.persisted` allows a tab to record. */
export function writeShellState({ camera = null, display = {}, tool = "", renderer = {} } = {}) {
  return {
    version: SHELL_STATE_VERSION,
    camera: null,
    display: structuredClone(display),
    tool: String(tool || ""),
    renderer: plainObject(renderer) ? structuredClone(renderer) : {}
  };
}

export function shellStatesEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

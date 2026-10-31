import { english } from "../../../i18n/core.js";
import { isProgressKey } from "./progressEvent.js";

// The loading and view-update lines are a closed vocabulary (`loadingState.js` names every step the
// screen shows; a renderer's own wait and an update say one of these), kept in English as the
// renderers' and tests' identifiers. The screen says them in the view's language: each by its key.
// The engine's progress events are the other half of the vocabulary: `loadingState.js` names their
// stage by its key itself (`progress.<kind>.<stage>`, `progressEvent.js`), which `t` says directly.
const KEYS = Object.freeze({
  "Finding file": "loading.findingFile",
  "Opening model": "loading.openingModel",
  "Reading model": "loading.readingModel",
  "Importing model": "loading.importingModel",
  "Building model": "loading.buildingModel",
  "Meshing parts": "loading.meshingParts",
  "Loading geometry": "loading.loadingGeometry",
  "Preparing view": "loading.preparingView",
  "Reading drawing": "loading.readingDrawing",
  "Updating model…": "viewUpdate.updatingModel",
  "Updating drawing…": "viewUpdate.updatingDrawing",
  "Updating view…": "viewUpdate.updatingView",
  "Preparing section view…": "viewUpdate.preparingSection",
});
const MESHING = /^Meshing parts( \d+\/\d+)?…$/;

/**
 * A loading or update line in `t`'s language. A line outside the vocabulary (a file's own words)
 * shows as it came.
 * @param {string | undefined | null} label
 * @param {(key: string, params?: Record<string, unknown>) => string} [t]
 */
export function statusLabel(label, t = english) {
  if (!label) return label;
  const key = KEYS[label];
  if (key) return t(key);
  if (isProgressKey(label)) return t(label);
  const meshing = MESHING.exec(label);
  return meshing ? t("viewUpdate.meshingParts", { counts: meshing[1] || "" }) : label;
}

/**
 * An update status's line in `t`'s language: its label, and for the engine's progress event its
 * count beside it, in flight ("Writing files 1/2…").
 * @param {{ label?: string, counts?: string }} status
 * @param {(key: string, params?: Record<string, unknown>) => string} [t]
 */
export function statusLine(status, t = english) {
  const label = statusLabel(status?.label, t);
  if (!isProgressKey(status?.label)) return label;
  return t("viewUpdate.inProgress", { label, counts: status.counts ? ` ${status.counts}` : "" });
}

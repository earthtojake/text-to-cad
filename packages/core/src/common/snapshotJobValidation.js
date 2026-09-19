import { CAD_DISPLAY_MODE, normalizeDisplayMode } from "./displaySettings.js";

export function validateSnapshotRenderJob(job = {}) {
  if (Object.hasOwn(job, "theme")) {
    throw new Error("Unsupported snapshot field: theme");
  }
  if (Object.hasOwn(job, "render")) {
    throw new Error("Unsupported snapshot field: render; use display.mode 'render'");
  }
  if (
    job.display?.mode != null &&
    normalizeDisplayMode(job.display.mode) === CAD_DISPLAY_MODE.RENDER &&
    String(job.mode || "view").trim().toLowerCase() !== "view"
  ) {
    throw new Error("Render display supports only view mode");
  }
}

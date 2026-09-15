import { normalizeRenderPayload } from "./sceneSettings.js";

// Snapshot requests have one rendering path. Unlike the viewer's dormant CAD
// session state, explicitly supplied CAD controls must never be ignored here.
const CAD_ONLY_RENDER_KEYS = Object.freeze([
  "camera", "display", "selection", "jointValues", "quality"
]);

export function validateSnapshotRenderJob(job = {}) {
  if (Object.hasOwn(job, "theme")) {
    throw new Error("Unsupported snapshot field: theme");
  }
  if (!Object.hasOwn(job, "render")) return;
  normalizeRenderPayload(job.render);
  if (String(job.mode || "view").trim().toLowerCase() !== "view") {
    throw new Error("Photographic Render supports only view mode");
  }
  const conflicts = CAD_ONLY_RENDER_KEYS.filter((key) => Object.hasOwn(job, key));
  if (conflicts.length) {
    throw new Error(`render cannot be combined with CAD-only fields: ${conflicts.join(", ")}`);
  }
}

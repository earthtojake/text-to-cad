import { normalizeViewSettings, resolveViewSettings } from "./viewSettings.js";

// A job's camera poses and frames the view. Projection and focal length are
// display.camera's, so a job's camera has no such fields, though the viewer's
// own camera spec (camera.js) carries them.
const DISPLAY_CAMERA_FIELDS = Object.freeze(["projection", "focalLength"]);

export function validateSnapshotRenderJob(job = {}) {
  normalizeViewSettings(Object.hasOwn(job, "display") ? job.display : {});
  for (const camera of [job.camera, ...(Array.isArray(job.outputs) ? job.outputs.map(output => output.camera) : [])]) {
    if (camera && typeof camera === "object") {
      const unsupported = DISPLAY_CAMERA_FIELDS.filter(key => Object.hasOwn(camera, key));
      if (unsupported.length) throw new Error(`Unsupported camera fields: ${unsupported.join(", ")}`);
    }
  }
  if (resolveViewSettings(job.display ?? {}).lighting.enabled && String(job.mode || "view").trim().toLowerCase() !== "view") {
    throw new Error("Render display supports only view mode");
  }
}

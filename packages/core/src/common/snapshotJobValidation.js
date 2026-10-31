import { normalizeAnnotation } from "./annotation.js";
import { normalizeViewSettings } from "./viewSettings.js";

export function validateSnapshotRenderJob(job = {}) {
  const mode = String(job.mode || "view").trim().toLowerCase();
  if (!["view", "list"].includes(mode)) {
    throw new Error(`Unsupported render mode: ${mode}. Modes: list, view`);
  }
  for (const field of ["theme", "section"]) {
    if (Object.hasOwn(job, field)) throw new Error(`Unsupported snapshot field: ${field}`);
  }
  // Preview is its own request beside the display, never a display mode: `preview: true`.
  if (Object.hasOwn(job, "preview") && typeof job.preview !== "boolean") throw new Error("preview must be a boolean");
  normalizeViewSettings(Object.hasOwn(job, "display") ? job.display : {});
  // The ink drawn over the model (`annotation.js`): refused before anything loads, by what is wrong.
  if (job.annotation != null) normalizeAnnotation(job.annotation);
  for (const camera of [job.camera, ...(Array.isArray(job.outputs) ? job.outputs.map(output => output.camera) : [])]) {
    if (camera && typeof camera === "object") {
      const moved = ["projection", "focalLength"].filter(key => Object.hasOwn(camera, key));
      if (moved.length) throw new Error(`Camera ${moved.join(", ")} moved to display.camera`);
    }
  }
  if (job.preview === true && String(job.mode || "view").trim().toLowerCase() !== "view") {
    throw new Error("Preview supports only view mode");
  }
}

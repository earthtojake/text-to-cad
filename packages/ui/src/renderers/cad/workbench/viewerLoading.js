import { formatArtifactProgress } from "./artifactProgress.js";

export { prolongedLoadingMessage } from "../../kit/status/loadingMessage.js";

// Internal phases stay diagnostic data. The screen describes the user's wait.
export function loadingProgress(progress, { finding = false, preparing = false } = {}) {
  const hint = `${progress?.phase || ""} ${progress?.label || ""}`.toLowerCase();
  const label = finding ? "Finding file"
    : preparing ? "Preparing view"
    : /catalog|metadata|finding/.test(hint) ? "Finding file"
    : /geometry|component|mesh|surface|tessellat/.test(hint) && !/building geometry/.test(hint) ? "Loading geometry"
    : /view|finaliz|writing|saving|saved|module|building assembly|building robot/.test(hint) ? "Preparing view"
    : "Reading model";
  const frame = formatArtifactProgress(progress);
  return {
    label,
    detail: String(progress?.detail || ""),
    counts: !finding && !preparing ? frame?.counts || "" : "",
    percent: !finding && !preparing && frame?.determinate ? frame.percent : null,
    connectionLost: progress?.connectionLost || null,
  };
}

export function viewerLoadingState({
  busy = false, editPending = false, previousView = false,
  currentPreview = false, error = null, progress = null,
  finding = false, preparing = false,
} = {}) {
  const failed = error && (typeof error === "string" || error.severity !== "warning" || error.blocking === true);
  const active = !failed && (busy || (editPending && !currentPreview));
  return {
    opening: active && !previousView,
    updating: active && previousView,
    busy: active,
    progress: loadingProgress(progress, { finding, preparing }),
  };
}

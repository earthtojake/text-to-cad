import {
  stepArtifactHasRenderableGlb,
  stepArtifactStatusMessage
} from "./fileStatusItems.js";
import { failedStepArtifact } from "./stepArtifactStatus.js";
import { fileKey } from "./entryPaths.js";
import { failureAlert, isViewerServiceFailure, noGeometryAlert } from "../../kit/status/loadAlerts.js";

export function buildViewerMeshAlert(entry, hasMeshData, loadError, artifact = null, { partial = false } = {}) {
  const fileRef = fileKey(entry);
  if (!fileRef) {
    return null;
  }


  if (artifact?.status === "failed") {
    const alert = failureAlert(fileRef, artifact.error, artifact.failure, true);
    return hasMeshData && !partial ? {
      ...alert,
      blocking: false,
      message: `${alert.message} The existing model remains visible.`
    } : alert;
  }

  const stepArtifactError = failedStepArtifact(entry);
  if (stepArtifactError && !hasMeshData) {
    const code = String(stepArtifactError.error || "").trim();
    const missingGlb = code === "missing_glb";
    const summary = missingGlb ? "STEP artifact missing" : "STEP artifact unavailable";
    const renderableGlb = stepArtifactHasRenderableGlb(entry);
    if (!renderableGlb || !loadError) {
      return {
        severity: renderableGlb ? "warning" : "error",
        ...(renderableGlb ? { blocking: false } : {}),
        summary,
        title: summary,
        message: `“${fileRef}”: ${stepArtifactStatusMessage(stepArtifactError)}`,
        recovery: "Reload to check for rebuilt display assets. If the problem persists, check the viewer’s terminal output.",
        details: `File: ${fileRef}\n${String(stepArtifactError.message || code)}`,
        reload: true
      };
    }
  }

  if (loadError) {
    const alert = failureAlert(fileRef, loadError?.message || loadError, loadError?.failure);
    return hasMeshData && !partial ? {
      ...alert,
      blocking: false,
      message: `${alert.message} The existing model remains visible.`
    } : alert;
  }

  if (!hasMeshData) {
    return noGeometryAlert(fileRef);
  }

  return null;
}

/**
 * Turn a live-edit failure into the same actionable alert used by file loads.
 * Feed disconnects and recoverable preview expiry stay quiet; neither means the
 * model or its saved file is invalid.
 */
export function buildViewerEditAlert(editingState, showingCurrentPreview = false, hasGeometry = false) {
  const state = String(editingState?.state || "").trim().toLowerCase();
  const detail = String(editingState?.error || "").trim();
  if (!editingState || state === "disconnected") {
    return null;
  }

  const usableModelVisible = Boolean(showingCurrentPreview || hasGeometry);
  const hasSavedFallback = Boolean(editingState.saved || editingState.retainedSaved);
  const missingPreviewBlocksOpen = editingState.previewUnavailable
    && !usableModelVisible
    && !hasSavedFallback;
  const previewOnlyFailure = editingState.previewUnavailable
    && /preview|cache|no longer available/i.test(detail);
  if ((editingState.previewUnavailable && !missingPreviewBlocksOpen && previewOnlyFailure)
      || (state !== "failed" && !missingPreviewBlocksOpen)) {
    return null;
  }

  const actualDetail = detail || (missingPreviewBlocksOpen
    ? "The live model is no longer available."
    : "The viewer returned no diagnostic for the failed update.");
  const details = [
    editingState.file || editingState.output
      ? `File: ${editingState.file || editingState.output}`
      : "",
    editingState.revision ? `Revision: ${editingState.revision}` : "",
    showingCurrentPreview ? "Operation: writing the STEP file" : "Operation: updating the model",
    actualDetail
  ].filter(Boolean).join("\n");
  const common = {
    severity: "error",
    details,
    reload: true,
    ...(usableModelVisible ? { blocking: false } : {})
  };

  if (showingCurrentPreview) {
    return {
      ...common,
      summary: "Update failed",
      title: "Couldn’t write the STEP file",
      message: "The updated model is visible, but the STEP file could not be written.",
      reason: actualDetail,
      recovery: "Check the diagnostic in Details and the viewer’s terminal output, then run the model again."
    };
  }

  if (isViewerServiceFailure(editingState.failure, actualDetail)) {
    return {
      ...common,
      kind: "service",
      summary: "Viewer service failed",
      title: "Couldn’t prepare the model",
      message: usableModelVisible
        ? "The viewer couldn’t prepare the latest update. You’re still viewing the previous version."
        : "The viewer’s processing service failed.",
      recovery: "Try again. If this continues, check the viewer’s terminal output."
    };
  }

  return {
    ...common,
    summary: usableModelVisible ? "Update failed" : "Open failed",
    title: usableModelVisible ? "Couldn’t update the model" : "Couldn’t open the model",
    message: usableModelVisible
      ? "The latest update couldn’t be loaded. You’re still viewing the previous version."
      : "The model could not be prepared for display.",
    reason: actualDetail,
    recovery: "Check the diagnostic in Details, correct the model, then run it again."
  };
}

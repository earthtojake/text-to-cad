import { entrySourceFormat } from "cadgen-js/lib/fileFormats.js";
import {
  ASSET_KIND,
  renderCapabilities
} from "cadgen-js/lib/renderCapabilities.js";
import {
  failedStepArtifact,
  stepArtifactHasRenderableGlb,
  stepArtifactStatusMessage
} from "./stepArtifactStatus.js";
import { fileKey } from "./sidebar.js";

// The summary belongs in the compact file badge. The viewport shows one title,
// an explanation with a next step, and the complete diagnostic on demand.
function isViewerServiceFailure(failure, detail) {
  const kind = String(failure?.kind || "").toLowerCase();
  return ["service", "worker", "daemon", "broker", "status", "timeout"].includes(kind) || /\b(?:artifact|model) (?:worker|broker)\b|\bworker unavailable\b|\bservice unavailable\b|artifact request failed|lost its protocol|no cold retry|no unaccounted retry/i.test(detail);
}

function failureAlert(fileRef, error, failure, compile = false) {
  const detail = String(failure?.detail || error || "").trim();
  let kind = failure?.kind || (/^(Failed to fetch|Load failed|NetworkError.*|network failed)$/i.test(detail)
    ? "network" : compile ? "compile" : "mesh");
  if (isViewerServiceFailure(failure, detail)) {
    kind = "service";
  }
  const operation = failure?.operation || (compile ? "preparing display assets" : "loading geometry");
  const diagnostics = [
    `File: ${fileRef}`, `Operation: ${operation}`,
    failure?.url && `Request: ${failure.method || "GET"} ${failure.url}`,
    failure?.status && `HTTP status: ${failure.status}`,
    detail
  ].filter(Boolean).join("\n");
  const common = { severity: "error", kind, details: diagnostics };
  if (kind === "network") return {
    ...common, summary: "Connection lost", title: "Can’t reach the viewer",
    tooltip: "The browser lost contact with the viewer while loading the model.",
    message: `The browser lost contact with the viewer while ${operation} for “${fileRef}”. Check that the viewer is running and this tab has the correct address, then reload.`,
    ...(failure?.method === "POST" ? {
      recovery: "The build may still be running on the server. Reloading checks its status before starting any work."
    } : {}),
    reload: true
  };
  if (kind === "service") return {
    ...common, summary: "Viewer service failed", title: "Couldn’t prepare the model",
    tooltip: "The viewer couldn’t finish preparing the model for display.",
    message: ["status", "timeout"].includes(failure?.kind)
      ? "The viewer did not respond while preparing this model."
      : "The viewer couldn’t finish processing this model.",
    recovery: "Try again. If this continues, check the viewer’s terminal output.",
    reload: true
  };
  if (kind === "http" || kind === "response") return {
    ...common, summary: "Request failed", title: "The viewer couldn’t complete the request",
    tooltip: "The viewer returned an error while loading the model.",
    message: `${failure?.status ? `The server returned HTTP ${failure.status}` : "The server returned an unexpected response"} while ${operation} for “${fileRef}”.`,
    reason: detail,
    recovery: "Reload to try again. If this continues, check the viewer’s terminal output for the request shown in Details.",
    reload: true
  };
  return {
    ...common, summary: compile || kind === "compile" ? "Compile failed" : "Mesh load failed",
    title: compile || kind === "compile" ? "Couldn’t prepare the model" : "Couldn’t load the model",
    message: `“${fileRef}” could not be ${compile || kind === "compile" ? "prepared for display" : "loaded"}.`,
    reason: detail || "No diagnostic was returned by the viewer.",
    recovery: compile || kind === "compile"
      ? "Check the reported error and the viewer’s terminal output. Correct or rebuild the source file, then reload."
      : "Check that the file is complete and readable, then reload. The full loading error is available in Details.",
    reload: true
  };
}

export function buildViewerAnnotationAlert(entry) {
  if (!entry?.annotationError || entry.editingPreview) return null;
  return {
    severity: "warning", blocking: false,
    title: "Some model settings are unavailable",
    tooltip: "The shape is visible, but some saved model settings could not be read. Materials, animation, or joint controls may be unavailable.",
    message: "The geometry is visible, but its saved settings could not be read. Kinematics or appearance settings may be missing.",
    recovery: "Rebuild the model with the current cadgen version, then reload.",
    details: `File: ${fileKey(entry)}\n${entry.annotationError}`,
  };
}

export function buildViewerStaleRuntimeAlert(serverInfo, runtimeError = "") {
  const serverDetail = String(runtimeError || "").trim();
  if (!serverInfo?.restartRequired && !/CAD Viewer code changed after this server started/i.test(serverDetail)) {
    return null;
  }
  const port = Number(serverInfo?.port) || "unknown";
  const root = String(serverInfo?.rootPath || "unknown");
  return {
    severity: "error",
    kind: "service",
    summary: "Viewer restart required",
    code: "viewer_restart_required",
    title: "Restart this CAD Viewer",
    tooltip: "The viewer was updated after this server started. Restart the viewer to load the new code.",
    message: "The viewer’s code changed after its server started, so the browser and Python backend may no longer match.",
    recovery: "Run `cadgen viewer` from the same directory, then open the URL it prints. "
      + "Reloading this page alone cannot update the Python server.",
    details: [
      `Port: ${port}`,
      `Root: ${root}`,
      `Started identity: ${String(serverInfo?.identityToken || "unknown")}`,
      `Current identity: ${String(serverInfo?.currentIdentityToken || "unknown")}`,
      serverDetail && `Server response: ${serverDetail}`,
    ].filter(Boolean).join("\n"),
  };
}

export function resolveFileStatusAlert(fileStatus, viewerAlert = null, annotationAlert = null) {
  if (!fileStatus || fileStatus.busy) {
    return null;
  }
  if (viewerAlert) {
    return viewerAlert;
  }
  if (annotationAlert) {
    return annotationAlert;
  }
  if (!["error", "warning"].includes(fileStatus.tone)) {
    return null;
  }
  return {
    severity: fileStatus.tone,
    title: fileStatus.label,
    message: fileStatus.title,
    reload: fileStatus.tone === "error",
    blocking: false,
  };
}

export function fileStatusAlertKey(fileRef, alert) {
  if (!alert) {
    return "";
  }
  return JSON.stringify([
    String(fileRef || ""),
    alert.severity || "",
    alert.kind || "",
    alert.summary || "",
    alert.title || "",
    alert.message || "",
    alert.reason || "",
    alert.recovery || "",
    alert.details || "",
  ]);
}

export function buildViewerMeshAlert(entry, hasMeshData, loadError, artifact = null, { partial = false } = {}) {
  const fileRef = fileKey(entry);
  if (!fileRef) {
    return null;
  }

  const sourceFormat = entrySourceFormat(entry);

  if (artifact?.status === "failed") {
    const alert = failureAlert(fileRef, artifact.error, artifact.failure, true);
    return hasMeshData && !partial ? {
      ...alert,
      blocking: false,
      message: `${alert.message} The existing model remains visible.`
    } : alert;
  }

  const stepArtifactError = failedStepArtifact(entry, sourceFormat);
  if (stepArtifactError && !hasMeshData) {
    const code = String(stepArtifactError.error || "").trim();
    const missingGlb = code === "missing_glb";
    const summary = missingGlb ? "STEP artifact missing" : "STEP artifact unavailable";
    const renderableGlb = stepArtifactHasRenderableGlb(entry);
    if (!renderableGlb || !loadError) {
      return {
        severity: renderableGlb ? "warning" : "error",
        ...(renderableGlb ? { blocking: false } : {}),
        compact: true,
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

  // A dimensioned DRAWING has no mesh BY DESIGN -- it encloses nothing to extrude
  // and renders as lines (issue #246). The profile is decided from the PARSED file
  // now, which this alert path cannot see, so any meshless DXF stays quiet: a
  // layout's mesh is built from the same parse, and a genuinely broken file
  // reports through loadError above.
  if (!hasMeshData && renderCapabilities(entrySourceFormat(entry)).assetKind === ASSET_KIND.DRAWING) {
    return null;
  }

  if (!hasMeshData) {
    return {
      severity: "error",
      summary: "Mesh unavailable",
      title: "No geometry to display",
      message: `“${fileRef}” is listed in the file browser, but loading it produced no visible geometry.`,
      recovery: "Check that the file contains a model and was saved completely, then reload.",
      reload: true
    };
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
      tooltip: "The viewer couldn’t finish preparing the updated model for display.",
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

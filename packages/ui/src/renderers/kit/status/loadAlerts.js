// Alerts for a file that failed to load, and the badge-to-dialog plumbing beside
// them. Nothing here knows what kind of file it is: a renderer hands over the
// file's name, the error its loader raised and (when the transport classified
// it) the failure record.

// The summary belongs in the compact file badge. The viewport shows one title,
// an explanation with a next step, and the complete diagnostic on demand.
export function isViewerServiceFailure(failure, detail) {
  const kind = String(failure?.kind || "").toLowerCase();
  return ["service", "worker", "daemon", "broker", "status", "timeout"].includes(kind) || /\b(?:artifact|model) (?:worker|broker)\b|\bworker unavailable\b|\bservice unavailable\b|artifact request failed|lost its protocol|no cold retry|no unaccounted retry/i.test(detail);
}

export function failureAlert(fileRef, error, failure, compile = false) {
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

/** The file is listed, loading raised nothing, and nothing came out of it. */
export function noGeometryAlert(fileRef) {
  return {
    severity: "error",
    summary: "Mesh unavailable",
    title: "No geometry to display",
    message: `“${fileRef}” is listed in the file browser, but loading it produced no visible geometry.`,
    recovery: "Check that the file contains a model and was saved completely, then reload.",
    reload: true
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

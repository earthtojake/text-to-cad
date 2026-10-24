// Alerts for a file that failed to load. Nothing here knows what kind of file it
// is: a renderer hands over the file's name, the error its loader raised and (when
// the transport classified it) the failure record.

// The viewport's card shows one title, an explanation with a next step, and the
// complete diagnostic on demand; `summary` is the alert's short name.
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
    message: `The browser lost contact with the viewer while ${operation} for “${fileRef}”. Check that the viewer is running and this tab has the correct address, then reload.`,
    ...(failure?.method === "POST" ? {
      recovery: "The build may still be running on the server. Reloading checks its status before starting any work."
    } : {}),
    reload: true
  };
  if (kind === "service") return {
    ...common, summary: "Viewer service failed", title: "Couldn’t prepare the model",
    message: ["status", "timeout"].includes(failure?.kind)
      ? "The viewer did not respond while preparing this model."
      : "The viewer couldn’t finish processing this model.",
    recovery: "Try again. If this continues, check the viewer’s terminal output.",
    reload: true
  };
  if (kind === "http" || kind === "response") return {
    ...common, summary: "Request failed", title: "The viewer couldn’t complete the request",
    message: `${failure?.status ? `The server returned HTTP ${failure.status}` : "The server returned an unexpected response"} while ${operation} for “${fileRef}”.`,
    reason: detail,
    recovery: "Reload to try again. If this continues, check the viewer’s terminal output for the request shown in Details.",
    reload: true
  };
  // The file refused to be read, so nothing is known about its contents: on Windows,
  // another program holding it, or saving or replacing it, arrives as a PermissionError.
  if (failure?.errorType === "PermissionError") return {
    ...common, summary: "File unreadable", title: "Couldn’t read the model",
    message: `“${fileRef}” could not be read.`,
    reason: detail,
    recovery: "Another program may have it open, or be saving, syncing or scanning it. Close it there or let that finish, then retry. If this continues, check that the folder can be read.",
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

/**
 * The file's last build failed (`failed`: the engine's record of it -- the model, its error and the
 * stage it reached): over a model on screen, the last version that built, the card is no block and
 * can be put away; the error is said, and held whole in the details. The view updates by itself
 * when a build succeeds, so there is nothing to retry here.
 * @param {string} fileRef
 * @param {{ model?: string, error?: string, progress?: { label?: string, detail?: string } | null }} failed
 * @param {boolean} hasModel  A version of the file is on screen.
 */
export function buildFailedAlert(fileRef, failed, hasModel) {
  const error = String(failed?.error || "").trim() || "The build returned no diagnostic.";
  const stage = [failed?.progress?.label, failed?.progress?.detail].filter(Boolean).join(" · ");
  const details = [`File: ${fileRef}`, failed?.model && `Model: ${failed.model}`, stage && `Stage: ${stage}`,
    "Operation: building the model", error].filter(Boolean).join("\n");
  // What was raised, the traceback's last line; the traceback itself is in the details.
  const raised = error.split("\n").map(line => line.trim()).filter(Boolean).at(-1);
  return {
    severity: "error", kind: "build", details, reason: raised,
    summary: hasModel ? "Update failed" : "Build failed",
    title: hasModel ? "Couldn’t update the model" : "Couldn’t build the model",
    message: hasModel ? "The model’s latest build failed. You’re still viewing the previous version." : `“${fileRef}” could not be built.`,
    recovery: "Correct the error in the model’s source: the view updates when a build succeeds.",
    ...(hasModel ? { blocking: false } : {})
  };
}

/**
 * A model the engine answers from its last build -- its cache, or the hold of a worker gone -- though
 * the code it was built from changed since (`stale`: the engine's words, what changed and the
 * command that builds it again). A warning beside the model on screen, put away like a failed
 * update; nothing reran, and nothing here runs the command. In the page's language (`t`).
 * @param {{ text?: string, changes?: string[], rebuild?: string | null }} stale
 * @param {(key: string) => string} t
 */
export function staleBuildAlert(stale, t) {
  return {
    severity: "warning", kind: "stale", blocking: false, report: false,
    title: t("alert.stale.title"),
    message: t("alert.stale.message"),
    recovery: stale?.rebuild || "",
    details: [...(stale?.changes || []), stale?.text].filter(Boolean).join("\n")
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

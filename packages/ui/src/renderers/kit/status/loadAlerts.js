// Alerts for a file that failed to load. Nothing here knows what kind of file it
// is: a renderer hands over the file's name, the error its loader raised and (when
// the transport classified it) the failure record.

// The viewport's card shows one title, an explanation with a next step, and the
// complete diagnostic on demand; `summary` is the alert's short name. Each is said in the
// language of the `t` a renderer hands over (English unless it does); the diagnostic in
// `details` stays English, as it is reported.
import { english } from "../../../i18n/core.js";
import { isProgressEvent, progressKey } from "./progressEvent.js";

export function isViewerServiceFailure(failure, detail) {
  const kind = String(failure?.kind || "").toLowerCase();
  return ["service", "worker", "daemon", "broker", "status", "timeout"].includes(kind) || /\b(?:artifact|model) (?:worker|broker)\b|\bworker unavailable\b|\bservice unavailable\b|artifact request failed|lost its protocol|no cold retry|no unaccounted retry/i.test(detail);
}

// The client names each request's operation by a token (`@text-to-cad/core/client`'s `request`):
// a sentence says it in words, the details keep the token. A token this kit has no words for (a
// family's own read) is the file being loaded; an operation already in words is said as it is,
// the kit's own two by their keys.
const OPERATION_KEYS = Object.freeze({
  "engine-document": "alert.op.loadingModel", catalog: "alert.op.lookingUpFile", folder: "alert.op.readingFolder",
  search: "alert.op.searchingFolder", server: "alert.op.reachingViewer",
  "preparing display assets": "alert.op.preparingAssets", "loading geometry": "alert.op.loadingGeometry",
});
const operationWords = (operation, t) => OPERATION_KEYS[operation] ? t(OPERATION_KEYS[operation])
  : /\s/.test(operation) ? operation : t("alert.op.loadingFile");

export function failureAlert(fileRef, error, failure, compile = false, t = english) {
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
    ...common, summary: t("alert.network.summary"), title: t("alert.network.title"),
    message: t("alert.network.message", { operation: operationWords(operation, t), file: fileRef }),
    ...(failure?.method === "POST" ? {
      recovery: t("alert.network.recoveryPost")
    } : {}),
    reload: true
  };
  if (kind === "service") return {
    ...common, summary: t("alert.service.summary"), title: t("alert.prepareFailed"),
    message: ["status", "timeout"].includes(failure?.kind)
      ? t("alert.service.noResponse")
      : t("alert.service.unfinished"),
    recovery: t("alert.service.recovery"),
    reload: true
  };
  if (kind === "http" || kind === "response") return {
    ...common, summary: t("alert.request.summary"), title: t("alert.request.title"),
    message: failure?.status
      ? t("alert.request.status", { status: failure.status, operation: operationWords(operation, t), file: fileRef })
      : t("alert.request.unexpected", { operation: operationWords(operation, t), file: fileRef }),
    reason: detail,
    recovery: t("alert.request.recovery"),
    reload: true
  };
  // The file refused to be read, so nothing is known about its contents: on Windows,
  // another program holding it, or saving or replacing it, arrives as a PermissionError.
  if (failure?.errorType === "PermissionError") return {
    ...common, summary: t("alert.unreadable.summary"), title: t("alert.unreadable.title"),
    message: t("alert.unreadable.message", { file: fileRef }),
    reason: detail,
    recovery: t("alert.unreadable.recovery"),
    reload: true
  };
  return {
    ...common, summary: t(compile || kind === "compile" ? "alert.compile.summary" : "alert.load.summary"),
    title: t(compile || kind === "compile" ? "alert.prepareFailed" : "alert.load.title"),
    message: t(compile || kind === "compile" ? "alert.compile.message" : "alert.load.message", { file: fileRef }),
    reason: detail || t("alert.noDiagnostic"),
    recovery: compile || kind === "compile"
      ? t("alert.compile.recovery")
      : t("alert.load.recovery"),
    reload: true
  };
}

/**
 * The file's last build failed (`failed`: the engine's record of it -- the model, its error and the
 * stage it reached, its last progress event): over a model on screen, the last version that built,
 * the card is no block and can be put away; the error is said, and held whole in the details (the
 * stage in English, as the details are). The view updates by itself when a build succeeds, so there
 * is nothing to retry here.
 * @param {string} fileRef
 * @param {{ model?: string, error?: string, progress?: { kind?: string, stage?: string, detail?: string } | null }} failed
 * @param {boolean} hasModel  A version of the file is on screen.
 * @param {(key: string, params?: Record<string, unknown>) => string} [t]
 */
export function buildFailedAlert(fileRef, failed, hasModel, t = english) {
  const error = String(failed?.error || "").trim() || t("alert.build.noDiagnostic");
  const reached = isProgressEvent(failed?.progress) ? english(progressKey(failed.progress)) : "";
  const stage = [reached, failed?.progress?.detail].filter(Boolean).join(" · ");
  const details = [`File: ${fileRef}`, failed?.model && `Model: ${failed.model}`, stage && `Stage: ${stage}`,
    "Operation: building the model", error].filter(Boolean).join("\n");
  // What was raised, the traceback's last line; the traceback itself is in the details.
  const raised = error.split("\n").map(line => line.trim()).filter(Boolean).at(-1);
  return {
    severity: "error", kind: "build", details, reason: raised,
    summary: t(hasModel ? "alert.update.summary" : "alert.build.summary"),
    title: t(hasModel ? "alert.update.title" : "alert.build.title"),
    message: hasModel ? t("alert.update.message") : t("alert.build.message", { file: fileRef }),
    recovery: t("alert.build.recovery"),
    ...(hasModel ? { blocking: false } : {})
  };
}

/** The file is listed, loading raised nothing, and nothing came out of it. */
export function noGeometryAlert(fileRef, t = english) {
  return {
    severity: "error",
    summary: t("alert.empty.summary"),
    title: t("alert.empty.title"),
    message: t("alert.empty.message", { file: fileRef }),
    recovery: t("alert.empty.recovery"),
    reload: true
  };
}

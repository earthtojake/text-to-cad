// The decision logic behind useArtifact, as pure functions.
//
// Extracted so it can be tested directly: the rules below are where the client decides
// whether to START a build or WATCH someone else's, and getting that wrong is expensive
// (a duplicate multi-minute OCP build) but invisible in a rendered component.

export const ARTIFACT_ACTION_READY = "rendered";
export const ARTIFACT_ACTION_ERROR = "failed";
export const ARTIFACT_ACTION_ATTACH = "attach";
export const ARTIFACT_ACTION_BUILD = "build";

/**
 * What the client should do about a status payload from `GET /__cad/artifact`.
 *
 * Only `not-compiled` starts a compile. `compiling` means a job for this document is
 * already in cadgen's pool — a `python model.py` in a terminal, another viewer tab — so we
 * attach to that job and watch it. POSTing there would only queue a duplicate.
 *
 * `blocked` is the server saying the document has no tree AND a job for it is already
 * running: attach rather than POST a second one.
 */
export function artifactActionFor(status) {
  const state = String(status?.state || "rendered");
  if (state === ARTIFACT_ACTION_READY) {
    return ARTIFACT_ACTION_READY;
  }
  if (state === ARTIFACT_ACTION_ERROR) {
    return ARTIFACT_ACTION_ERROR;
  }
  if (state === "compiling" || status?.blocked) {
    return ARTIFACT_ACTION_ATTACH;
  }
  return ARTIFACT_ACTION_BUILD;
}

/**
 * The advisory flag a `rendered` status may carry: `busy`, when another process
 * currently holds the model's generator. It changes nothing about what the
 * client DOES — the model renders — it is an honest badge for the file sheet.
 * (The old `stale` advisory died with content keying: an edited file resolves
 * to a different package key, so a stale-but-rendering package cannot exist.)
 * Returns null when there is nothing to surface, so `advisory` is falsy in
 * the overwhelmingly common case.
 */
export function artifactAdvisoryFor(status) {
  if (status?.busy !== true) {
    return null;
  }
  return {
    busy: true,
    runId: status?.runId ? String(status.runId) : "",
  };
}

/**
 * Reconcile a freshly polled status against the run whose bar is currently on screen.
 *
 * Returns `{ runId, progress, handedOff }`. The server's ratio is monotonic only WITHIN a
 * run, so when one run hands off to another (one dies and another starts; a CLI run ends
 * and the viewer's own begins) the old position must be dropped rather than carried —
 * carrying it is what made the bar jump backwards.
 */
export function reconcileArtifactRun(shownRunId, status, progress) {
  const runId = status?.runId ? String(status.runId) : null;
  const handedOff = runId !== null && shownRunId !== null && runId !== shownRunId;
  return {
    runId: runId === null ? shownRunId : runId,
    progress: handedOff ? null : progress || null,
    handedOff,
  };
}

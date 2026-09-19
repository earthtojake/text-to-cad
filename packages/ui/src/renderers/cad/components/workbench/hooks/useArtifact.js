import { useEffect, useRef, useState } from "react";

import { serverErrorMessage } from "@hardcore/core/client";
import {
  ARTIFACT_PROGRESS_FIRST_POLL_MS,
  ARTIFACT_PROGRESS_POLL_MS,
  ARTIFACT_STATUS_FAILURE_LIMIT,
  ARTIFACT_STATUS_TIMEOUT_MS,
  artifactProgressConnectionLost,
  artifactStatusFailure,
  normalizeArtifactProgress,
  refreshArtifactProgress
} from "../../../workbench/artifactProgress.js";
import {
  ARTIFACT_ACTION_ATTACH,
  ARTIFACT_ACTION_ERROR,
  ARTIFACT_ACTION_READY,
  artifactActionFor,
  artifactAdvisoryFor,
  reconcileArtifactRun
} from "../../../workbench/artifactResolution.js";
import { artifactWarningItems } from "../../../workbench/artifactWarnings.js";

// useArtifact — the client half of the render-artifact pipeline.
//
// For the selected entry it resolves a single status: `ready` (render it), `generating` (a (re)build
// is running — show a loading state), or `error` (a fatal build/source failure). A missing or stale
// cache is NOT surfaced as an issue: the hook simply triggers a build and reports `generating`.
//
// Optimistic-ready: a freshly-selected entry starts `ready` so a fresh model renders immediately with
// no flash; only when the freshness check comes back `needs-build` do we flip to `compiling` (and
// the caller hides the now-known-stale render assets) and POST a build. Direct-render entries
// (`enabled: false`) never hit the network and stay `ready`.
//
// While the build POST is in flight it is polled for PROGRESS. The POST is one long-lived request
// that resolves only when the build finishes, so the position has to come from somewhere else: a
// concurrent GET of the same status route, which reads the record the build writes as it works.
// The poll is strictly read-only — it never triggers a build of its own — so the single POST stays
// the only writer no matter how long it runs.
//
// ATTACH vs BUILD. Only `not-compiled` POSTs. When the server reports `compiling`, some other
// process already holds this model's lock — a `cad gen` in a terminal, another tab — and we watch
// its run instead, re-resolving when it ends. Previously every non-ready state POSTed, so opening a
// model during a long CLI build meant waiting out that build and then paying for a full duplicate
// rebuild. Progress carries the server's `runId`; when it changes the bar resets, because the
// reported ratio is monotonic only within a single run and carrying it across a handoff is what
// made the bar jump backwards.

// One shared empty list, so `warnings` keeps a stable identity across renders
// and the memo that builds the warning alert does not rerun for every frame.
const NO_WARNINGS = Object.freeze([]);

const READY = { status: "compiled", error: "", progress: null, advisory: null, warnings: NO_WARNINGS };

function isAbortError(error) {
  return error?.name === "AbortError";
}

export function useArtifact(fileRef, { enabled = true, freshnessKey = "", client } = {}) {
  const activeRef = String(enabled ? fileRef || "" : "").trim();
  const key = activeRef ? `${activeRef}:${freshnessKey}` : "";
  const [state, setState] = useState({ key: "", status: "compiled", error: "", progress: null });
  const requestSeqRef = useRef(0);

  useEffect(() => {
    if (!activeRef) {
      return undefined;
    }
    const seq = (requestSeqRef.current += 1);
    const controller = new AbortController();
    const isCurrent = () => seq === requestSeqRef.current && !controller.signal.aborted;
    const settle = (next) => {
      if (isCurrent()) {
        setState({ key, progress: null, ...next });
      }
    };

    // Polls the status route alongside the in-flight build and merges whatever position it
    // reports into the existing `generating` state. A single missed response retains the
    // last useful frame and marks the connection as lost; repeated misses become an
    // actionable status failure. The compile POST itself has no elapsed-time timeout.
    let pollTimer = 0;
    let statusFailures = 0;
    // A status GET already in flight may reject after the compile POST has completed.
    // Once a final result wins, that stale read must not put the same key back into a
    // waiting or failed state. A peer handoff reopens polling in showGenerating().
    let finished = false;
    // True when we are watching a build we did NOT start. Nothing else will tell us it
    // finished, so the poll has to notice the state leaving `generating` and re-resolve.
    let attached = false;
    const stopPolling = () => {
      if (pollTimer) {
        window.clearTimeout(pollTimer);
        pollTimer = 0;
      }
    };
    // The run this component is currently rendering a bar for. A build can hand off to a
    // different run (one dies, another starts; a CLI run finishes and the viewer's own
    // begins), and the server's ratio is monotonic only WITHIN a run — so carrying the old
    // position across a handoff is what made the bar jump backwards. On a new runId the
    // bar resets instead.
    let shownRunId = null;
    // Advisory warnings about the document's NEIGHBOURS. They ride every status
    // payload and mean nothing about the state, so the last successful READ owns
    // them: the compile POST answers without them and must not erase what the
    // status route reported about a file that is still sitting there.
    let warnings = NO_WARNINGS;
    const readWarnings = (status) => {
      const items = artifactWarningItems(status);
      warnings = items.length > 0 ? items : NO_WARNINGS;
    };

    const noteStatusFailure = (error) => {
      if (finished || !isCurrent() || controller.signal.aborted || isAbortError(error)) {
        return false;
      }
      statusFailures += 1;
      const source = error?.failure || { detail: error instanceof Error ? error.message : String(error) };
      const terminal = statusFailures >= ARTIFACT_STATUS_FAILURE_LIMIT;
      const failure = terminal ? artifactStatusFailure(error, statusFailures) : null;
      if (terminal) {
        finished = true;
        stopPolling();
      }
      setState((current) => {
        const progress = artifactProgressConnectionLost(
          current.key === key ? current.progress : null,
          source,
          statusFailures
        );
        const base = current.key === key
          ? current
          : { key, status: "compiling", error: "", progress, advisory: null, warnings };
        return terminal
          ? { ...base, status: "failed", error: failure.detail, failure, progress }
          : { ...base, progress };
      });
      return !terminal;
    };

    const statusReadSucceeded = () => {
      statusFailures = 0;
    };

    const mergeProgress = (status) => {
      if (finished || !isCurrent()) {
        return;
      }
      const reconciled = reconcileArtifactRun(
        shownRunId,
        status,
        refreshArtifactProgress(normalizeArtifactProgress(status?.progress))
      );
      shownRunId = reconciled.runId;
      if (!reconciled.progress && !reconciled.handedOff) {
        setState((current) => current.key === key && current.progress?.connectionLost
          ? { ...current, progress: null }
          : current);
        return;
      }
      setState((current) =>
        current.key === key ? { ...current, progress: reconciled.progress } : current
      );
    };

    const pollProgress = async () => {
      if (finished || !isCurrent() || controller.signal.aborted) {
        return;
      }
      let reported = "";
      try {
        const status = await client.requestArtifactStatus(activeRef, {
          signal: controller.signal,
          timeoutMs: ARTIFACT_STATUS_TIMEOUT_MS
        });
        statusReadSucceeded();
        readWarnings(status);
        reported = String(status?.state || "");
        mergeProgress(status);
      } catch (error) {
        if (!noteStatusFailure(error)) return;
      }
      // ATTACHED to a peer's build (we did not POST, so nothing else will tell us it
      // finished): keep polling until the run leaves `generating`, then re-resolve.
      if (!finished && attached && isCurrent() && !controller.signal.aborted && reported && reported !== "compiling") {
        stopPolling();
        resolve();
        return;
      }
      if (!finished && isCurrent() && !controller.signal.aborted) {
        pollTimer = window.setTimeout(pollProgress, ARTIFACT_PROGRESS_POLL_MS);
      }
    };

    const showGenerating = (status) => {
      finished = false;
      statusReadSucceeded();
      shownRunId = status?.runId ? String(status.runId) : null;
      settle({
        status: "compiling",
        error: "",
        warnings,
        progress: refreshArtifactProgress(normalizeArtifactProgress(status?.progress))
      });
    };

    async function resolve() {
      let readingStatus = true;
      try {
        const status = await client.requestArtifactStatus(activeRef, {
          signal: controller.signal,
          timeoutMs: ARTIFACT_STATUS_TIMEOUT_MS
        });
        readingStatus = false;
        statusReadSucceeded();
        readWarnings(status);
        if (!isCurrent()) {
          return;
        }
        const action = artifactActionFor(status);
        if (action === ARTIFACT_ACTION_READY) {
          // Ready may carry advisory flags (stale package compiled as-is, generator
          // busy elsewhere); keep them for the file sheet's status section.
          finished = true;
          stopPolling();
          settle({ ...READY, advisory: artifactAdvisoryFor(status), warnings });
          return;
        }
        if (action === ARTIFACT_ACTION_ERROR) {
          finished = true;
          stopPolling();
          settle({ status: "failed", error: serverErrorMessage(status), warnings });
          return;
        }
        if (action === ARTIFACT_ACTION_ATTACH) {
          // SOMEONE ELSE is already building this model (a `cad gen` in a terminal, or
          // another viewer tab). Watch their run and re-resolve when it ends.
          attached = true;
          showGenerating(status);
          pollTimer = window.setTimeout(pollProgress, ARTIFACT_PROGRESS_FIRST_POLL_MS);
          return;
        }
        // not-compiled -> we own the compile. The POST is one long-lived request that resolves
        // only when the build finishes, so its position comes from the concurrent status
        // poll below.
        attached = false;
        showGenerating(status);
        pollTimer = window.setTimeout(pollProgress, ARTIFACT_PROGRESS_FIRST_POLL_MS);
        const result = await client.requestArtifact(activeRef, { signal: controller.signal });
        finished = true;
        stopPolling();
        if (!isCurrent()) {
          return;
        }
        if (result?.ok && result.state === "compiling") {
          // The server handed us off to a peer that took the lock first. Attach to it
          // rather than reporting a failure.
          attached = true;
          showGenerating(result);
          pollTimer = window.setTimeout(pollProgress, ARTIFACT_PROGRESS_FIRST_POLL_MS);
          return;
        }
        settle(result?.ok && result.state === "compiled"
          ? { ...READY, advisory: artifactAdvisoryFor(result), warnings }
          : { status: "failed", error: serverErrorMessage(result), warnings });
      } catch (error) {
        if (readingStatus && noteStatusFailure(error)) {
          pollTimer = window.setTimeout(resolve, ARTIFACT_PROGRESS_POLL_MS);
          return;
        }
        if (readingStatus) return;
        finished = true;
        stopPolling();
        if (isCurrent() && !isAbortError(error) && !controller.signal.aborted) {
          settle({
            status: "failed", error: error instanceof Error ? error.message : String(error),
            warnings,
            failure: error?.failure || { kind: "response", operation: "checking display assets" }
          });
        }
      }
    }

    resolve();

    return () => {
      requestSeqRef.current += 1;
      finished = true;
      stopPolling();
      controller.abort();
    };
  }, [activeRef, key, client]);

  // Optimistic-ready until this exact key has settled, so a fresh selection renders without a flash.
  return state.key === key
    ? {
      status: state.status,
      error: state.error,
      failure: state.failure || null,
      progress: state.progress,
      advisory: state.advisory || null,
      warnings: state.warnings || NO_WARNINGS
    }
    : READY;
}

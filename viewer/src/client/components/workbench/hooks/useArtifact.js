import { useEffect, useRef, useState } from "react";

import { requestArtifact, requestArtifactStatus } from "../../../workbench/cadManifestStore.js";
import {
  ARTIFACT_PROGRESS_FIRST_POLL_MS,
  ARTIFACT_PROGRESS_POLL_MS,
  normalizeArtifactProgress
} from "../../../workbench/artifactProgress.js";
import {
  ARTIFACT_ACTION_ATTACH,
  ARTIFACT_ACTION_ERROR,
  ARTIFACT_ACTION_READY,
  artifactActionFor,
  reconcileArtifactRun
} from "../../../workbench/artifactResolution.js";

// useArtifact — the client half of the render-artifact pipeline.
//
// For the selected entry it resolves a single status: `ready` (render it), `generating` (a (re)build
// is running — show a loading state), or `error` (a fatal build/source failure). A missing or stale
// cache is NOT surfaced as an issue: the hook simply triggers a build and reports `generating`.
//
// Optimistic-ready: a freshly-selected entry starts `ready` so a fresh model renders immediately with
// no flash; only when the freshness check comes back `needs-build` do we flip to `generating` (and
// the caller hides the now-known-stale render assets) and POST a build. Direct-render entries
// (`enabled: false`) never hit the network and stay `ready`.
//
// While the build POST is in flight it is polled for PROGRESS. The POST is one long-lived request
// that resolves only when the build finishes, so the position has to come from somewhere else: a
// concurrent GET of the same status route, which reads the record the build writes as it works.
// The poll is strictly read-only — it never triggers a build of its own — so the single POST stays
// the only writer no matter how long it runs.
//
// ATTACH vs BUILD. Only `needs-build` POSTs. When the server reports `generating`, some other
// process already holds this model's lock — a `cad gen` in a terminal, another tab — and we watch
// its run instead, re-resolving when it ends. Previously every non-ready state POSTed, so opening a
// model during a long CLI build meant waiting out that build and then paying for a full duplicate
// rebuild. Progress carries the server's `runId`; when it changes the bar resets, because the
// reported ratio is monotonic only within a single run and carrying it across a handoff is what
// made the bar jump backwards.

const READY = { status: "ready", error: "", progress: null };

function isAbortError(error) {
  return error?.name === "AbortError" || /abort/i.test(String(error?.message || ""));
}

export function useArtifact(fileRef, { enabled = true, freshnessKey = "" } = {}) {
  const activeRef = String(enabled ? fileRef || "" : "").trim();
  const key = activeRef ? `${activeRef}:${freshnessKey}` : "";
  const [state, setState] = useState({ key: "", status: "ready", error: "", progress: null });
  const requestSeqRef = useRef(0);

  useEffect(() => {
    if (!activeRef) {
      return undefined;
    }
    const seq = (requestSeqRef.current += 1);
    const controller = new AbortController();
    const isCurrent = () => seq === requestSeqRef.current;
    const settle = (next) => {
      if (isCurrent()) {
        setState({ key, progress: null, ...next });
      }
    };

    // Polls the status route alongside the in-flight build and merges whatever position it
    // reports into the existing `generating` state. Any failure (a poll racing the build's
    // own request, a sidecar not written yet) simply leaves the last known progress in place —
    // this is decoration, and it must never turn into an error the user sees.
    let pollTimer = 0;
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

    const mergeProgress = (status) => {
      if (!isCurrent()) {
        return;
      }
      const reconciled = reconcileArtifactRun(
        shownRunId,
        status,
        normalizeArtifactProgress(status?.progress)
      );
      shownRunId = reconciled.runId;
      if (!reconciled.progress && !reconciled.handedOff) {
        return;
      }
      setState((current) =>
        current.key === key ? { ...current, progress: reconciled.progress } : current
      );
    };

    const pollProgress = async () => {
      if (!isCurrent() || controller.signal.aborted) {
        return;
      }
      let reported = "";
      try {
        const status = await requestArtifactStatus(activeRef, { signal: controller.signal });
        reported = String(status?.state || "");
        mergeProgress(status);
      } catch {
        // ignored on purpose — see above
      }
      // ATTACHED to a peer's build (we did not POST, so nothing else will tell us it
      // finished): keep polling until the run leaves `generating`, then re-resolve.
      if (attached && isCurrent() && !controller.signal.aborted && reported && reported !== "generating") {
        stopPolling();
        resolve();
        return;
      }
      if (isCurrent() && !controller.signal.aborted) {
        pollTimer = window.setTimeout(pollProgress, ARTIFACT_PROGRESS_POLL_MS);
      }
    };

    const showGenerating = (status) => {
      shownRunId = status?.runId ? String(status.runId) : null;
      settle({
        status: "generating",
        error: "",
        progress: normalizeArtifactProgress(status?.progress)
      });
    };

    async function resolve() {
      try {
        const status = await requestArtifactStatus(activeRef, { signal: controller.signal });
        if (!isCurrent()) {
          return;
        }
        const action = artifactActionFor(status);
        if (action === ARTIFACT_ACTION_READY) {
          settle(READY);
          return;
        }
        if (action === ARTIFACT_ACTION_ERROR) {
          settle({ status: "error", error: String(status?.error || status?.reason || "Render artifact is unavailable.") });
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
        // needs-build -> we own the build. The POST is one long-lived request that resolves
        // only when the build finishes, so its position comes from the concurrent status
        // poll below.
        attached = false;
        showGenerating(status);
        pollTimer = window.setTimeout(pollProgress, ARTIFACT_PROGRESS_FIRST_POLL_MS);
        const result = await requestArtifact(activeRef, { signal: controller.signal });
        stopPolling();
        if (!isCurrent()) {
          return;
        }
        if (result?.ok && result.state === "generating") {
          // The server handed us off to a peer that took the lock first. Attach to it
          // rather than reporting a failure.
          attached = true;
          showGenerating(result);
          pollTimer = window.setTimeout(pollProgress, ARTIFACT_PROGRESS_FIRST_POLL_MS);
          return;
        }
        settle(result?.ok && result.state === "ready"
          ? READY
          : { status: "error", error: String(result?.error || "Failed to generate the render artifact.") });
      } catch (error) {
        stopPolling();
        if (isCurrent() && !isAbortError(error) && !controller.signal.aborted) {
          settle({ status: "error", error: error instanceof Error ? error.message : String(error) });
        }
      }
    }

    resolve();

    return () => {
      stopPolling();
      controller.abort();
    };
  }, [activeRef, key]);

  // Optimistic-ready until this exact key has settled, so a fresh selection renders without a flash.
  return state.key === key
    ? { status: state.status, error: state.error, progress: state.progress }
    : READY;
}

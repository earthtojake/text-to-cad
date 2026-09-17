/**
 * The browser half of the backend's development auto-reload.
 *
 * A viewer served by an installed wheel never watches its own code, reports
 * `autoReload: false`, and none of this runs: the poll below starts only when
 * the server says it restarts itself, which it says only when cadgen is a
 * source checkout (see `cadgen/viewer/reload.py`).
 *
 * When it IS a checkout, the backend re-executes itself on the SAME port the
 * moment its Python changes and the work in flight is done. That is invisible
 * from here except for two things: `/__cad/server` stops answering for a
 * fraction of a second, and when it answers again its `identityToken` is a new
 * value. Either one means "the server is no longer the process this page
 * loaded against", and the page reloads — which is also what picks up a
 * rebuilt client, since the page re-fetches everything.
 *
 * The decision is a pure function so the whole behaviour is testable without a
 * browser: `nextAutoReloadState` takes the state and one poll result and says
 * what to do and when to ask again.
 */

/** Steady-state poll while the server is the one this page loaded against. */
export const VIEWER_WATCH_INTERVAL_MS = 2000;
/** Faster poll while the server is mid-restart. */
export const VIEWER_RELOADING_POLL_MS = 400;
/**
 * How long the "Reloading" status may stand before the page stops claiming a
 * restart is under way. The watch continues at the slow interval — a restart
 * that eventually lands still reloads the page — but the badge stops asserting
 * something that is no longer happening, and ordinary request failures surface
 * through the alerts they always did.
 */
export const VIEWER_RELOAD_TIMEOUT_MS = 30000;

export const AUTO_RELOAD_PHASE = Object.freeze({
  WATCHING: "watching",
  RELOADING: "reloading",
});

/**
 * @param {{phase: string, since: number}} state
 * @param {{ok: boolean, identityToken?: string}} poll
 * @param {{baseline: string, now: number}} context
 * @returns {{phase: string, since: number, reload: boolean, delayMs: number}}
 */
export function nextAutoReloadState(state, poll, { baseline, now }) {
  const phase = state?.phase === AUTO_RELOAD_PHASE.RELOADING
    ? AUTO_RELOAD_PHASE.RELOADING
    : AUTO_RELOAD_PHASE.WATCHING;
  // Number.isFinite, not `||`: `since` is a timestamp and 0 is a real one.
  const since = Number.isFinite(state?.since) ? Number(state.since) : now;
  const reloading = { phase: AUTO_RELOAD_PHASE.RELOADING, reload: false, delayMs: VIEWER_RELOADING_POLL_MS };
  const watching = { phase: AUTO_RELOAD_PHASE.WATCHING, since: now, reload: false, delayMs: VIEWER_WATCH_INTERVAL_MS };

  if (!poll?.ok) {
    // The port is closed for the moment it takes to exec and re-bind. This is
    // the normal first sign of a restart, not a failure.
    return { ...reloading, since: phase === AUTO_RELOAD_PHASE.RELOADING ? since : now };
  }

  const answered = String(poll.identityToken || "");
  if (answered && answered !== String(baseline || "")) {
    // A different process on the same port: reload, whatever the phase was.
    // The token is start-time identity, so this cannot be a false positive.
    return { ...reloading, since, reload: true };
  }

  if (phase === AUTO_RELOAD_PHASE.RELOADING) {
    // It came back as the SAME process — a transient fetch failure, not a
    // restart. Drop the claim and go back to watching.
    return watching;
  }
  return { phase, since, reload: false, delayMs: VIEWER_WATCH_INTERVAL_MS };
}

/**
 * True while the page should say a restart is under way. Past the bound the
 * watch continues but stops asserting it.
 */
export function autoReloadIsPending(state, now, timeoutMs = VIEWER_RELOAD_TIMEOUT_MS) {
  if (state?.phase !== AUTO_RELOAD_PHASE.RELOADING) {
    return false;
  }
  const since = Number.isFinite(state.since) ? Number(state.since) : now;
  return now - since < timeoutMs;
}

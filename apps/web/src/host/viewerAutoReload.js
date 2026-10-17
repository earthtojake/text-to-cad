/**
 * The browser half of "the server is no longer the one this page loaded from".
 *
 * Every viewer server says who it is: `/__cad/server`'s `identityToken`, its
 * cadgen version and a digest of the page it serves. Once that answer is not the
 * one the page loaded against, the page reloads, which picks up the client that
 * server serves -- and with it whatever its store speaks (a mesh format, a
 * route). A page from before an upgrade cannot read the meshes of the server
 * after it. Two kinds of server change under a page:
 *
 * - A source checkout's backend re-executes itself on the SAME port the moment
 *   its Python changes and the work in flight is done (`autoReload: true`, see
 *   `cadgen/viewer/reload.py`): `/__cad/server` stops answering for a fraction of
 *   a second, and answers again with a new token. It is asked every 2 s, and
 *   every 0.4 s mid-restart.
 * - An installed one is replaced by another version on its port, under a tab
 *   left open across the upgrade. It is asked every 5 s (and, by the hook, the
 *   moment the tab comes back into view): a token from another install reloads
 *   the page, and the same install restarting does not.
 *
 * The decision is a pure function so the whole behaviour is testable without a
 * browser: `nextAutoReloadState` takes the state, one poll result and the
 * cadence, and says what to do and when to ask again.
 */

/** Steady-state poll while the server is the one this page loaded against. */
export const VIEWER_WATCH_INTERVAL_MS = 2000;
/** Faster poll while the server is mid-restart. */
export const VIEWER_RELOADING_POLL_MS = 400;
/** An installed server's poll, answered or not: it changes only when another version replaces it. */
export const VIEWER_INSTALL_POLL_MS = 5000;

export const AUTO_RELOAD_PHASE = Object.freeze({
  WATCHING: "watching",
  RELOADING: "reloading",
});

/**
 * @param {{phase: string, since: number}} state
 * @param {{ok: boolean, identityToken?: string}} poll
 * @param {{baseline: string, now: number, watchMs?: number, reloadingMs?: number}} context  The cadence:
 *   a development backend's by default (`VIEWER_WATCH_INTERVAL_MS`, `VIEWER_RELOADING_POLL_MS`).
 * @returns {{phase: string, since: number, reload: boolean, delayMs: number}}
 */
export function nextAutoReloadState(state, poll, {
  baseline, now, watchMs = VIEWER_WATCH_INTERVAL_MS, reloadingMs = VIEWER_RELOADING_POLL_MS
}) {
  const phase = state?.phase === AUTO_RELOAD_PHASE.RELOADING
    ? AUTO_RELOAD_PHASE.RELOADING
    : AUTO_RELOAD_PHASE.WATCHING;
  // Number.isFinite, not `||`: `since` is a timestamp and 0 is a real one.
  const since = Number.isFinite(state?.since) ? Number(state.since) : now;
  const reloading = { phase: AUTO_RELOAD_PHASE.RELOADING, reload: false, delayMs: reloadingMs };
  const watching = { phase: AUTO_RELOAD_PHASE.WATCHING, since: now, reload: false, delayMs: watchMs };

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
  return { phase, since, reload: false, delayMs: watchMs };
}

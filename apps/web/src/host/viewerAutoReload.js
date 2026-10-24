/**
 * The browser half of "the server is no longer the one this page loaded from".
 *
 * Every viewer server says who it is: `/__cad/server`'s `identityToken`, its
 * cadgen version and a digest of the page it serves. Once that answer is not the
 * one the page loaded against, the page reloads, which picks up the client that
 * server serves -- and with it whatever its store speaks (a mesh format, a
 * route). A page from before an upgrade cannot read the meshes of the server
 * after it. The engine never re-executes its Python process under a page.
 * The page checks its backend identity every five seconds and on window focus.
 *
 * The decision is a pure function so the whole behaviour is testable without a
 * browser: `nextAutoReloadState` takes the state, one poll result and the
 * cadence, and says what to do and when to ask again.
 *
 * Only a dev server is followed to another identity (`follow`). A page the engine
 * serves never is: the engine's token is new with every engine, so the page's own
 * credential is refused by any later engine on its port, and an answer from a new
 * identity there is a process the page cannot authenticate -- whatever binds the
 * port once the engine is gone. The page stops asking and says its engine is gone
 * (`foreign`), and never loads that process into the tab.
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
  FOREIGN: "foreign",
});

/**
 * @param {{phase: string, since: number}} state
 * @param {{ok: boolean, identityToken?: string}} poll
 * @param {{baseline: string, now: number, watchMs?: number, reloadingMs?: number, follow?: boolean}} context  The cadence:
 *   the default cadence (`VIEWER_WATCH_INTERVAL_MS`, `VIEWER_RELOADING_POLL_MS`); `follow`, whether a
 *   new identity is reloaded into (a dev server's) or refused (`FOREIGN`, every engine-served page's).
 * @returns {{phase: string, since: number, reload: boolean, delayMs: number}}
 */
export function nextAutoReloadState(state, poll, {
  baseline, now, watchMs = VIEWER_WATCH_INTERVAL_MS, reloadingMs = VIEWER_RELOADING_POLL_MS, follow = false
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
    // A different process on the same port. A dev server's restart is followed; an engine-served
    // page is not reloaded into a process its credential cannot authenticate: it stops asking.
    if (!follow) {
      return { phase: AUTO_RELOAD_PHASE.FOREIGN, since, reload: false, delayMs: 0 };
    }
    return { ...reloading, since, reload: true };
  }

  if (phase === AUTO_RELOAD_PHASE.RELOADING) {
    // It came back as the SAME process — a transient fetch failure, not a
    // restart. Drop the claim and go back to watching.
    return watching;
  }
  return { phase, since, reload: false, delayMs: watchMs };
}

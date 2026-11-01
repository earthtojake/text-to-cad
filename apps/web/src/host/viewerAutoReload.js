/**
 * The browser half of "the server is no longer the one this page loaded from".
 *
 * An update is followed: the engine that answers with another release (`/api/v1/server`'s `release`)
 * and admits this page's credential is the device's engine of the next release, and the page reloads
 * into it (`reload`, deferred while the page has something unsaved: `@text-to-cad/ui/update`).
 *
 * Every viewer server says who it is: `/api/v1/server`'s `identityToken`, its
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
 * serves is not reloaded here: it stops asking and says its engine is gone
 * (`foreign`). It then asks for its engine as any page that lost one does
 * (`useEngineReconnect`), which reloads it only once an engine that holds its
 * token answers -- the installation's own, whose token outlives its restarts --
 * and never loads another process on its port into the tab.
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
 * @param {{ok: boolean, identityToken?: string, release?: string}} poll
 * @param {{baseline: string, release?: string, now: number, watchMs?: number, reloadingMs?: number, follow?: boolean}} context
 *   The cadence: the default cadence (`VIEWER_WATCH_INTERVAL_MS`, `VIEWER_RELOADING_POLL_MS`); `follow`,
 *   whether a new identity is reloaded into (a dev server's) or refused (`FOREIGN`, every engine-served
 *   page's); `release`, the release the page loaded from, another of which -- an update -- is reloaded into.
 * @returns {{phase: string, since: number, reload: boolean, delayMs: number}}
 */
export function nextAutoReloadState(state, poll, {
  baseline, release = "", now, watchMs = VIEWER_WATCH_INTERVAL_MS, reloadingMs = VIEWER_RELOADING_POLL_MS, follow = false
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
    // A different process on the same port. A dev server's restart is followed, and so is an update:
    // the engine of another release that admitted this page's credential. Any other engine-served page
    // is not reloaded into a process it cannot tell apart: it stops asking.
    const updated = Boolean(release && poll.release && String(poll.release) !== String(release));
    if (!follow && !updated) {
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

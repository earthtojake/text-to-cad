/**
 * A page left open across a new build of the CAD Viewer it was served (a release installed, or a checkout's
 * bundle rebuilt, under a server that keeps running): the page still names the old build's chunks, by their
 * hashed names, and the server no longer has them. The first view that needs one it has not loaded yet -- a
 * board's 3D view, a renderer for another kind of file -- fails to import it, and the view's boundary said
 * "Could not display that file" until the person reloaded.
 *
 * Vite says so on the window (`vite:preloadError`, for every dynamic import of the build), and the remedy is
 * the page of the build the server has now: a reload, once nothing typed would be lost (`reloadWhenClean`).
 * The tab's views are its store's (`tab-store`, sessionStorage), so the file comes back as it was left, the
 * board in 3D included. Once a reload was made for it within `STALE_BUILD_WINDOW_MS`, another failure is a
 * chunk the new build lacks too: the page is not reloaded again, and the view says it could not display.
 */
import { reloadWhenClean } from "./reloadWhenClean.js";

export const STALE_BUILD_KEY = "text-to-cad:stale-build-reload";
export const STALE_BUILD_WINDOW_MS = 30000;
/** How long the page lets the view it lost settle first: it writes what it holds (`tab-store`), so the reload finds it. */
export const STALE_BUILD_SETTLE_MS = 300;

/**
 * @param {{ target?: Pick<Window, "addEventListener" | "removeEventListener">, storage?: Pick<Storage, "getItem" | "setItem">,
 *   reload?: () => void, now?: () => number, whenClean?: (reload: () => void) => () => void,
 *   settle?: (callback: () => void) => () => void }} [options]  `settle`: waits `STALE_BUILD_SETTLE_MS`.
 * @returns {() => void} Stops listening (and cancels a reload not made yet).
 */
export function reloadOnStaleBuild({
  target = window, storage = window.sessionStorage, reload = () => window.location.reload(), now = () => Date.now(), whenClean = reloadWhenClean,
  settle = callback => { const timer = window.setTimeout(callback, STALE_BUILD_SETTLE_MS); return () => window.clearTimeout(timer); }
} = {}) {
  let cancel = null;
  const onPreloadError = () => {
    if (cancel) return;
    const last = Number(storage.getItem(STALE_BUILD_KEY));
    if (Number.isFinite(last) && last > 0 && now() - last < STALE_BUILD_WINDOW_MS) return;
    let cancelReload = null;
    const cancelSettle = settle(() => { cancelReload = whenClean(() => { storage.setItem(STALE_BUILD_KEY, String(now())); reload(); }); });
    cancel = () => { cancelSettle(); cancelReload?.(); };
  };
  target.addEventListener("vite:preloadError", onPreloadError);
  return () => { target.removeEventListener("vite:preloadError", onPreloadError); cancel?.(); };
}

/**
 * The page's address keeps a working link (`?token=<expires>.<mac>`), so the address copied into
 * another browser on this machine opens the same page there. The server leaves the link a page was
 * opened with in its address; a page loaded without one (a reload the session cookie admitted) or
 * with one about to expire is given a fresh one (`GET /api/v1/local/link`), written in place
 * (`history.replaceState`: the same path, the rest of the query and the hash kept) -- when the page
 * loads, and again whenever it is shown or focused.
 */

/** A link this close to its expiry, or past it, is replaced. */
export const LINK_REFRESH_SECONDS = 12 * 60 * 60;

/** Whether the address `search` needs a fresh link at `now` (Unix seconds). */
export function addressNeedsLink(search, now) {
  const link = new URLSearchParams(search).get("token") || "";
  const expires = Number(link.split(".")[0]);
  return !link.includes(".") || !Number.isFinite(expires) || expires - now < LINK_REFRESH_SECONDS;
}

/**
 * Keep `page`'s address holding a fresh link, asked of `fetchLink` (`() => Promise<{ link }>`):
 * answers the function that stops it. A failed ask leaves the address as it is.
 */
export function keepAddressLink({ fetchLink, page = globalThis.window, now = () => Date.now() / 1000 }) {
  let asking = false;
  let stopped = false;
  const refresh = async () => {
    if (stopped || asking || !addressNeedsLink(page.location.search, now())) return;
    asking = true;
    try {
      const { link } = await fetchLink();
      if (stopped || !link) return;
      // Written over the address as it is now: the page may have moved while it asked.
      const query = new URLSearchParams(page.location.search);
      query.set("token", String(link));
      page.history.replaceState(page.history.state, "", `${page.location.pathname}?${query}${page.location.hash}`);
    } catch {
      // The engine did not answer: the address keeps what it holds, and the next look asks again.
    } finally {
      asking = false;
    }
  };
  const onVisible = () => { if (page.document.visibilityState !== "hidden") void refresh(); };
  page.document.addEventListener("visibilitychange", onVisible);
  page.addEventListener("focus", onVisible);
  const started = refresh();
  const stop = () => {
    stopped = true;
    page.document.removeEventListener("visibilitychange", onVisible);
    page.removeEventListener("focus", onVisible);
  };
  stop.started = started;
  return stop;
}

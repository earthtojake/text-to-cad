/**
 * Where the page goes once the update it followed ended with its server staying (`useUpdate`'s `onMoved`: the
 * update's state `moved`) -- another channel is still on that server's version, or work is in flight there, so the
 * new release's server serves pages at another address: the same document there (the page's path and hash), with
 * the link the old server signed for the new one's page token (`update.link`). Null where the update names no
 * address it can go to (the new server did not answer): the page stays, and says the update is done.
 *
 * @param {{ address?: string | null, link?: string | null } | null | undefined} update
 * @param {{ pathname?: string, hash?: string }} location
 * @returns {string | null}
 */
export function movedPage(update, location) {
  if (!update || typeof update.address !== "string" || typeof update.link !== "string" || !update.link) return null;
  let url;
  try {
    url = new URL(location.pathname || "/", update.address);
  } catch {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  url.search = "";
  url.searchParams.set("token", update.link);
  url.hash = location.hash || "";
  return url.toString();
}

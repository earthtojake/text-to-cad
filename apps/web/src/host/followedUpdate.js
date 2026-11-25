/**
 * The tab's note that its page followed an update through the server's restart (`useUpdate`'s phase
 * `restarting`, or the server gone while the release installed), and the release it followed it from.
 * The page reloads into the server that comes back, and the page loaded there follows the update still
 * (`useUpdate`'s `followed`): a spinner while the update's end is written, then its failure, or, on
 * another release, that it is updated, once. Kept in the tab's own session storage, which a private
 * window or blocked site data may refuse: then the page loaded follows nothing, and says the update's
 * failure from the server's record all the same.
 */
const KEY = "text-to-cad.update.followed";

/** @param {Storage | undefined} storage */
function tabStorage(storage) {
  return storage ?? window.sessionStorage;
}

/** The note made: this page follows an update from `release` through the server's restart. @param {string} release @param {Storage} [storage] */
export function noteFollowedUpdate(release, storage) {
  try {
    tabStorage(storage).setItem(KEY, String(release || "?"));
  } catch {
    // no storage for this tab: the page loaded after the restart follows nothing
  }
}

/**
 * The release the page this one reloaded from followed an update from, or null. Only read: React renders
 * twice in strict mode, so the note is forgotten apart (`forgetFollowedUpdate`).
 * @param {Storage} [storage]
 * @returns {string | null}
 */
export function followedUpdate(storage) {
  try {
    return tabStorage(storage).getItem(KEY) || null;
  } catch {
    return null;
  }
}

/** The note gone: taken by the page loaded, or the update ended on the page that made it. @param {Storage} [storage] */
export function forgetFollowedUpdate(storage) {
  try {
    tabStorage(storage).removeItem(KEY);
  } catch {
    // nothing kept, nothing to forget
  }
}

/**
 * The tab's note that its page followed an update through the engine's restart (`useUpdate`'s phase
 * `restarting`). The page reloads into the engine that comes back (`useEngineReconnect`), and the page
 * loaded there follows the update still (`useUpdate`'s `followed`): a switch that failed and went back
 * is said there, once. Kept in the tab's own session storage, which a private window or blocked site
 * data may refuse: then the page loaded says nothing, as before.
 */
const KEY = "text-to-cad.update.followed";

/** @param {Storage | undefined} storage */
function tabStorage(storage) {
  return storage ?? window.sessionStorage;
}

/** The note made: this page follows an update through the engine's restart. @param {Storage} [storage] */
export function noteFollowedUpdate(storage) {
  try {
    tabStorage(storage).setItem(KEY, "1");
  } catch {
    // no storage for this tab: the page loaded after the restart says nothing
  }
}

/**
 * Whether the page this one reloaded from followed an update through the engine's restart. Only read:
 * React renders twice in strict mode, so the note is forgotten apart (`forgetFollowedUpdate`).
 * @param {Storage} [storage]
 * @returns {boolean}
 */
export function followedUpdate(storage) {
  try {
    return tabStorage(storage).getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/** The note gone, once the page loaded has taken it. @param {Storage} [storage] */
export function forgetFollowedUpdate(storage) {
  try {
    tabStorage(storage).removeItem(KEY);
  } catch {
    // nothing kept, nothing to forget
  }
}

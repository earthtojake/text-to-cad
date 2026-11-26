/**
 * The project's notices the person dismissed in this browser (`useUpdate`'s `notices`, `@cad/ui/update`): their ids,
 * kept in the browser's local storage, so a notice dismissed on one page stays dismissed on every page of this browser.
 * A browser that keeps nothing (a private window, blocked site data, no storage) reads none and keeps none: the notice
 * is shown again on the next page, and nothing fails.
 */
const KEY = "text-to-cad.notices.dismissed";

/** @param {Storage | undefined} storage */
function browserStorage(storage) {
  return storage ?? window.localStorage;
}

/** The ids dismissed in this browser. @param {Storage} [storage] @returns {string[]} */
export function dismissedNotices(storage) {
  try {
    const kept = JSON.parse(browserStorage(storage).getItem(KEY) || "[]");
    return Array.isArray(kept) ? kept.filter(id => typeof id === "string") : [];
  } catch {
    return [];
  }
}

/** A notice dismissed, kept with the others. @param {string} id @param {Storage} [storage] */
export function dismissNotice(id, storage) {
  try {
    const kept = dismissedNotices(storage);
    if (!kept.includes(id)) browserStorage(storage).setItem(KEY, JSON.stringify([...kept, id]));
  } catch {
    // nothing kept: shown again on the next page
  }
}

/** This browser's dismissals, as `useUpdate` takes them. */
export const browserNoticeDismissals = { dismissed: () => dismissedNotices(), dismiss: id => dismissNotice(id) };

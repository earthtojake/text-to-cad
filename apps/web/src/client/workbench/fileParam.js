/**
 * The document a page shows, in its URL's path: `/<id>` -- a document's id (`cad.engine.ids`): a
 * model's, or a file's, which the server derives from its canonical path and registers when a
 * launcher or the page opens it -- and `/` for the home. A path that names no id is the home.
 */
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** The id the URL's path names, or null: the home. */
export function readDocumentId(pathname = window.location.pathname) {
  const value = String(pathname || "").replace(/^\/+|\/+$/g, "");
  return ID.test(value) ? value : null;
}

/** The file a developer's build opens by default (`VIEWER_DEFAULT_FILE`, an absolute path), or null. */
export function readDefaultFileParam() {
  return String(import.meta.env?.VIEWER_DEFAULT_FILE ?? "").trim() || null;
}

/**
 * Name the document `id` in the URL (`""` or null is none: the home, `/`), as a new history entry or
 * in place of this one. The query the page carries is kept.
 */
export function writeDocumentId(id, { history = "push" } = {}) {
  const rest = new URLSearchParams(window.location.search).toString();
  const next = `/${id || ""}${rest ? `?${rest}` : ""}${window.location.hash}`;
  if (next === `${window.location.pathname}${window.location.search}${window.location.hash}`) return;
  if (history === "push") window.history.pushState({}, "", next);
  else window.history.replaceState({}, "", next);
}

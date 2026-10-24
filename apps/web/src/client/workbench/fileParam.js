/**
 * The document a page shows, in its URL's path: `/<id>` -- a document's id (`cadgen.engine.ids`): a
 * model's, or a file's, which the server derives from its canonical path and registers when a
 * launcher or the page opens it -- and `/` for the home. There is no other form: a path that names
 * no id (an old `/s/<session>/`, or `/` with `?file=`) is the home, and the page names it so.
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
 * in place of this one. Any other query the page carries is kept; a document named by query is not.
 */
export function writeDocumentId(id, { history = "push" } = {}) {
  const params = new URLSearchParams(window.location.search);
  params.delete("file");
  params.delete("doc");
  params.delete("id");
  const rest = params.toString();
  const next = `/${id || ""}${rest ? `?${rest}` : ""}${window.location.hash}`;
  if (next === `${window.location.pathname}${window.location.search}${window.location.hash}`) return;
  if (history === "push") window.history.pushState({}, "", next);
  else window.history.replaceState({}, "", next);
}

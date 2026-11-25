/**
 * What a page shows, in its address. A document, in the path: `/<id>` -- a document's id (`cad.engine.ids`), its
 * file's, which the server derives from its canonical path and knows once a launcher, the page or a folder's listing
 * has named it. The home, at `/`, at a place on it its query names: `/` Recents, `/?view=pinned`, `/?view=standalone`,
 * `/?project=<id>` a project's page at its top, `&path=<folder>` at a folder of it (below its root, `/`-separated). A
 * path that names no id is the home, and a query that names no place is Recents.
 */
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
/** The places of the home the query's `view` names; Recents is the home with none. */
const VIEWS = new Set(["pinned", "standalone"]);
/** The query's parameters that name a place: a document's page carries none of them. */
const PLACE_PARAMETERS = ["view", "project", "path"];

/** The id the URL's path names, or null: the home. */
export function readDocumentId(pathname = window.location.pathname) {
  const value = String(pathname || "").replace(/^\/+|\/+$/g, "");
  return ID.test(value) ? value : null;
}

/**
 * @typedef {{ view: "recents" | "pinned" | "standalone" } | { view: "project", project: string, path?: string }} HomePlace
 *   A place on the home (`@cad/ui/host`'s `HomeLocation`).
 */

/**
 * The place on the home the URL's query names: a project's page (at the folder `path` names, its top with none), Pinned
 * or Standalone; Recents for anything else.
 * @param {string} [search]
 * @returns {HomePlace}
 */
export function readHomePlace(search = window.location.search) {
  const query = new URLSearchParams(search);
  const project = query.get("project");
  const path = (query.get("path") ?? "").replace(/^\/+|\/+$/g, "");
  if (project) return path ? { view: "project", project, path } : { view: "project", project };
  const view = query.get("view");
  return { view: view === "pinned" || view === "standalone" ? view : "recents" };
}

/** The file a developer's build opens by default (`VIEWER_DEFAULT_FILE`, an absolute path), or null. */
export function readDefaultFileParam() {
  return String(import.meta.env?.VIEWER_DEFAULT_FILE ?? "").trim() || null;
}

/**
 * The address, in this origin, of the document `id`'s page, or with none of the home at `place` (Recents with none):
 * its path, the place's parameter, then whatever else the page's address carries (`search`: its link, so the address
 * opens in another browser too) and its hash. Never another place's parameter.
 * @param {{ id?: string, place?: HomePlace | null }} [target]
 * @param {{ search?: string, hash?: string }} [carried]
 */
export function pageAddress({ id = "", place = null } = {}, { search = window.location.search, hash = window.location.hash } = {}) {
  const query = new URLSearchParams();
  if (!id && place?.view === "project" && place.project) {
    query.set("project", place.project);
    if (place.path) query.set("path", place.path);
  } else if (!id && place && VIEWS.has(place.view)) query.set("view", place.view);
  for (const [name, value] of new URLSearchParams(search)) if (!PLACE_PARAMETERS.includes(name)) query.append(name, value);
  const rest = query.toString();
  return `/${id || ""}${rest ? `?${rest}` : ""}${hash}`;
}

/**
 * Name the document `id` in the URL (`""` or null is none: the home, `/`, at `place`), as a new history entry or
 * in place of this one. The rest of the query the page carries is kept.
 * @param {string | null} id
 * @param {{ history?: "push" | "replace", place?: HomePlace | null }} [options]
 */
export function writeDocumentId(id, { history = "push", place = null } = {}) {
  const next = pageAddress({ id: id || "", place });
  if (next === `${window.location.pathname}${window.location.search}${window.location.hash}`) return;
  if (history === "push") window.history.pushState({}, "", next);
  else window.history.replaceState({}, "", next);
}

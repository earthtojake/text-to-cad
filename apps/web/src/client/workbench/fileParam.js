/**
 * The file a page shows, in its URL: `?file=<absolute path>`, and no `?file=` for the home. One
 * CAD Viewer serves every file on the machine, so a link names its file in full. A path that is not
 * absolute is a developer's: it resolves against the folder this viewer started in (the server's
 * `start`), and the page names the file in full from then on.
 */
const PARAM = "file";

const isAbsolute = (path) => /^(?:\/|[A-Za-z]:\/)/.test(path);

/** `?file=` as the URL has it, or null. */
export function readFileParam(search = window.location.search) {
  const value = new URLSearchParams(search).get(PARAM);
  return value && value.trim() ? value.trim() : null;
}

/** The file a developer's build opens by default (`VIEWER_DEFAULT_FILE`), or null. */
export function readDefaultFileParam() {
  return String(import.meta.env?.VIEWER_DEFAULT_FILE ?? "").trim() || null;
}

/** `value` as an absolute path, `/`-separated: as it is, or resolved against `start`. */
export function resolveFileParam(value, start = "") {
  const raw = String(value || "").trim().replace(/\\/g, "/");
  if (!raw) return "";
  const joined = isAbsolute(raw) ? raw : `${String(start).replace(/\\/g, "/").replace(/\/+$/, "")}/${raw}`;
  const drive = /^[A-Za-z]:/.test(joined) ? joined.slice(0, 2) : "";
  const parts = [];
  for (const part of joined.slice(drive.length).split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") parts.pop();
    else parts.push(part);
  }
  return `${drive}/${parts.join("/")}`;
}

// A path stays readable in the URL: only what a query cannot carry is escaped.
const encodePath = (path) => encodeURIComponent(path).replace(/%2F/gi, "/").replace(/%3A/gi, ":");

/** Name `path` in the URL (`""` is none: the home), as a new history entry or in place of this one. */
export function writeFileParam(path, { history = "push" } = {}) {
  const params = new URLSearchParams(window.location.search);
  params.delete(PARAM);
  const rest = params.toString();
  const search = [path ? `${PARAM}=${encodePath(path)}` : "", rest].filter(Boolean).join("&");
  const next = `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`;
  if (next === `${window.location.pathname}${window.location.search}${window.location.hash}`) return;
  if (history === "push") window.history.pushState({}, "", next);
  else window.history.replaceState({}, "", next);
}

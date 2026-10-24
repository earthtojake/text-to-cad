// Resolving a file's relative reference (a GLB's texture or buffer) against the URL the file
// came from.
//
// The Viewer serves a file as `/__cad/asset?file=<absolute path>`, so the file the reference is
// relative to lives in the QUERY, not the path. Resolving `textures/skin.png` against that URL
// the ordinary way gives `/__cad/textures/skin.png`, which the backend does not serve. The
// reference has to be resolved against the `file` parameter and written back into a fresh
// `/__cad/asset` URL. (A robot's link meshes are named by the URLs cadgen minted for them and
// never resolved here.)

function normalizeAbsoluteUrl(url) {
  if (url instanceof URL) {
    return url.toString();
  }
  return new URL(String(url || "/"), globalThis.window?.location?.href || "http://localhost/").toString();
}

// Collapse `.` and `..` by hand: these are filesystem refs carried in a query parameter, not
// URL path segments, so the URL parser never sees them.
function normalizeFileRefSegments(value) {
  const rawValue = String(value || "").replace(/\\/g, "/");
  const absolute = rawValue.startsWith("/");
  const parts = [];
  for (const part of rawValue.split("/")) {
    if (!part || part === ".") {
      continue;
    }
    if (part === "..") {
      if (parts.length && parts[parts.length - 1] !== "..") {
        parts.pop();
      } else if (!absolute) {
        parts.push(part);
      }
      continue;
    }
    parts.push(part);
  }
  return `${absolute ? "/" : ""}${parts.join("/")}`;
}

function dirnameFileRef(value) {
  const normalized = String(value || "").replace(/\\/g, "/");
  const index = normalized.lastIndexOf("/");
  return index >= 0 ? normalized.slice(0, index + 1) : "";
}

function decoded(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

// `package://NAME/rest` names a file of ROS package NAME, and a package is a folder named for
// it: the nearest folder of that name above the description is the package root. That is how a
// description inside its own package (`NAME/urdf/robot.urdf` beside `NAME/meshes/`) finds its
// meshes. "" when no folder above it has that name.
function packageFileRef(sourceFileRef, reference) {
  const match = /^package:\/\/([^/]+)\/(.+)$/i.exec(reference);
  if (!match) {
    return "";
  }
  const folders = dirnameFileRef(String(sourceFileRef || "").replace(/\\/g, "/")).split("/");
  const at = folders.lastIndexOf(decoded(match[1]));
  if (at < 0) {
    return "";
  }
  const root = normalizeFileRefSegments(folders.slice(0, at + 1).join("/"));
  const resolved = normalizeFileRefSegments(`${root}/${decoded(match[2])}`);
  // `..` in the rest may not climb out of the package.
  return resolved.startsWith(`${root}/`) ? resolved : "";
}

// `file:///abs/path` is that absolute path; `file:///C:/abs/path` is `C:/abs/path`.
function fileUriFileRef(reference) {
  const match = /^file:\/\/(?:localhost)?(\/[^?#]*)$/i.exec(reference);
  if (!match) {
    return "";
  }
  const path = decoded(match[1]);
  return normalizeFileRefSegments(/^\/[a-z]:\//i.test(path) ? path.slice(1) : path);
}

export function resolveLocalAssetFileRef(sourceFileRef, reference) {
  const rawReference = String(reference || "").trim();
  if (/^package:\/\//i.test(rawReference)) {
    return packageFileRef(sourceFileRef, rawReference);
  }
  if (/^file:/i.test(rawReference)) {
    return fileUriFileRef(rawReference);
  }
  if (!rawReference || /^[a-z][a-z0-9+.-]*:/i.test(rawReference)) {
    return "";
  }
  if (rawReference.startsWith("/")) {
    return normalizeFileRefSegments(rawReference);
  }
  return normalizeFileRefSegments(`${dirnameFileRef(sourceFileRef)}${rawReference}`);
}

/** The `/__cad/asset` URL for a file named relative to one served from that route, or "" when
 * the source did not come from it (a plain static host, a test fixture). */
export function resolveCadAssetMeshUrl(reference, sourceUrl) {
  const source = new URL(normalizeAbsoluteUrl(sourceUrl));
  if (source.pathname !== "/__cad/asset") {
    return "";
  }
  const sourceFileRef = source.searchParams.get("file") || "";
  const meshFileRef = resolveLocalAssetFileRef(sourceFileRef, reference);
  const rawReference = String(reference || "").trim();
  if (!meshFileRef && /^package:\/\//i.test(rawReference)) {
    // Resolved against the server's root instead, the request fetched the page itself, and the
    // robot failed as a corrupt mesh ("Invalid typed array length"), naming nothing.
    const name = decoded(rawReference.slice("package://".length).split("/")[0]);
    throw new Error(`Mesh ${rawReference}: no folder named “${name}” holds ${sourceFileRef}, so its package `
      + "cannot be found. Keep the description inside its package folder, or name the mesh by a path relative to the description.");
  }
  if (!meshFileRef) {
    return "";
  }
  const resolved = new URL("/__cad/asset", source);
  resolved.searchParams.set("file", meshFileRef);
  // Carry the cache-busting `v` (and anything else) so a mesh is versioned with its robot.
  for (const [key, value] of source.searchParams.entries()) {
    if (key !== "file") {
      resolved.searchParams.set(key, value);
    }
  }
  return /^[a-z][a-z0-9+.-]*:\/\//i.test(String(sourceUrl)) ? resolved.href : `${resolved.pathname}${resolved.search}`;
}

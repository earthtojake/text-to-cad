// Resolving a robot's link-mesh reference against the URL its DESCRIPTION came from.
//
// The Viewer serves a description as `/__cad/asset?file=<absolute path>`, so the file the
// mesh is relative to lives in the QUERY, not the path. Resolving `meshes/wedge.stl`
// against that URL the ordinary way gives `/__cad/meshes/wedge.stl`, which the backend does
// not serve — the mesh 404s and the whole model fails to load. The reference has to be
// resolved against the `file` parameter and written back into a fresh `/__cad/asset` URL.
//
// This lived privately in the URDF parser, so URDF link meshes loaded and SDF ones did not:
// every SDF that names a mesh failed in the Viewer with "Couldn't load the model". One copy,
// both parsers.

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

export function resolveLocalAssetFileRef(sourceFileRef, reference) {
  const rawReference = String(reference || "").trim();
  if (!rawReference || /^[a-z][a-z0-9+.-]*:/i.test(rawReference)) {
    return "";
  }
  if (rawReference.startsWith("/")) {
    return normalizeFileRefSegments(rawReference);
  }
  return normalizeFileRefSegments(`${dirnameFileRef(sourceFileRef)}${rawReference}`);
}

/** The `/__cad/asset` URL for a mesh named relative to a description served from one, or ""
 * when the description did not come from that route (a plain static host, a test fixture). */
export function resolveCadAssetMeshUrl(reference, sourceUrl) {
  const source = new URL(normalizeAbsoluteUrl(sourceUrl));
  if (source.pathname !== "/__cad/asset") {
    return "";
  }
  const sourceFileRef = source.searchParams.get("file") || "";
  const meshFileRef = resolveLocalAssetFileRef(sourceFileRef, reference);
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

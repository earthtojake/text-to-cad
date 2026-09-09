// THE origin of the CAD Viewer backend this surface talks to.
//
// The standalone app is served BY that backend, so every call it makes is a
// root-relative `/__cad/...` or `/__tess_cache/...` URL and the origin is the
// empty string — same origin, exactly what shipped before this module existed.
// A host that embeds <CadFileView> (the desktop app, which spawns
// `cadgen viewer --api-only` per project root) is served from somewhere else
// entirely, so it hands the surface an absolute origin
// ("http://127.0.0.1:3250") and every backend URL is built against it.
//
// One value, one join. Nothing downstream concatenates an origin by hand:
// worker fetches included, a URL is either produced here or produced by
// resolving against a URL that was.

const ABSOLUTE_URL_PATTERN = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//u;

// The entry fields that carry a backend URL. A catalog entry is data from the
// server, so the rebasing below is a rewrite of THESE keys and nothing else —
// an unknown field is left alone rather than guessed at.
const ENTRY_URL_KEYS = Object.freeze(["url", "poseUrl", "renderModuleUrl"]);

export function normalizeViewerOrigin(value) {
  const text = String(value ?? "").trim();
  if (!text) {
    return "";
  }
  return text.replace(/\/+$/u, "");
}

export function isAbsoluteViewerUrl(value) {
  return ABSOLUTE_URL_PATTERN.test(String(value ?? "").trim());
}

// Join a root-relative backend path onto the origin. An empty origin returns
// the path untouched (the standalone app's every URL), and an already-absolute
// URL is returned as-is so applying the origin twice is a no-op.
export function viewerOriginUrl(origin, path) {
  const normalizedOrigin = normalizeViewerOrigin(origin);
  const normalizedPath = String(path ?? "").trim();
  if (!normalizedOrigin || !normalizedPath || isAbsoluteViewerUrl(normalizedPath)) {
    return normalizedPath;
  }
  return `${normalizedOrigin}${normalizedPath.startsWith("/") ? "" : "/"}${normalizedPath}`;
}

// Rebase every URL a catalog entry carries onto the origin.
//
// Doing it HERE, once, at the catalog boundary is what keeps the rest of the
// client origin-blind: an entry's asset URLs are handed to fetches, to workers
// (which resolve relative URLs against the WORKER's origin, not the backend's)
// and to `new URL(ref, assetUrl)` resolutions, and an absolute URL survives all
// three unchanged.
export function applyViewerOriginToEntry(entry, origin) {
  const normalizedOrigin = normalizeViewerOrigin(origin);
  if (!normalizedOrigin || !entry || typeof entry !== "object") {
    return entry;
  }
  let next = entry;
  const write = (key, value) => {
    if (next === entry) {
      next = { ...entry };
    }
    next[key] = value;
  };
  for (const key of ENTRY_URL_KEYS) {
    const url = String(entry[key] ?? "").trim();
    if (!url) {
      continue;
    }
    const rebased = viewerOriginUrl(normalizedOrigin, url);
    if (rebased !== entry[key]) {
      write(key, rebased);
    }
  }
  const relations = entry.relations && typeof entry.relations === "object" ? entry.relations : null;
  if (relations) {
    let nextRelations = null;
    for (const [key, relation] of Object.entries(relations)) {
      const url = String(relation?.url ?? "").trim();
      if (!url) {
        continue;
      }
      const rebased = viewerOriginUrl(normalizedOrigin, url);
      if (rebased === relation.url) {
        continue;
      }
      if (!nextRelations) {
        nextRelations = { ...relations };
      }
      nextRelations[key] = { ...relation, url: rebased };
    }
    if (nextRelations) {
      write("relations", nextRelations);
    }
  }
  return next;
}

export function applyViewerOriginToEntries(entries, origin) {
  const list = Array.isArray(entries) ? entries : [];
  const normalizedOrigin = normalizeViewerOrigin(origin);
  if (!normalizedOrigin) {
    return list;
  }
  return list.map((entry) => applyViewerOriginToEntry(entry, normalizedOrigin));
}

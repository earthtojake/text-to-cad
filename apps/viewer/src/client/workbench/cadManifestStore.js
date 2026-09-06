// The catalog store, one instance per BACKEND ORIGIN.
//
// The standalone viewer is served by its own backend, so it has exactly one
// origin — "" (same origin) — and that instance is created at import time and
// polls exactly as it always did. A host that embeds <CadFileView> against
// another `cadgen viewer` (the desktop app) asks for the store of that origin
// instead; the two never share a snapshot, a poll loop, or a listener set.
//
// Entries handed out are rebased onto the store's origin, so every asset URL a
// consumer sees is one it can fetch from wherever it happens to be running.
import { applyViewerOriginToEntries, normalizeViewerOrigin, viewerOriginUrl } from "../file-view/viewerOrigin.js";

const CAD_CATALOG_REFRESH_INTERVAL_MS = 2_000;
const CAD_CATALOG_FETCH_TIMEOUT_MS = 10_000;
const CAD_FILE_QUERY_PARAM = "file";

function normalizeCadManifest(manifest, origin = "") {
  if (!manifest || typeof manifest !== "object") {
    return {
      schemaVersion: 4,
      entries: [],
    };
  }

  return {
    schemaVersion: 4,
    entries: applyViewerOriginToEntries(manifest.entries, origin),
  };
}

function readSearchParam(name) {
  if (typeof window === "undefined") {
    return "";
  }
  try {
    return String(new URL(window.location.href).searchParams.get(name) || "").trim();
  } catch {
    return "";
  }
}

async function readJsonError(response, fallback) {
  try {
    const payload = await response.json();
    const error = String(
      payload?.error ||
      payload?.result?.error ||
      payload?.result?.validation?.error?.message ||
      fallback
    ).trim();
    return error || fallback;
  } catch {
    return fallback;
  }
}

async function fetchWithTimeout(url, options, timeoutMs, timeoutMessage) {
  if (typeof AbortController !== "function") {
    return fetch(url, options);
  }
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort();
  }, timeoutMs);
  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new Error(timeoutMessage);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

// Build a backend URL for one origin. No directory param: the server serves one
// root, fixed at startup, and a request that named its own would be a second
// source of truth for the same fact.
export function cadApiUrl(path, {
  origin = "",
  file = "",
  params = {},
} = {}) {
  const url = new URL(path, "http://cad.local");
  const fileRef = String(file ?? "").trim();
  if (fileRef) {
    url.searchParams.set(CAD_FILE_QUERY_PARAM, fileRef);
  }
  for (const [key, value] of Object.entries(params)) {
    const text = String(value ?? "").trim();
    if (text) {
      url.searchParams.set(key, text);
    }
  }
  return viewerOriginUrl(origin, `${url.pathname}${url.search}`);
}

function createCadManifestStore(origin) {
  const listeners = new Set();
  let currentSnapshot = {
    manifest: normalizeCadManifest(null, origin),
    revision: 0,
    catalogHydrated: false,
    catalogRefreshing: typeof window !== "undefined",
    catalogError: "",
  };
  let currentManifestSignature = JSON.stringify(currentSnapshot.manifest);
  let refreshRequestId = 0;
  let refreshInFlight = null;
  // Which file the catalog request names. The same-origin store falls back to
  // the page's own `?file=`, which is where the standalone viewer keeps it; an
  // embedded surface sets it explicitly because there is no such URL to read.
  let fileHint = null;

  function currentFileRef() {
    return fileHint === null ? readSearchParam(CAD_FILE_QUERY_PARAM) : String(fileHint || "").trim();
  }

  function emit() {
    for (const listener of listeners) {
      listener();
    }
  }

  function publishCadManifest(nextManifest, { hydrated = true, refreshing = false, error = "" } = {}) {
    const manifest = normalizeCadManifest(nextManifest, origin);
    const manifestSignature = JSON.stringify(manifest);
    const manifestChanged = manifestSignature !== currentManifestSignature;
    const nextSnapshot = {
      manifest: manifestChanged ? manifest : currentSnapshot.manifest,
      revision: currentSnapshot.revision + 1,
      catalogHydrated: hydrated,
      catalogRefreshing: refreshing,
      catalogError: error,
    };
    if (
      !manifestChanged &&
      nextSnapshot.catalogHydrated === currentSnapshot.catalogHydrated &&
      nextSnapshot.catalogRefreshing === currentSnapshot.catalogRefreshing &&
      nextSnapshot.catalogError === currentSnapshot.catalogError
    ) {
      return;
    }
    if (manifestChanged) {
      currentManifestSignature = manifestSignature;
    }
    currentSnapshot = {
      ...nextSnapshot,
    };
    emit();
  }

  function publishCadRefreshState({
    refreshing = currentSnapshot.catalogRefreshing,
    error = currentSnapshot.catalogError,
  } = {}) {
    if (
      refreshing === currentSnapshot.catalogRefreshing &&
      error === currentSnapshot.catalogError
    ) {
      return;
    }
    currentSnapshot = {
      ...currentSnapshot,
      revision: currentSnapshot.revision + 1,
      catalogRefreshing: refreshing,
      catalogError: error,
    };
    emit();
  }

  async function refresh({ markRefreshing = !currentSnapshot.catalogHydrated } = {}) {
    if (typeof window === "undefined") {
      return;
    }
    if (refreshInFlight) {
      return refreshInFlight;
    }
    const requestId = ++refreshRequestId;
    if (markRefreshing) {
      publishCadRefreshState({ refreshing: true, error: "" });
    }
    refreshInFlight = (async () => {
      try {
        const response = await fetchWithTimeout(
          cadApiUrl("/__cad/catalog", { origin, file: currentFileRef() }),
          { cache: "no-store" },
          CAD_CATALOG_FETCH_TIMEOUT_MS,
          `Timed out loading CAD catalog after ${CAD_CATALOG_FETCH_TIMEOUT_MS / 1000}s`
        );
        if (!response.ok) {
          throw new Error(await readJsonError(
            response,
            `Failed to read CAD catalog: ${response.status} ${response.statusText}`
          ));
        }
        const catalog = await response.json();
        if (requestId === refreshRequestId) {
          publishCadManifest(catalog, { hydrated: true, refreshing: false, error: "" });
        }
      } catch (error) {
        if (requestId === refreshRequestId) {
          publishCadManifest(currentSnapshot.manifest, {
            hydrated: true,
            refreshing: false,
            error: error instanceof Error ? error.message : String(error),
          });
        }
        throw error;
      } finally {
        if (requestId === refreshRequestId) {
          refreshInFlight = null;
        }
      }
    })();
    return refreshInFlight;
  }

  const store = {
    origin,
    getSnapshot() {
      return currentSnapshot;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    refresh,
    setFileHint(file) {
      const next = file === null || file === undefined ? null : String(file).trim();
      fileHint = next;
    },
    publishCatalog(catalog) {
      publishCadManifest(catalog);
    },
  };

  if (typeof window !== "undefined") {
    const refreshSilently = () => {
      store.refresh({ markRefreshing: false }).catch((error) => {
        if (import.meta.env.DEV) {
          console.warn("Failed to refresh CAD catalog", error);
        }
      });
    };

    store.refresh().catch((error) => {
      if (import.meta.env.DEV) {
        console.warn("Failed to refresh CAD catalog", error);
      }
    });

    window.setInterval(() => {
      if (document.visibilityState !== "hidden") {
        refreshSilently();
      }
    }, CAD_CATALOG_REFRESH_INTERVAL_MS);
    window.addEventListener("focus", refreshSilently);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState !== "hidden") {
        refreshSilently();
      }
    });
  }

  return store;
}

const storesByOrigin = new Map();

export function getCadManifestStore(origin = "") {
  const normalizedOrigin = normalizeViewerOrigin(origin);
  let store = storesByOrigin.get(normalizedOrigin);
  if (!store) {
    store = createCadManifestStore(normalizedOrigin);
    storesByOrigin.set(normalizedOrigin, store);
  }
  return store;
}

// Unified render-artifact client API. GET reports compile state ({ state: "rendered" | "not-compiled" |
// "compiling" | "failed", ... }); a direct-render entry is always "rendered". (Replaced the STEP-specific
// requestStepSourceStatus + requestStepArtifactGeneration.)
export async function requestArtifactStatus(fileRef, { origin = "", signal } = {}) {
  if (typeof window === "undefined") {
    return null;
  }
  const normalizedFileRef = String(fileRef || "").trim();
  if (!normalizedFileRef) {
    throw new Error("Missing file");
  }
  const response = await fetch(cadApiUrl("/__cad/artifact", {
    origin,
    params: { file: normalizedFileRef },
  }), {
    method: "GET",
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error(await readJsonError(
      response,
      `Failed to check render artifact: ${response.status} ${response.statusText}`
    ));
  }
  return response.json();
}

// POST (re)builds the artifact and publishes the refreshed catalog; resolves to
// { ok, state: "rendered" | "failed", ... }.
export async function requestArtifact(fileRef, { origin = "", force = false, signal } = {}) {
  if (typeof window === "undefined") {
    return null;
  }
  const normalizedFileRef = String(fileRef || "").trim();
  if (!normalizedFileRef) {
    throw new Error("Missing file");
  }
  const response = await fetch(cadApiUrl("/__cad/artifact", {
    origin,
    params: { file: normalizedFileRef, ...(force ? { force: "1" } : {}) },
  }), {
    method: "POST",
    cache: "no-store",
    signal,
    // Custom header => a cross-origin caller must preflight, and the backend answers
    // no CORS, so a hostile page can never trigger a build (which runs the generator).
    headers: { "x-cadgen-viewer": "1" },
  });
  if (!response.ok) {
    throw new Error(await readJsonError(
      response,
      `Failed to generate render artifact: ${response.status} ${response.statusText}`
    ));
  }
  const payload = await response.json();
  if (payload?.catalog) {
    getCadManifestStore(origin).publishCatalog(payload.catalog);
  }
  return payload;
}

export function getCadManifestSnapshot() {
  return getCadManifestStore("").getSnapshot();
}

export function subscribeCadManifest(listener) {
  return getCadManifestStore("").subscribe(listener);
}

export function refreshCadCatalog(options) {
  return getCadManifestStore("").refresh(options);
}

if (typeof window !== "undefined") {
  // The same-origin store is the standalone app's, and it starts polling the
  // moment this module loads — as it always has.
  getCadManifestStore("");
}

if (import.meta.hot) {
  import.meta.hot.on("cad-catalog:changed", () => {
    // One root per instance, so a change anywhere the dev server watches is a change
    // in the directory this page is showing.
    refreshCadCatalog().catch((error) => {
      console.warn("Failed to refresh CAD catalog", error);
    });
  });
}

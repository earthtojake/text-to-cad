import { requestViewerJson } from "./viewerRequest.js";

const CAD_CATALOG_REFRESH_INTERVAL_MS = 2_000;
const CAD_CATALOG_FETCH_TIMEOUT_MS = 10_000;
const CAD_FILE_QUERY_PARAM = "file";

function normalizeCadManifest(manifest) {
  if (!manifest || typeof manifest !== "object") {
    return {
      schemaVersion: 4,
      entries: [],
    };
  }

  return {
    schemaVersion: 4,
    entries: Array.isArray(manifest.entries) ? manifest.entries : [],
  };
}

const listeners = new Set();
let currentManifestSignature = "";
let currentSnapshot = {
  manifest: normalizeCadManifest(),
  revision: 0,
  catalogHydrated: false,
  catalogRefreshing: typeof window !== "undefined",
  catalogError: "",
};
let refreshRequestId = 0;
let refreshInFlight = null;
let refreshInFlightUrl = "";
let refreshLoopStarted = false;

currentManifestSignature = JSON.stringify(currentSnapshot.manifest);

function publishCadManifest(nextManifest, { hydrated = true, refreshing = false, error = "" } = {}) {
  const manifest = normalizeCadManifest(nextManifest);
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
  for (const listener of listeners) {
    listener();
  }
}

function publishCadRefreshState({ refreshing = currentSnapshot.catalogRefreshing, error = currentSnapshot.catalogError } = {}) {
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
  for (const listener of listeners) {
    listener();
  }
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

function cadApiUrl(path, {
  includeFile = false,
  params = {},
} = {}) {
  // No directory param: the server serves one root, fixed at startup, and a request
  // that named its own would be a second source of truth for the same fact.
  const url = new URL(path, "http://cad.local");
  if (includeFile) {
    const file = readSearchParam(CAD_FILE_QUERY_PARAM);
    if (file) {
      url.searchParams.set(CAD_FILE_QUERY_PARAM, file);
    }
  }
  for (const [key, value] of Object.entries(params)) {
    const text = String(value ?? "").trim();
    if (text) {
      url.searchParams.set(key, text);
    }
  }
  return `${url.pathname}${url.search}`;
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

export async function refreshCadCatalog({
  markRefreshing = !currentSnapshot.catalogHydrated,
  fileRef = readSearchParam(CAD_FILE_QUERY_PARAM),
} = {}) {
  if (typeof window === "undefined") {
    return;
  }
  const url = cadApiUrl("/__cad/catalog", { params: { file: fileRef } });
  if (refreshInFlight) {
    if (refreshInFlightUrl === url) {
      return refreshInFlight;
    }
    // A file selection must hydrate that file even if the previous selection's
    // catalog is still loading. Keep one request in flight and then prioritize it.
    await refreshInFlight.catch(() => {});
    return refreshCadCatalog({ markRefreshing, fileRef });
  }
  const requestId = ++refreshRequestId;
  refreshInFlightUrl = url;
  if (markRefreshing) {
    publishCadRefreshState({ refreshing: true, error: "" });
  }
  refreshInFlight = (async () => {
    try {
      const response = await fetchWithTimeout(
        url,
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
        refreshInFlightUrl = "";
      }
    }
  })();
  return refreshInFlight;
}

// Unified geometry-artifact client API. GET reports compile state ({ state: "compiled" | "not-compiled" |
// "compiling" | "failed", ... }); a direct-render entry is always "compiled". (Replaced the STEP-specific
// requestStepSourceStatus + requestStepArtifactGeneration.)
export async function requestArtifactStatus(fileRef, { signal, timeoutMs = 0 } = {}) {
  if (typeof window === "undefined") {
    return null;
  }
  const normalizedFileRef = String(fileRef || "").trim();
  if (!normalizedFileRef) {
    throw new Error("Missing file");
  }
  return requestViewerJson(cadApiUrl("/__cad/artifact", {
    params: { file: normalizedFileRef },
  }), { method: "GET", cache: "no-store", signal }, "checking display assets", { timeoutMs });
}

// POST (re)builds the artifact and publishes the refreshed catalog; resolves to
// { ok, state: "compiled" | "failed", ... }.
export async function requestArtifact(fileRef, { force = false, signal } = {}) {
  if (typeof window === "undefined") {
    return null;
  }
  const normalizedFileRef = String(fileRef || "").trim();
  if (!normalizedFileRef) {
    throw new Error("Missing file");
  }
  const payload = await requestViewerJson(cadApiUrl("/__cad/artifact", {
    params: { file: normalizedFileRef, ...(force ? { force: "1" } : {}) },
  }), {
    method: "POST",
    cache: "no-store",
    signal,
    // Custom header => a cross-origin caller must preflight, and the backend answers
    // no CORS, so a hostile page can never trigger a build (which runs the generator).
    headers: { "x-cadgen-viewer": "1" },
  }, "preparing display assets");
  if (payload?.catalog) {
    publishCadManifest(payload.catalog);
  }
  return payload;
}

export function getCadManifestSnapshot() {
  return currentSnapshot;
}

export function subscribeCadManifest(listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

if (import.meta.hot) {
  import.meta.hot.on("cad-catalog:changed", (data = {}) => {
    // One root per instance, so a change anywhere the dev server watches is a change
    // in the directory this page is showing.
    refreshCadCatalog().catch((error) => {
      console.warn("Failed to refresh CAD catalog", error);
    });
  });
}

if (typeof window !== "undefined") {
  const refreshSilently = () => {
    refreshCadCatalog({ markRefreshing: false }).catch((error) => {
      if (import.meta.env.DEV) {
        console.warn("Failed to refresh CAD catalog", error);
      }
    });
  };

  refreshCadCatalog().catch((error) => {
    if (import.meta.env.DEV) {
      console.warn("Failed to refresh CAD catalog", error);
    }
  });

  if (!refreshLoopStarted) {
    refreshLoopStarted = true;
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
}

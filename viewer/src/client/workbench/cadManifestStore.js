import {
  readStoredActiveCadDir,
  rememberActiveCadDir,
} from "./cadViewerDirectorySession.mjs";

const CAD_CATALOG_REFRESH_INTERVAL_MS = 2_000;
const CAD_CATALOG_FETCH_TIMEOUT_MS = 10_000;
const CAD_GENERATION_STATUS_REFRESH_INTERVAL_MS = 750;
const CAD_DIR_QUERY_PARAM = "dir";
const CAD_FILE_QUERY_PARAM = "file";
const HOSTED_CATALOG_BACKENDS = new Set(["vercel-blob"]);

function viewerAssetBackendFromEnv() {
  return String(import.meta.env?.VIEWER_ASSET_BACKEND || "").trim().toLowerCase();
}

export function cadViewerUsesHostedCatalog(assetBackend = viewerAssetBackendFromEnv()) {
  return HOSTED_CATALOG_BACKENDS.has(String(assetBackend || "").trim().toLowerCase());
}

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

function normalizeCadGenerationStatus(status) {
  if (!status || typeof status !== "object") {
    return {
      schemaVersion: 1,
      runs: [],
      files: {},
    };
  }
  return {
    schemaVersion: 1,
    runs: Array.isArray(status.runs) ? status.runs : [],
    files: status.files && typeof status.files === "object" ? status.files : {},
  };
}

const listeners = new Set();
let currentManifestSignature = "";
let currentSnapshot = {
  manifest: normalizeCadManifest(),
  generationStatus: normalizeCadGenerationStatus(),
  revision: 0,
  catalogHydrated: false,
  catalogRefreshing: typeof window !== "undefined",
  catalogError: "",
  activeDir: "",
};
let refreshRequestId = 0;
let refreshInFlight = null;
let generationRefreshInFlight = null;
let generationStatusUnavailable = false;
let refreshLoopStarted = false;

currentManifestSignature = JSON.stringify(currentSnapshot.manifest);

function publishCadManifest(nextManifest, { hydrated = true, refreshing = false, error = "", activeDir = currentSnapshot.activeDir } = {}) {
  const manifest = normalizeCadManifest(nextManifest);
  const manifestSignature = JSON.stringify(manifest);
  const manifestChanged = manifestSignature !== currentManifestSignature;
  const nextSnapshot = {
    manifest: manifestChanged ? manifest : currentSnapshot.manifest,
    generationStatus: currentSnapshot.generationStatus,
    revision: currentSnapshot.revision + 1,
    catalogHydrated: hydrated,
    catalogRefreshing: refreshing,
    catalogError: error,
    activeDir,
  };
  if (
    !manifestChanged &&
    nextSnapshot.catalogHydrated === currentSnapshot.catalogHydrated &&
    nextSnapshot.catalogRefreshing === currentSnapshot.catalogRefreshing &&
    nextSnapshot.catalogError === currentSnapshot.catalogError &&
    nextSnapshot.activeDir === currentSnapshot.activeDir
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

function publishCadGenerationStatus(nextGenerationStatus) {
  const generationStatus = normalizeCadGenerationStatus(nextGenerationStatus);
  const previousSignature = JSON.stringify(currentSnapshot.generationStatus);
  const nextSignature = JSON.stringify(generationStatus);
  if (previousSignature === nextSignature) {
    return;
  }
  currentSnapshot = {
    ...currentSnapshot,
    generationStatus,
    revision: currentSnapshot.revision + 1,
  };
  for (const listener of listeners) {
    listener();
  }
}

function publishCadRefreshState({ refreshing = currentSnapshot.catalogRefreshing, error = currentSnapshot.catalogError, activeDir = currentSnapshot.activeDir } = {}) {
  if (
    refreshing === currentSnapshot.catalogRefreshing &&
    error === currentSnapshot.catalogError &&
    activeDir === currentSnapshot.activeDir
  ) {
    return;
  }
  currentSnapshot = {
    ...currentSnapshot,
    revision: currentSnapshot.revision + 1,
    catalogRefreshing: refreshing,
    catalogError: error,
    activeDir,
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

export function readActiveCadDir({ assetBackend = viewerAssetBackendFromEnv() } = {}) {
  if (typeof window === "undefined") {
    return "";
  }
  if (cadViewerUsesHostedCatalog(assetBackend)) {
    return "";
  }
  let url = null;
  try {
    url = new URL(window.location.href);
  } catch {
    return "";
  }
  if (url.searchParams.has(CAD_DIR_QUERY_PARAM)) {
    const queryDir = String(url.searchParams.get(CAD_DIR_QUERY_PARAM) || "").trim();
    return rememberActiveCadDir(queryDir);
  }
  return readStoredActiveCadDir();
}

function cadApiUrl(path, {
  activeDir = readActiveCadDir(),
  includeFile = false,
  params = {},
} = {}) {
  const url = new URL(path, "http://cad.local");
  if (activeDir) {
    url.searchParams.set(CAD_DIR_QUERY_PARAM, activeDir);
  }
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

export async function refreshCadCatalog({ markRefreshing = !currentSnapshot.catalogHydrated } = {}) {
  if (typeof window === "undefined") {
    return;
  }
  if (refreshInFlight) {
    return refreshInFlight;
  }
  const requestId = ++refreshRequestId;
  const activeDir = readActiveCadDir();
  if (markRefreshing) {
    publishCadRefreshState({ refreshing: true, error: "", activeDir });
  }
  refreshInFlight = (async () => {
    try {
      const response = await fetchWithTimeout(
        cadApiUrl("/__cad/catalog", { activeDir, includeFile: true }),
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
        publishCadManifest(catalog, { hydrated: true, refreshing: false, error: "", activeDir });
      }
    } catch (error) {
      if (requestId === refreshRequestId) {
        publishCadManifest(currentSnapshot.manifest, {
          hydrated: true,
          refreshing: false,
          error: error instanceof Error ? error.message : String(error),
          activeDir,
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

export async function refreshCadGenerationStatus() {
  if (typeof window === "undefined" || generationStatusUnavailable) {
    return;
  }
  const activeDir = readActiveCadDir();
  if (generationRefreshInFlight) {
    return generationRefreshInFlight;
  }
  generationRefreshInFlight = (async () => {
    try {
      const response = await fetch(cadApiUrl("/__cad/generation-status", { activeDir }), {
        cache: "no-store",
      });
      const contentType = String(response.headers?.get?.("content-type") || "");
      if (!response.ok || !contentType.includes("application/json")) {
        if (response.status === 404 || response.status === 501 || !contentType.includes("application/json")) {
          generationStatusUnavailable = true;
          publishCadGenerationStatus(null);
          return;
        }
        throw new Error(`Failed to read CAD generation status: ${response.status} ${response.statusText}`);
      }
      publishCadGenerationStatus(await response.json());
    } catch (error) {
      if (import.meta.env.DEV) {
        console.warn("Failed to refresh CAD generation status", error);
      }
    } finally {
      generationRefreshInFlight = null;
    }
  })();
  return generationRefreshInFlight;
}

export async function requestStepArtifactGeneration(fileRef, { signal } = {}) {
  if (typeof window === "undefined") {
    return null;
  }
  const normalizedFileRef = String(fileRef || "").trim();
  if (!normalizedFileRef) {
    throw new Error("Missing STEP file");
  }
  const response = await fetch(cadApiUrl("/__cad/step-artifact", {
    params: { file: normalizedFileRef },
  }), {
    method: "POST",
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error(await readJsonError(
      response,
      `Failed to generate STEP artifact: ${response.status} ${response.statusText}`
    ));
  }
  const payload = await response.json();
  if (payload?.catalog) {
    publishCadManifest(payload.catalog);
  }
  return payload;
}

export async function requestStepSourceStatus(fileRef, { signal } = {}) {
  if (typeof window === "undefined") {
    return null;
  }
  const normalizedFileRef = String(fileRef || "").trim();
  if (!normalizedFileRef) {
    throw new Error("Missing STEP file");
  }
  const response = await fetch(cadApiUrl("/__cad/step-source-status", {
    params: { file: normalizedFileRef },
  }), {
    method: "GET",
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error(await readJsonError(
      response,
      `Failed to check STEP source status: ${response.status} ${response.statusText}`
    ));
  }
  return response.json();
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
    const changedDir = String(data?.dir || "").trim();
    const activeDir = readActiveCadDir();
    if (changedDir && activeDir && changedDir !== activeDir) {
      return;
    }
    refreshCadCatalog().catch((error) => {
      console.warn("Failed to refresh CAD catalog", error);
    });
  });
  import.meta.hot.on("cad-generation-status:changed", (data = {}) => {
    const changedDir = String(data?.dir || "").trim();
    const activeDir = readActiveCadDir();
    if (changedDir && activeDir && changedDir !== activeDir) {
      return;
    }
    refreshCadGenerationStatus().catch((error) => {
      console.warn("Failed to refresh CAD generation status", error);
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
    refreshCadGenerationStatus();
  };

  refreshCadCatalog().catch((error) => {
    if (import.meta.env.DEV) {
      console.warn("Failed to refresh CAD catalog", error);
    }
  });
  refreshCadGenerationStatus();

  if (!refreshLoopStarted) {
    refreshLoopStarted = true;
    window.setInterval(() => {
      if (document.visibilityState !== "hidden") {
        refreshSilently();
      }
    }, CAD_CATALOG_REFRESH_INTERVAL_MS);
    window.setInterval(() => {
      if (document.visibilityState !== "hidden") {
        refreshCadGenerationStatus();
      }
    }, CAD_GENERATION_STATUS_REFRESH_INTERVAL_MS);
    window.addEventListener("focus", refreshSilently);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState !== "hidden") {
        refreshSilently();
      }
    });
  }
}

import { fileSheetWidthPxForSessionState } from "@hardcore/ui/renderers/cad/state";
export { cadWorkspaceDefaultFileSheetWidthForViewport } from "@hardcore/ui/renderers/cad/state";

export const CAD_DIRECTORY_SESSION_STORAGE_VERSION = 1;
export const CAD_DIRECTORY_SESSION_STORAGE_KEY = `cad-viewer:directory-session:v${CAD_DIRECTORY_SESSION_STORAGE_VERSION}`;

function normalizeUniqueStringList(value) {
  return Array.isArray(value) ? [...new Set(value.map(entry => String(entry ?? "").trim()).filter(Boolean))] : [];
}
function normalizeNullableUniqueStringList(value) { return Array.isArray(value) ? normalizeUniqueStringList(value) : null; }
function normalizeNullableBoolean(value) { return typeof value === "boolean" ? value : null; }

function readStorageJson(storage, key) {
  try {
    const rawValue = storage.getItem(key);
    return rawValue ? JSON.parse(rawValue) : null;
  } catch {
    return null;
  }
}

function reportStorageWriteFailure(key, error, options = {}) {
  if (typeof options.onWriteError === "function") {
    options.onWriteError({ key, error });
  }
}

function writeStorageJson(storage, key, value, options = {}) {
  try {
    storage.setItem(key, JSON.stringify(value));
    return true;
  } catch (error) {
    reportStorageWriteFailure(key, error, options);
    return false;
  }
}

function removeStorageItem(storage, key, options = {}) {
  try {
    storage.removeItem(key);
    return true;
  } catch (error) {
    reportStorageWriteFailure(key, error, options);
    return false;
  }
}

function browserSessionStorage() {
  return typeof window !== "undefined" ? window.sessionStorage : null;
}

export function createCadDirectorySessionState(overrides = {}, options = {}) {
  return {
    // Nullable, exactly like `fileSheetOpen`: null is "nobody has said", which
    // resolves to the panel list's own default (`@hardcore/ui/navigation`'s
    // `panels.js` — the file tree, unless the open file's Inspector claims it).
    // A stored `false` is a person who closed the panel and must come back to
    // it closed, which a plain boolean could not tell apart from a first visit.
    fileViewerOpen: normalizeNullableBoolean(overrides?.fileViewerOpen),
    fileViewerExpandedDirectoryIds: normalizeNullableUniqueStringList(overrides?.fileViewerExpandedDirectoryIds),
    fileSheetOpen: normalizeNullableBoolean(overrides?.fileSheetOpen),
    fileSheetWidthPx: fileSheetWidthPxForSessionState(
      overrides?.fileSheetWidthPx,
      options.defaultFileSheetWidthPx
    )
  };
}

function buildCadDirectorySessionStoragePayload(state = {}, options = {}) {
  const normalizedState = createCadDirectorySessionState(state, options);
  const payload = {
    version: CAD_DIRECTORY_SESSION_STORAGE_VERSION
  };
  if (typeof normalizedState.fileViewerOpen === "boolean") {
    payload.fileViewerOpen = normalizedState.fileViewerOpen;
  }
  if (Array.isArray(normalizedState.fileViewerExpandedDirectoryIds)) {
    payload.fileViewerExpandedDirectoryIds = normalizedState.fileViewerExpandedDirectoryIds;
  }
  if (typeof normalizedState.fileSheetOpen === "boolean") {
    payload.fileSheetOpen = normalizedState.fileSheetOpen;
  }
  if (normalizedState.fileSheetWidthPx) {
    payload.fileSheetWidthPx = normalizedState.fileSheetWidthPx;
  }
  return Object.keys(payload).length > 1 ? payload : null;
}

export function readCadDirectorySessionState(options = {}) {
  const storage = options.storage || browserSessionStorage();
  if (!storage) {
    return createCadDirectorySessionState({}, options);
  }
  const rawValue = readStorageJson(storage, CAD_DIRECTORY_SESSION_STORAGE_KEY);
  if (!rawValue || rawValue.version !== CAD_DIRECTORY_SESSION_STORAGE_VERSION) {
    return createCadDirectorySessionState({}, options);
  }
  return createCadDirectorySessionState(rawValue, options);
}

export function writeCadDirectorySessionState(state = {}, options = {}) {
  const storage = options.storage || browserSessionStorage();
  if (!storage) {
    return true;
  }
  const payload = buildCadDirectorySessionStoragePayload(state, options);
  if (!payload) {
    return removeStorageItem(storage, CAD_DIRECTORY_SESSION_STORAGE_KEY, options);
  }
  return writeStorageJson(storage, CAD_DIRECTORY_SESSION_STORAGE_KEY, payload, options);
}

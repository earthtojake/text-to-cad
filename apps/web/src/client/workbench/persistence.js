import {
  CUSTOM_THEME_ID,
  DEFAULT_THEME_ID,
  normalizeThemeId,
  normalizeThemeSettings
} from "@hardcore/core/lib/themeSettings.js";
import { THEME_STORAGE_KEY } from "../ui/colorScheme.js";
import { createThemeState, fileSheetWidthPxForSessionState } from "@hardcore/ui/renderers/cad/state";
export { cadWorkspaceDefaultFileSheetWidthForViewport } from "@hardcore/ui/renderers/cad/state";

export { THEME_STORAGE_KEY };
export const THEME_STORAGE_VERSION = 13;

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
    ),
    theme: normalizeDirectorySessionThemeSlice(overrides?.theme)
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
  if (normalizedState.theme) {
    payload.theme = normalizedState.theme;
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

// --- one-shot tutorial tips ---------------------------------------------
// Each tip fires the first time its moment happens and never again, so the
// record of which ones have been seen outlives the session. `?resetTips=1`
// clears it (see applyTutorialTipResetQueryParam) for demos and manual testing.
export const TUTORIAL_TIP_STORAGE_VERSION = 1;
export const TUTORIAL_TIP_STORAGE_KEY = `cad-viewer:tutorial-tips:v${TUTORIAL_TIP_STORAGE_VERSION}`;
export const TUTORIAL_TIP_RESET_QUERY_PARAM = "resetTips";

function browserLocalStorage() {
  return typeof window !== "undefined" ? window.localStorage : null;
}

export function readSeenTutorialTipIds(options = {}) {
  const storage = options.storage || browserLocalStorage();
  if (!storage) {
    return [];
  }
  const rawValue = readStorageJson(storage, TUTORIAL_TIP_STORAGE_KEY);
  if (!rawValue || rawValue.version !== TUTORIAL_TIP_STORAGE_VERSION) {
    return [];
  }
  return normalizeUniqueStringList(rawValue.seen);
}

export function markTutorialTipSeen(tipId, options = {}) {
  const storage = options.storage || browserLocalStorage();
  const normalizedTipId = String(tipId || "").trim();
  if (!storage || !normalizedTipId) {
    return false;
  }
  const seen = readSeenTutorialTipIds(options);
  if (seen.includes(normalizedTipId)) {
    return true;
  }
  return writeStorageJson(storage, TUTORIAL_TIP_STORAGE_KEY, {
    version: TUTORIAL_TIP_STORAGE_VERSION,
    seen: [...seen, normalizedTipId]
  }, options);
}

export function resetTutorialTips(options = {}) {
  const storage = options.storage || browserLocalStorage();
  if (!storage) {
    return false;
  }
  return removeStorageItem(storage, TUTORIAL_TIP_STORAGE_KEY, options);
}

// Honour `?resetTips=1`, then strip it from the URL so a reload does not keep
// re-arming the tips: the reset is a one-shot action, not a mode.
export function applyTutorialTipResetQueryParam(options = {}) {
  if (typeof window === "undefined") {
    return false;
  }
  let url;
  try {
    url = new URL(window.location.href);
  } catch {
    return false;
  }
  if (!url.searchParams.has(TUTORIAL_TIP_RESET_QUERY_PARAM)) {
    return false;
  }
  resetTutorialTips(options);
  url.searchParams.delete(TUTORIAL_TIP_RESET_QUERY_PARAM);
  try {
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  } catch {
    // A blocked replaceState only leaves the param in the address bar.
  }
  return true;
}

// Theme state is one active id plus, at most, one customized settings blob.
//
// `themeId` is "system", a built-in preset id, or "custom". Presets are
// read-only: editing any setting writes the result into the single custom slot
// and makes "custom" active, and picking a preset again is what resets it. There
// is deliberately no saved-theme library, and no save/restore action.
function prefersDarkColorScheme() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches === true;
  } catch {
    return false;
  }
}

function readThemeStoragePayload() {
  if (typeof window === "undefined") {
    return null;
  }
  const rawValue = readStorageJson(window.localStorage, THEME_STORAGE_KEY);
  return rawValue?.version === THEME_STORAGE_VERSION ? rawValue : null;
}

export function readThemeSettingsState(options = {}) {
  const payload = readThemeStoragePayload();
  return createThemeState(payload?.themeId, payload?.custom, {
    prefersDark: options.prefersDark ?? prefersDarkColorScheme()
  });
}


function isPlainStorageObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

// A directory may pin its own theme, overriding the global one for that folder.
// Same shape as global theme state: an id plus the custom slot it may point at.
function normalizeDirectorySessionThemeSlice(value) {
  if (!isPlainStorageObject(value)) {
    return null;
  }
  const themeId = normalizeThemeId(value.themeId);
  if (!themeId) {
    return null;
  }
  const custom = isPlainStorageObject(value.custom) ? normalizeThemeSettings(value.custom) : null;
  if (themeId === CUSTOM_THEME_ID && !custom) {
    return null;
  }
  return { themeId, custom };
}

export function createDirectorySessionThemeSlice(themeState = {}) {
  const slice = normalizeDirectorySessionThemeSlice(themeState);
  if (!slice) {
    return null;
  }
  // Only store a slice that actually overrides something. Persisting one that
  // merely restates the global theme would later shadow a global theme change.
  const globalPayload = readThemeStoragePayload();
  const globalThemeId = normalizeThemeId(globalPayload?.themeId) || DEFAULT_THEME_ID;
  const globalCustom = globalPayload?.custom ? normalizeThemeSettings(globalPayload.custom) : null;
  if (
    slice.themeId === globalThemeId &&
    JSON.stringify(slice.custom) === JSON.stringify(globalCustom)
  ) {
    return null;
  }
  return slice;
}

export function readDirectoryThemeSettingsState(options = {}) {
  const resolveOptions = {
    prefersDark: options.prefersDark ?? prefersDarkColorScheme()
  };
  const sessionTheme = normalizeDirectorySessionThemeSlice(readCadDirectorySessionState(options).theme);
  if (!sessionTheme) {
    return readThemeSettingsState(resolveOptions);
  }
  return createThemeState(sessionTheme.themeId, sessionTheme.custom, resolveOptions);
}

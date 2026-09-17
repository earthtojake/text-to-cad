export const SYSTEM_COLOR_SCHEME_ID = "system";
export const LIGHT_COLOR_SCHEME_ID = "light";
export const DARK_COLOR_SCHEME_ID = "dark";
export const DEFAULT_COLOR_SCHEME_ID = SYSTEM_COLOR_SCHEME_ID;
export const THEME_STORAGE_KEY = "cad-viewer:theme";
export const COLOR_SCHEME_STORAGE_KEY = "cad-viewer:color-scheme";
export const COLOR_SCHEME_COOKIE_NAME = "cad-viewer-appearance";
export const COLOR_SCHEME_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

const COLOR_SCHEME_OPTIONS = Object.freeze([
  {
    id: SYSTEM_COLOR_SCHEME_ID,
    label: "System"
  },
  {
    id: LIGHT_COLOR_SCHEME_ID,
    label: "Light"
  },
  {
    id: DARK_COLOR_SCHEME_ID,
    label: "Dark"
  }
]);

const COLOR_SCHEME_REGISTRY = Object.freeze(
  Object.fromEntries(COLOR_SCHEME_OPTIONS.map((option) => [option.id, option]))
);

export const COLOR_SCHEMES = COLOR_SCHEME_OPTIONS;

function normalizeColorSchemeId(colorSchemeId) {
  const normalizedId = String(colorSchemeId || "").trim().toLowerCase();
  return Object.hasOwn(COLOR_SCHEME_REGISTRY, normalizedId) ? normalizedId : DEFAULT_COLOR_SCHEME_ID;
}

function getColorSchemeOption(colorSchemeId) {
  return COLOR_SCHEME_REGISTRY[normalizeColorSchemeId(colorSchemeId)];
}

export function resolveColorSchemeMode(colorSchemeId, { prefersDark = false } = {}) {
  const normalizedId = normalizeColorSchemeId(colorSchemeId);
  return normalizedId === SYSTEM_COLOR_SCHEME_ID
    ? (prefersDark ? DARK_COLOR_SCHEME_ID : LIGHT_COLOR_SCHEME_ID)
    : normalizedId;
}

function browserLocalStorage() {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage || null;
  } catch {
    return null;
  }
}

function browserDocument() {
  return typeof document !== "undefined" ? document : null;
}

// Cookies are shared by viewer ports on the same host. The localStorage copy
// is a fallback when cookies are disabled and a signal for other same-origin tabs.
export function readColorSchemeCookie(target = browserDocument()) {
  try {
    for (const part of String(target?.cookie || "").split(";")) {
      const [name, ...value] = part.trim().split("=");
      if (name !== COLOR_SCHEME_COOKIE_NAME) continue;
      const preference = value.join("=");
      return Object.hasOwn(COLOR_SCHEME_REGISTRY, preference) ? preference : null;
    }
  } catch {
    // Sandboxed documents can deny cookie access while still allowing storage.
  }
  return null;
}

export function readColorSchemePreference(storage = browserLocalStorage(), target = browserDocument()) {
  const cookiePreference = readColorSchemeCookie(target);
  if (cookiePreference) return cookiePreference;
  if (!storage) {
    return DEFAULT_COLOR_SCHEME_ID;
  }
  try {
    return normalizeColorSchemeId(storage.getItem(COLOR_SCHEME_STORAGE_KEY));
  } catch {
    return DEFAULT_COLOR_SCHEME_ID;
  }
}

export function writeColorSchemePreference(colorSchemeId, options = {}) {
  const storage = Object.hasOwn(options, "storage") ? options.storage : browserLocalStorage();
  const target = Object.hasOwn(options, "document") ? options.document : browserDocument();
  const normalizedId = normalizeColorSchemeId(colorSchemeId);
  let persisted = false;
  let failure = null;
  if (target) {
    try {
      const secure = target.location?.protocol === "https:" ? "; Secure" : "";
      target.cookie = `${COLOR_SCHEME_COOKIE_NAME}=${normalizedId}; Path=/; Max-Age=${COLOR_SCHEME_COOKIE_MAX_AGE}; SameSite=Lax${secure}`;
      persisted = readColorSchemeCookie(target) === normalizedId;
      if (!persisted) failure = new Error("The browser did not save the appearance cookie");
    } catch (error) {
      failure = error;
    }
  }
  if (storage) {
    try {
      if (normalizedId === DEFAULT_COLOR_SCHEME_ID) {
        storage.removeItem(COLOR_SCHEME_STORAGE_KEY);
      } else {
        storage.setItem(COLOR_SCHEME_STORAGE_KEY, normalizedId);
      }
      // A readable stale cookie remains authoritative. Do not claim a save
      // succeeded merely because the fallback accepted a conflicting value.
      persisted ||= readColorSchemeCookie(target) === null;
    } catch (error) {
      failure ||= error;
    }
  }
  if (!persisted && failure && typeof options.onWriteError === "function") {
    options.onWriteError({ key: COLOR_SCHEME_COOKIE_NAME, error: failure });
  }
  return persisted || (!storage && !target);
}

export function applyColorSchemeToDocument(colorSchemeId, root = document.documentElement, { prefersDark = false } = {}) {
  if (!root) {
    return;
  }

  const normalizedId = normalizeColorSchemeId(colorSchemeId);
  const resolvedMode = resolveColorSchemeMode(normalizedId, { prefersDark });

  root.dataset.themePreference = normalizedId;
  root.dataset.theme = resolvedMode;
  root.classList.toggle("dark", resolvedMode === DARK_COLOR_SCHEME_ID);
  root.style.colorScheme = resolvedMode;
}

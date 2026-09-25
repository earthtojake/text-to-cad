export const SYSTEM_COLOR_SCHEME_ID = "system";
export const LIGHT_COLOR_SCHEME_ID = "light";
export const DARK_COLOR_SCHEME_ID = "dark";
export const DEFAULT_COLOR_SCHEME_ID = SYSTEM_COLOR_SCHEME_ID;
export const THEME_STORAGE_KEY = "cad-viewer:theme";
export const COLOR_SCHEME_STORAGE_KEY = "cad-viewer:color-scheme";

const COLOR_SCHEME_ALIASES = Object.freeze({
  "studio-light": LIGHT_COLOR_SCHEME_ID,
  ivory: LIGHT_COLOR_SCHEME_ID,
  graphite: DARK_COLOR_SCHEME_ID,
  blueprint: DARK_COLOR_SCHEME_ID,
  solarized: DARK_COLOR_SCHEME_ID,
  terminal: DARK_COLOR_SCHEME_ID,
  "candy-core": DARK_COLOR_SCHEME_ID
});

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

export function normalizeColorSchemeId(colorSchemeId) {
  const normalizedId = String(colorSchemeId || "").trim().toLowerCase();
  const canonicalId = COLOR_SCHEME_ALIASES[normalizedId] || normalizedId;
  return COLOR_SCHEME_REGISTRY[canonicalId] ? canonicalId : DEFAULT_COLOR_SCHEME_ID;
}

export function getColorSchemeOption(colorSchemeId) {
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

export function readColorSchemePreference(storage = browserLocalStorage()) {
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
  const storage = options.storage || browserLocalStorage();
  if (!storage) {
    return true;
  }
  const normalizedId = normalizeColorSchemeId(colorSchemeId);
  try {
    if (normalizedId === DEFAULT_COLOR_SCHEME_ID) {
      storage.removeItem(COLOR_SCHEME_STORAGE_KEY);
    } else {
      storage.setItem(COLOR_SCHEME_STORAGE_KEY, normalizedId);
    }
    return true;
  } catch (error) {
    if (typeof options.onWriteError === "function") {
      options.onWriteError({ key: COLOR_SCHEME_STORAGE_KEY, error });
    }
    return false;
  }
}

export function getColorSchemeControlLabel(colorSchemeId, { prefersDark = false } = {}) {
  const option = getColorSchemeOption(colorSchemeId);
  if (option.id !== SYSTEM_COLOR_SCHEME_ID) {
    return option.label;
  }
  const resolvedMode = resolveColorSchemeMode(colorSchemeId, { prefersDark });
  return `${option.label} (${getColorSchemeOption(resolvedMode).label})`;
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

export const SYSTEM_THEME_ID = SYSTEM_COLOR_SCHEME_ID;
export const LIGHT_THEME_ID = LIGHT_COLOR_SCHEME_ID;
export const DARK_THEME_ID = DARK_COLOR_SCHEME_ID;
export const DEFAULT_THEME_ID = DEFAULT_COLOR_SCHEME_ID;
export const THEMES = COLOR_SCHEMES;
export const normalizeThemeId = normalizeColorSchemeId;
export const getThemeOption = getColorSchemeOption;
export const resolveThemeMode = resolveColorSchemeMode;
export const getThemeControlLabel = getColorSchemeControlLabel;
export const applyThemeToDocument = applyColorSchemeToDocument;

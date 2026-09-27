// The app's appearance: System, Light or Dark. It is one of the tab's settings
// (`settings.appearance` of the tab record, `@hardcore/ui/tab-store`); this module says what
// the ids are and how System resolves against the OS, and applies the answer to the document.
export const SYSTEM_COLOR_SCHEME_ID = "system";
export const LIGHT_COLOR_SCHEME_ID = "light";
export const DARK_COLOR_SCHEME_ID = "dark";
export const DEFAULT_COLOR_SCHEME_ID = SYSTEM_COLOR_SCHEME_ID;

export const COLOR_SCHEMES = Object.freeze([
  { id: SYSTEM_COLOR_SCHEME_ID, label: "System" },
  { id: LIGHT_COLOR_SCHEME_ID, label: "Light" },
  { id: DARK_COLOR_SCHEME_ID, label: "Dark" }
]);

const KNOWN = new Set(COLOR_SCHEMES.map((option) => option.id));

export function normalizeColorSchemeId(colorSchemeId) {
  const normalizedId = String(colorSchemeId || "").trim().toLowerCase();
  return KNOWN.has(normalizedId) ? normalizedId : DEFAULT_COLOR_SCHEME_ID;
}

export function resolveColorSchemeMode(colorSchemeId, { prefersDark = false } = {}) {
  const normalizedId = normalizeColorSchemeId(colorSchemeId);
  return normalizedId === SYSTEM_COLOR_SCHEME_ID
    ? (prefersDark ? DARK_COLOR_SCHEME_ID : LIGHT_COLOR_SCHEME_ID)
    : normalizedId;
}

/** The one write of the document's colour scheme: the class Tailwind compiles against, and the property native controls read. */
export function applyColorSchemeToDocument(colorSchemeId, root = document.documentElement, { prefersDark = false } = {}) {
  if (!root) return;
  const resolvedMode = resolveColorSchemeMode(colorSchemeId, { prefersDark });
  root.classList.toggle("dark", resolvedMode === DARK_COLOR_SCHEME_ID);
  root.style.colorScheme = resolvedMode;
}

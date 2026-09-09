import assert from "node:assert/strict";
import test from "node:test";

import {
  applyColorSchemeToDocument,
  COLOR_SCHEME_STORAGE_KEY,
  DARK_COLOR_SCHEME_ID,
  DEFAULT_COLOR_SCHEME_ID,
  LIGHT_COLOR_SCHEME_ID,
  readColorSchemePreference,
  resolveColorSchemeMode,
  writeColorSchemePreference
} from "./colorScheme.js";

function createMemoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      values.set(key, String(value));
    },
    removeItem: (key) => {
      values.delete(key);
    }
  };
}

test("color scheme preference persists independently from theme settings", () => {
  const storage = createMemoryStorage();

  assert.equal(readColorSchemePreference(storage), DEFAULT_COLOR_SCHEME_ID);

  assert.equal(writeColorSchemePreference(DARK_COLOR_SCHEME_ID, { storage }), true);
  assert.equal(storage.getItem(COLOR_SCHEME_STORAGE_KEY), DARK_COLOR_SCHEME_ID);
  assert.equal(readColorSchemePreference(storage), DARK_COLOR_SCHEME_ID);
  assert.equal(resolveColorSchemeMode(readColorSchemePreference(storage), { prefersDark: false }), DARK_COLOR_SCHEME_ID);

  assert.equal(writeColorSchemePreference(LIGHT_COLOR_SCHEME_ID, { storage }), true);
  assert.equal(readColorSchemePreference(storage), LIGHT_COLOR_SCHEME_ID);

  assert.equal(writeColorSchemePreference(DEFAULT_COLOR_SCHEME_ID, { storage }), true);
  assert.equal(storage.getItem(COLOR_SCHEME_STORAGE_KEY), null);
  assert.equal(readColorSchemePreference(storage), DEFAULT_COLOR_SCHEME_ID);
  assert.equal(resolveColorSchemeMode(readColorSchemePreference(storage), { prefersDark: true }), DARK_COLOR_SCHEME_ID);
});

/** A stand-in for `document.documentElement` — the four things chrome reads. */
function createRoot() {
  const classes = new Set();
  return {
    dataset: {},
    style: {},
    classList: {
      toggle: (name, on) => {
        if (on) {
          classes.add(name);
        } else {
          classes.delete(name);
        }
      },
      contains: (name) => classes.has(name)
    }
  };
}

/*
  The chrome's light/dark comes from the app's colour scheme and NOTHING else.

  The theme used to decide it: the dominant luminance of its scene background
  was read as a "scene tone" and written here, so a dark studio could not be
  looked at through a light window and picking a cinematic preset repainted
  every panel, toolbar and menu. That function is gone; a theme reaches the
  scene and stops there. What is left is this: a scheme id, the OS preference
  for `system`, and four writes on one element.
*/
test("the document's light/dark is written from a scheme id, never from a theme", () => {
  const root = createRoot();

  applyColorSchemeToDocument(DARK_COLOR_SCHEME_ID, root);
  assert.equal(root.dataset.themePreference, DARK_COLOR_SCHEME_ID);
  assert.equal(root.dataset.theme, DARK_COLOR_SCHEME_ID);
  assert.equal(root.style.colorScheme, DARK_COLOR_SCHEME_ID);
  assert.equal(root.classList.contains("dark"), true);

  applyColorSchemeToDocument(LIGHT_COLOR_SCHEME_ID, root);
  assert.equal(root.dataset.theme, LIGHT_COLOR_SCHEME_ID);
  assert.equal(root.classList.contains("dark"), false);

  // `system` keeps the PREFERENCE and resolves the mode from the OS, so the
  // attribute says what was chosen and the class says what it came to.
  applyColorSchemeToDocument(DEFAULT_COLOR_SCHEME_ID, root, { prefersDark: true });
  assert.equal(root.dataset.themePreference, DEFAULT_COLOR_SCHEME_ID);
  assert.equal(root.dataset.theme, DARK_COLOR_SCHEME_ID);
  assert.equal(root.classList.contains("dark"), true);
  applyColorSchemeToDocument(DEFAULT_COLOR_SCHEME_ID, root, { prefersDark: false });
  assert.equal(root.dataset.theme, LIGHT_COLOR_SCHEME_ID);
  assert.equal(root.classList.contains("dark"), false);

  // A theme id is not a scheme id: anything unrecognized falls back to
  // `system` rather than being honoured as a colour.
  applyColorSchemeToDocument("cinematic", root, { prefersDark: false });
  assert.equal(root.dataset.themePreference, DEFAULT_COLOR_SCHEME_ID);
  assert.equal(root.classList.contains("dark"), false);
});

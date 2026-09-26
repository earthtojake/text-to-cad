import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";

import {
  applyColorSchemeToDocument,
  COLOR_SCHEME_STORAGE_KEY,
  COLOR_SCHEME_COOKIE_NAME,
  COLOR_SCHEME_COOKIE_MAX_AGE,
  DARK_COLOR_SCHEME_ID,
  DEFAULT_COLOR_SCHEME_ID,
  LIGHT_COLOR_SCHEME_ID,
  readColorSchemePreference,
  readColorSchemeCookie,
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
  for `system`, and two writes on one element.
*/
test("the document's light/dark is written from a scheme id, never from a theme", () => {
  const root = createRoot();

  applyColorSchemeToDocument(DARK_COLOR_SCHEME_ID, root);
  assert.equal(root.style.colorScheme, DARK_COLOR_SCHEME_ID);
  assert.equal(root.classList.contains("dark"), true);

  applyColorSchemeToDocument(LIGHT_COLOR_SCHEME_ID, root);
  assert.equal(root.style.colorScheme, LIGHT_COLOR_SCHEME_ID);
  assert.equal(root.classList.contains("dark"), false);

  // `system` resolves the mode from the OS.
  applyColorSchemeToDocument(DEFAULT_COLOR_SCHEME_ID, root, { prefersDark: true });
  assert.equal(root.classList.contains("dark"), true);
  applyColorSchemeToDocument(DEFAULT_COLOR_SCHEME_ID, root, { prefersDark: false });
  assert.equal(root.style.colorScheme, LIGHT_COLOR_SCHEME_ID);
  assert.equal(root.classList.contains("dark"), false);

  // A theme id is not a scheme id: anything unrecognized falls back to
  // `system` rather than being honoured as a colour.
  applyColorSchemeToDocument("cinematic", root, { prefersDark: false });
  assert.equal(root.style.colorScheme, LIGHT_COLOR_SCHEME_ID);
  assert.equal(root.classList.contains("dark"), false);
});

/*
  The page's first paint, before any module loads, reads the preference the same way the
  app does: the cookie is authoritative, so a page whose cookie says dark never paints the
  light localStorage value first and then flips.
*/
function firstPaint({ cookie = "", stored = null, prefersDark = false }) {
  const html = readFileSync(new URL("../../../index.html", import.meta.url), "utf8");
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const root = createRoot();
  vm.runInNewContext(script, {
    document: { documentElement: root, cookie },
    window: { matchMedia: () => ({ matches: prefersDark }), localStorage: { getItem: () => stored } }
  });
  return root;
}

test("the first paint honours the appearance cookie before localStorage, as the app does", () => {
  const dark = firstPaint({ cookie: `other=1; ${COLOR_SCHEME_COOKIE_NAME}=${DARK_COLOR_SCHEME_ID}`, stored: LIGHT_COLOR_SCHEME_ID });
  assert.equal(dark.classList.contains("dark"), true);
  assert.equal(dark.style.colorScheme, DARK_COLOR_SCHEME_ID);
  const light = firstPaint({ stored: LIGHT_COLOR_SCHEME_ID, prefersDark: true });
  assert.equal(light.classList.contains("dark"), false);
  const system = firstPaint({ cookie: `${COLOR_SCHEME_COOKIE_NAME}=nonsense`, prefersDark: true });
  assert.equal(system.classList.contains("dark"), true);
  // The same answer the module gives for the same cookie.
  assert.equal(readColorSchemePreference(createMemoryStorage(), { cookie: `${COLOR_SCHEME_COOKIE_NAME}=${DARK_COLOR_SCHEME_ID}` }), DARK_COLOR_SCHEME_ID);
});

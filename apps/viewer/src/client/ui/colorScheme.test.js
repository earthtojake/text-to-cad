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

function createCookieDocument(protocol = "http:") {
  const values = new Map();
  return {
    location: { protocol },
    lastCookieWrite: "",
    get cookie() {
      return [...values].map(([key, value]) => `${key}=${value}`).join("; ");
    },
    set cookie(value) {
      this.lastCookieWrite = value;
      const [pair] = value.split(";");
      const [key, ...parts] = pair.split("=");
      values.set(key, parts.join("="));
    }
  };
}

test("appearance cookie restores across viewer ports and overrides stale per-origin preferences", () => {
  const document = createCookieDocument();
  const firstPort = createMemoryStorage();
  const secondPort = createMemoryStorage();
  secondPort.setItem(COLOR_SCHEME_STORAGE_KEY, "light");
  assert.equal(writeColorSchemePreference("dark", { storage: firstPort, document }), true);
  assert.equal(readColorSchemePreference(secondPort, document), "dark");
  assert.equal(readColorSchemePreference(createMemoryStorage(), document), "dark");
  assert.match(document.lastCookieWrite, /; Path=\/;/);
  assert.match(document.lastCookieWrite, new RegExp(`Max-Age=${COLOR_SCHEME_COOKIE_MAX_AGE}`));
  assert.match(document.lastCookieWrite, /; SameSite=Lax$/);

  assert.equal(writeColorSchemePreference("system", { storage: firstPort, document }), true);
  assert.equal(readColorSchemeCookie(document), "system");
  assert.equal(readColorSchemePreference(secondPort, document), "system");
});

test("HTTPS appearance cookies are Secure and persistence survives either storage mechanism being blocked", () => {
  const document = createCookieDocument("https:");
  const blockedStorage = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  assert.equal(writeColorSchemePreference("dark", { storage: blockedStorage, document }), true);
  assert.match(document.lastCookieWrite, /; Secure$/);
  assert.equal(readColorSchemePreference(blockedStorage, document), "dark");

  const blockedDocument = { get cookie() { throw new Error("blocked"); }, set cookie(value) { throw new Error("blocked"); } };
  const storage = createMemoryStorage();
  assert.equal(writeColorSchemePreference("light", { storage, document: blockedDocument }), true);
  assert.equal(readColorSchemePreference(storage, blockedDocument), "light");
  const failures = [];
  assert.equal(writeColorSchemePreference("light", { storage: blockedStorage, document: blockedDocument, onWriteError: (error) => failures.push(error) }), false);
  assert.equal(failures.length, 1);
});

test("appearance cookie parser accepts only an exact cookie name and closed preference values", () => {
  assert.equal(readColorSchemeCookie({ cookie: `other-${COLOR_SCHEME_COOKIE_NAME}=dark; ${COLOR_SCHEME_COOKIE_NAME}=light` }), "light");
  for (const value of ["cinematic", "dark=extra", "toString", "__proto__", "dark%3B"]) {
    assert.equal(readColorSchemeCookie({ cookie: `${COLOR_SCHEME_COOKIE_NAME}=${value}` }), null);
  }
});

test("an unwritable stale cookie cannot be reported as a successful appearance save", () => {
  const document = {
    get cookie() { return `${COLOR_SCHEME_COOKIE_NAME}=dark`; },
    set cookie(value) {}
  };
  const storage = createMemoryStorage();
  const failures = [];
  assert.equal(writeColorSchemePreference("light", { document, storage, onWriteError: error => failures.push(error) }), false);
  assert.equal(failures.length, 1);
  assert.equal(readColorSchemePreference(storage, document), "dark");
});

test("synchronous startup and hydrated app resolve the same appearance before rendering", () => {
  const html = readFileSync(new URL("../../../index.html", import.meta.url), "utf8");
  const startup = html.match(/<script>\s*([\s\S]*?)\s*<\/script>/)?.[1];
  assert.ok(startup);
  for (const cookie of ["", `${COLOR_SCHEME_COOKIE_NAME}=dark`, `${COLOR_SCHEME_COOKIE_NAME}=system`, `${COLOR_SCHEME_COOKIE_NAME}=invalid`]) {
    for (const saved of [null, "light", "dark", "system"]) {
      for (const prefersDark of [false, true]) {
        const storage = createMemoryStorage();
        if (saved) storage.setItem(COLOR_SCHEME_STORAGE_KEY, saved);
        const root = createRoot();
        const document = { cookie, documentElement: root };
        vm.runInNewContext(startup, { document, window: { localStorage: storage, matchMedia: () => ({ matches: prefersDark }) } });
        const preference = readColorSchemePreference(storage, document);
        assert.equal(root.dataset.themePreference, preference);
        assert.equal(root.dataset.theme, resolveColorSchemeMode(preference, { prefersDark }));
      }
    }
  }
  const root = createRoot();
  const document = { cookie: `${COLOR_SCHEME_COOKIE_NAME}=dark`, documentElement: root };
  vm.runInNewContext(startup, { document, window: { get localStorage() { throw new Error("blocked"); }, matchMedia: () => ({ matches: false }) } });
  assert.equal(root.dataset.theme, "dark");
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

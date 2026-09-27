import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";

import {
  applyColorSchemeToDocument,
  COLOR_SCHEMES,
  DARK_COLOR_SCHEME_ID,
  DEFAULT_COLOR_SCHEME_ID,
  LIGHT_COLOR_SCHEME_ID,
  normalizeColorSchemeId,
  resolveColorSchemeMode
} from "./colorScheme.js";

function createRoot() {
  const classes = new Set();
  return {
    classList: { toggle(name, force) { if (force) classes.add(name); else classes.delete(name); return classes.has(name); }, contains: (name) => classes.has(name) },
    style: { colorScheme: "" }
  };
}

test("System, Light and Dark are the appearances; anything else is System, and System is the OS's answer", () => {
  assert.deepEqual(COLOR_SCHEMES.map((option) => option.id), ["system", "light", "dark"]);
  assert.equal(normalizeColorSchemeId(" Dark "), DARK_COLOR_SCHEME_ID);
  for (const value of ["cinematic", "", null, undefined, 7]) assert.equal(normalizeColorSchemeId(value), DEFAULT_COLOR_SCHEME_ID);
  assert.equal(resolveColorSchemeMode("system", { prefersDark: true }), DARK_COLOR_SCHEME_ID);
  assert.equal(resolveColorSchemeMode("system", { prefersDark: false }), LIGHT_COLOR_SCHEME_ID);
  assert.equal(resolveColorSchemeMode("light", { prefersDark: true }), LIGHT_COLOR_SCHEME_ID);
  assert.equal(resolveColorSchemeMode("dark", { prefersDark: false }), DARK_COLOR_SCHEME_ID);
});

test("applying an appearance writes the dark class and the colour-scheme property, and nothing for a bad id but System", () => {
  const root = createRoot();
  applyColorSchemeToDocument(DARK_COLOR_SCHEME_ID, root);
  assert.equal(root.style.colorScheme, DARK_COLOR_SCHEME_ID);
  assert.equal(root.classList.contains("dark"), true);
  applyColorSchemeToDocument(LIGHT_COLOR_SCHEME_ID, root, { prefersDark: true });
  assert.equal(root.style.colorScheme, LIGHT_COLOR_SCHEME_ID);
  assert.equal(root.classList.contains("dark"), false);
  applyColorSchemeToDocument("cinematic", root, { prefersDark: false });
  assert.equal(root.style.colorScheme, LIGHT_COLOR_SCHEME_ID);
  assert.doesNotThrow(() => applyColorSchemeToDocument("dark", null));
});

/*
  The page's first paint, before any module loads, reads the appearance from the tab record in
  sessionStorage, the same record the app reads: a tab left in Dark never paints light and flips.
*/
function firstPaint({ record, prefersDark = false, blocked = false }) {
  const html = readFileSync(new URL("../../../index.html", import.meta.url), "utf8");
  const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const root = createRoot();
  vm.runInNewContext(script, {
    document: { documentElement: root },
    window: { matchMedia: () => ({ matches: prefersDark }), get sessionStorage() {
      if (blocked) throw new Error("blocked");
      return { getItem: (key) => (key === "hardcore:tab:v1" && record !== undefined ? JSON.stringify(record) : null) };
    } }
  });
  return root;
}

test("the first paint reads the tab record's appearance before any module loads, and follows the OS without one", () => {
  const html = readFileSync(new URL("../../../index.html", import.meta.url), "utf8");
  assert.ok(html.indexOf("<script>") < html.indexOf("</head>"), "the script is in the head, before anything is painted");
  const dark = firstPaint({ record: { version: 1, settings: { appearance: DARK_COLOR_SCHEME_ID } } });
  assert.equal(dark.classList.contains("dark"), true);
  assert.equal(dark.style.colorScheme, DARK_COLOR_SCHEME_ID);
  const light = firstPaint({ record: { version: 1, settings: { appearance: LIGHT_COLOR_SCHEME_ID } }, prefersDark: true });
  assert.equal(light.classList.contains("dark"), false);
  const system = firstPaint({ record: { version: 1, settings: { appearance: "nonsense" } }, prefersDark: true });
  assert.equal(system.classList.contains("dark"), true);
  assert.equal(firstPaint({ record: undefined, prefersDark: true }).classList.contains("dark"), true, "a new tab follows the OS");
  assert.equal(firstPaint({ record: { version: 0, settings: { appearance: "light" } }, prefersDark: true }).classList.contains("dark"), true, "another version's record is nobody's");
  assert.equal(firstPaint({ blocked: true, prefersDark: false }).style.colorScheme, LIGHT_COLOR_SCHEME_ID, "blocked storage still paints");
});

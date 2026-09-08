// The three things a host may pin on <CadFileView> — layout mode, sheet width,
// colour scheme — and, more importantly, what "not pinned" resolves to: the
// standalone viewer passes nothing, so every default here must mean "measure
// it yourself", or the shipping app changes shape.
import assert from "node:assert/strict";
import test from "node:test";

import {
  DESKTOP_TAB_TOOLS_MAX_WIDTH,
  DESKTOP_TAB_TOOLS_MIN_WIDTH,
  applyColorSchemeUnlessHostPinned,
  hostPrefersDarkForColorScheme,
  normalizeHostSheetWidth,
  resolveHostLayoutMode,
} from "./hostLayout.js";

test("layout: only \"desktop\" pins anything", () => {
  assert.equal(resolveHostLayoutMode("desktop"), "desktop");
  assert.equal(resolveHostLayoutMode(" Desktop "), "desktop");
  assert.equal(resolveHostLayoutMode("auto"), null);
  assert.equal(resolveHostLayoutMode(undefined), null);
  assert.equal(resolveHostLayoutMode(""), null);
  assert.equal(resolveHostLayoutMode("mobile"), null);
});

test("sheet width: null means the stored width, otherwise clamped to the sheet's range", () => {
  assert.equal(normalizeHostSheetWidth(null), null);
  assert.equal(normalizeHostSheetWidth(undefined), null);
  assert.equal(normalizeHostSheetWidth(0), null);
  assert.equal(normalizeHostSheetWidth(-40), null);
  assert.equal(normalizeHostSheetWidth("nope"), null);
  assert.equal(normalizeHostSheetWidth(300), 300);
  assert.equal(normalizeHostSheetWidth(300.4), 300);
  assert.equal(normalizeHostSheetWidth(10), DESKTOP_TAB_TOOLS_MIN_WIDTH);
  assert.equal(normalizeHostSheetWidth(10_000), DESKTOP_TAB_TOOLS_MAX_WIDTH);
});

test("colour scheme: dark and light resolve, anything else is the surface's own", () => {
  assert.equal(hostPrefersDarkForColorScheme("dark"), true);
  assert.equal(hostPrefersDarkForColorScheme("light"), false);
  assert.equal(hostPrefersDarkForColorScheme("DARK"), true);
  assert.equal(hostPrefersDarkForColorScheme(null), null);
  assert.equal(hostPrefersDarkForColorScheme(undefined), null);
  assert.equal(hostPrefersDarkForColorScheme("system"), null);
});

/*
  The surface writes the document only when NOBODY else owns it.

  The desktop app applies its own light/dark to `<html>` from its own settings
  row and passes the resolved answer down as `colorScheme`. This surface has a
  colour-scheme preference of its own (`cad-viewer:color-scheme`, which
  defaults to the OS) and it is nobody's choice inside a host — so a write from
  here flipped the whole app: on mount, on a storage event from another window,
  and again on every re-resolve. One writer per document is the rule, and this
  is where it is enforced.
*/

/** A stand-in for `document.documentElement`: the four things chrome reads. */
function createRoot() {
  const classes = new Set();
  return {
    dataset: {},
    style: {},
    classList: {
      toggle: (name, on) => (on ? classes.add(name) : classes.delete(name)),
      contains: (name) => classes.has(name),
    },
    get written() {
      return (
        Object.keys(this.dataset).length > 0 ||
        Object.keys(this.style).length > 0 ||
        classes.size > 0
      );
    },
  };
}

test("colour scheme: a host's pin skips the document write entirely", () => {
  for (const colorScheme of ["dark", "light", "Dark", " light "]) {
    const root = createRoot();
    // The preference disagrees with the host on purpose: if it were consulted
    // at all, a stored `dark` under a light host would show up here.
    const mode = applyColorSchemeUnlessHostPinned(colorScheme, "dark", { prefersDark: true, root });
    assert.equal(mode, null, `${colorScheme} should not be written`);
    assert.equal(root.written, false, `${colorScheme} touched the document`);
    assert.deepEqual(root.dataset, {});
    assert.deepEqual(root.style, {});
    assert.equal(root.classList.contains("dark"), false);
  }
});

test("colour scheme: with no host pin the surface writes its own preference", () => {
  const dark = createRoot();
  assert.equal(applyColorSchemeUnlessHostPinned(null, "dark", { root: dark }), "dark");
  assert.equal(dark.classList.contains("dark"), true);
  assert.equal(dark.dataset.theme, "dark");
  assert.equal(dark.style.colorScheme, "dark");

  const light = createRoot();
  assert.equal(applyColorSchemeUnlessHostPinned("", "light", { root: light }), "light");
  assert.equal(light.classList.contains("dark"), false);
  assert.equal(light.dataset.theme, "light");

  // `system` — the standalone default — resolves against the OS, live.
  const system = createRoot();
  assert.equal(
    applyColorSchemeUnlessHostPinned(undefined, "system", { prefersDark: true, root: system }),
    "dark",
  );
  assert.equal(system.dataset.themePreference, "system");
  assert.equal(system.classList.contains("dark"), true);
  assert.equal(
    applyColorSchemeUnlessHostPinned(undefined, "system", { prefersDark: false, root: system }),
    "light",
  );
  assert.equal(system.dataset.theme, "light");
  assert.equal(system.classList.contains("dark"), false);
});

test("colour scheme: a host that passes \"system\" is not a host that pinned one", () => {
  // `hostPrefersDarkForColorScheme("system")` is null, so the surface owns the
  // document — which is right for a page with no host, and is why a host must
  // resolve `system` before handing it over rather than forwarding the word.
  const root = createRoot();
  assert.equal(applyColorSchemeUnlessHostPinned("system", "dark", { root }), "dark");
  assert.equal(root.classList.contains("dark"), true);
});

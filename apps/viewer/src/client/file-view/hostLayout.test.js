// The three things a host may pin on <CadFileView> — layout mode, sheet width,
// colour scheme — and, more importantly, what "not pinned" resolves to: the
// standalone viewer passes nothing, so every default here must mean "measure
// it yourself", or the shipping app changes shape.
import assert from "node:assert/strict";
import test from "node:test";

import {
  DESKTOP_TAB_TOOLS_MAX_WIDTH,
  DESKTOP_TAB_TOOLS_MIN_WIDTH,
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

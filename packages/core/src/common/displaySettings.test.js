import assert from "node:assert/strict";
import test from "node:test";

import {
  CAD_DISPLAY_MODE,
  DEFAULT_DISPLAY_EDGE_SETTINGS,
  DEFAULT_DISPLAY_GUIDE_SETTINGS,
  DEFAULT_DISPLAY_SETTINGS,
  DEFAULT_EXPLODED_VIEW_SETTINGS,
  DEFAULT_PART_COLOR_SETTINGS,
  normalizeDisplayEdgeSettings,
  normalizeDisplaySettings,
  normalizeExplodedViewSettings,
  validateDisplaySettings
} from "./displaySettings.js";

test("display settings own CAD presentation fields while camera owns projection", () => {
  assert.deepEqual(normalizeDisplaySettings(), DEFAULT_DISPLAY_SETTINGS);
  assert.equal(normalizeDisplaySettings({ mode: "wireframe" }).mode, CAD_DISPLAY_MODE.WIREFRAME);
  assert.throws(
    () => normalizeDisplaySettings({ projection: "perspective" }),
    /Unsupported display fields: projection/
  );
  assert.deepEqual(normalizeDisplaySettings({
    mode: "wireframe",
    clip: { axis: "z", at: 12.5, invert: true }
  }), {
    mode: CAD_DISPLAY_MODE.WIREFRAME,
    clip: {
      enabled: true,
      axis: "z",
      invert: true,
      partColors: true,
      at: 12.5
    },
    exploded: DEFAULT_EXPLODED_VIEW_SETTINGS,
    edges: DEFAULT_DISPLAY_EDGE_SETTINGS,
    guides: DEFAULT_DISPLAY_GUIDE_SETTINGS,
    partColor: DEFAULT_PART_COLOR_SETTINGS
  });
});

test("internal display settings keep edge color and visibility while widths stay renderer owned", () => {
  assert.deepEqual(normalizeDisplayEdgeSettings({ enabled: false, silhouette: true }), {
    enabled: false, silhouette: true
  });
  assert.equal(normalizeDisplayEdgeSettings({ color: "#f00", visibility: "all" }).color, "#ff0000");
  for (const key of ["thickness", "classes", "highlightColor", "highlightOpacity", "highlightThickness", "silhouetteScale", "depthTest"]) {
    assert.throws(() => validateDisplaySettings({ edges: { [key]: 1 } }), /Unsupported display.edges fields/);
  }
  for (const key of ["centerColor", "cellColor"]) {
    assert.throws(() => validateDisplaySettings({ guides: { grid: { [key]: 1 } } }), /Unsupported display.guides.grid fields/);
  }
  // Density is a grid setting (the Grid preset's finer grid), bounded like the scene's own.
  assert.doesNotThrow(() => validateDisplaySettings({ guides: { grid: { enabled: true, density: 2 } } }));
  assert.throws(() => validateDisplaySettings({ guides: { grid: { enabled: true, density: 10 } } }), /density/);
});

test("display settings normalize exploded view, guides, and part colors", () => {
  assert.deepEqual(normalizeExplodedViewSettings({ enabled: true, amount: 0.5 }), {
    enabled: true,
    amount: 0.5
  });
  assert.equal(normalizeExplodedViewSettings({ amount: 9 }).amount, 1);
  assert.equal(normalizeExplodedViewSettings({ amount: -1 }).amount, 0);
  assert.deepEqual(normalizeExplodedViewSettings({ enabled: 1 }), { enabled: false, amount: 0 });

  const normalized = normalizeDisplaySettings({
    guides: {
      grid: { enabled: false },
      axis: { enabled: false }
    },
    partColor: { mode: "by_part", color: "#123456", colors: ["#abc", "#445566"] }
  });
  assert.equal(normalized.guides.grid.enabled, false);
  assert.deepEqual(normalized.guides.grid, { enabled: false });
  assert.equal(normalized.guides.axis.enabled, false);
  assert.deepEqual(normalized.partColor, {
    mode: "by_part",
    color: "#123456",
    colors: ["#aabbcc", "#445566"]
  });
});

test("display mode vocabulary is canonical", () => {
  for (const mode of Object.values(CAD_DISPLAY_MODE)) {
    assert.equal(normalizeDisplaySettings({ mode }).mode, mode);
  }
  for (const alias of ["render", "solid", "rendered", "edges", "shaded-with-edges", "x-ray", "theme", "wire"]) {
    assert.throws(() => normalizeDisplaySettings({ mode: alias }), /Unknown display mode/);
  }
});

test("grid color and opacity stay optional and validate at the shared display boundary", () => {
  const guides = { grid: { enabled: true, color: "#ABC", opacity: 0 } };
  validateDisplaySettings({ guides });
  assert.deepEqual(normalizeDisplaySettings({ guides }).guides.grid, {
    enabled: true, color: "#aabbcc", opacity: 0
  });
  assert.deepEqual(normalizeDisplaySettings({ guides: { grid: { enabled: false } } }).guides.grid,
    { enabled: false });
  for (const grid of [{ color: "red" }, { opacity: -0.1 }, { opacity: 1.1 }, { opacity: true }]) {
    assert.throws(() => validateDisplaySettings({ guides: { grid } }), /display.guides.grid/);
  }
});

test('Explode starts halfway on enable but preserves an explicit zero', () => {
  assert.deepEqual(normalizeExplodedViewSettings({ enabled: true }), { enabled: true, amount: 0.5 });
  assert.deepEqual(normalizeExplodedViewSettings({ enabled: true, amount: 0 }), { enabled: true, amount: 0 });
  assert.deepEqual(normalizeExplodedViewSettings({ enabled: false }), { enabled: false, amount: 0 });
});

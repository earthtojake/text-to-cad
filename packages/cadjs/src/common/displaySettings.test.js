import assert from "node:assert/strict";
import test from "node:test";

import {
  CAD_DISPLAY_MODE,
  CAMERA_PROJECTION,
  DEFAULT_DISPLAY_EDGE_SETTINGS,
  DEFAULT_DISPLAY_SETTINGS,
  DEFAULT_EXPLODED_VIEW_SETTINGS,
  displayModeForcesEdges,
  displayModeShowsEdges,
  displayModeShowsThroughEdges,
  displayModeSurfaceOpacity,
  displayModeUsesUnlitSurfaces,
  displaySettingsEqual,
  normalizeDisplayEdgeSettings,
  normalizeDisplaySettings,
  normalizeExplodedViewSettings,
  resolveDisplayMode
} from "./displaySettings.js";

test("display settings normalize mode and clip independently from theme settings", () => {
  assert.deepEqual(normalizeDisplaySettings(), DEFAULT_DISPLAY_SETTINGS);
  assert.equal(resolveDisplayMode({ mode: "wireframe" }), CAD_DISPLAY_MODE.WIREFRAME);
  // Projection is a theme trait now, not a display setting: it is dropped on
  // normalization even when a stale caller still passes it.
  assert.equal(Object.hasOwn(normalizeDisplaySettings(), "projection"), false);
  assert.equal(Object.hasOwn(normalizeDisplaySettings({ projection: "perspective" }), "projection"), false);
  assert.deepEqual(normalizeDisplaySettings({
    projection: "perspective",
    mode: "wireframe",
    clip: {
      enabled: true,
      axis: "z",
      offset: 0.4,
      invert: true
    }
  }), {
    mode: CAD_DISPLAY_MODE.WIREFRAME,
    clip: {
      enabled: true,
      axis: "z",
      offset: 0.4,
      offsets: {
        x: 0,
        y: 0,
        z: 0.4
      },
      invert: true
    },
    exploded: DEFAULT_EXPLODED_VIEW_SETTINGS,
    edges: DEFAULT_DISPLAY_EDGE_SETTINGS
  });
});

test("display settings normalize edge styling independently from theme settings", () => {
  assert.deepEqual(normalizeDisplayEdgeSettings({
    enabled: false,
    color: "#ABC",
    thickness: 2,
    classes: {
      tangent: {
        color: "#456",
        opacity: 0.25,
        thickness: 4
      }
    },
    highlightColor: "#123456",
    highlightOpacity: 0.4,
    highlightThickness: 4,
    silhouette: true,
    silhouetteScale: 0.01
  }), {
    enabled: false,
    color: "#aabbcc",
    thickness: 2,
    classes: {
      feature: { color: "#aabbcc", opacity: 1, thickness: 1.15 },
      tangent: { color: "#445566", opacity: 0.25, thickness: 4 },
      seam: { color: "#aabbcc", opacity: 0.85, thickness: 1.15 },
      degenerate: { color: "#aabbcc", opacity: 1, thickness: 0 }
    },
    highlightColor: "#123456",
    highlightOpacity: 0.4,
    highlightThickness: 4,
    silhouette: true,
    silhouetteScale: 0.01
  });
  assert.deepEqual(normalizeDisplaySettings({
    mode: "solid",
    edges: {
      enabled: false,
      color: "#456"
    }
  }).edges, {
    ...DEFAULT_DISPLAY_EDGE_SETTINGS,
    enabled: false,
    color: "#445566",
    classes: {
      feature: { color: "#445566", opacity: 1, thickness: 1.15 },
      tangent: { color: "#445566", opacity: 0.5, thickness: 1.15 },
      seam: { color: "#445566", opacity: 0.85, thickness: 1.15 },
      degenerate: { color: "#445566", opacity: 1, thickness: 0 }
    }
  });
});

test("display settings normalize the exploded view to enabled + amount", () => {
  assert.deepEqual(
    normalizeExplodedViewSettings({ enabled: true, amount: 0.5 }),
    { enabled: true, amount: 0.5 }
  );
  // Amount clamps; missing amount defaults to 0 (assembled).
  assert.equal(normalizeExplodedViewSettings({ amount: 9 }).amount, 1);
  assert.equal(normalizeExplodedViewSettings({ amount: -1 }).amount, 0);
  assert.deepEqual(normalizeExplodedViewSettings({ enabled: 1 }), { enabled: true, amount: 0 });
  // Legacy step-document fields are simply dropped.
  assert.deepEqual(
    normalizeExplodedViewSettings({ enabled: true, steps: [{}], auto: { mode: "x" }, order: "sequential" }),
    { enabled: true, amount: 0 }
  );

  assert.equal(normalizeDisplaySettings({ exploded: true }).exploded.enabled, false);
  assert.equal(normalizeDisplaySettings({ mode: "exploded", exploded: { enabled: true } }).exploded.enabled, true);
  assert.deepEqual(normalizeDisplaySettings({ mode: "exploded view" }), DEFAULT_DISPLAY_SETTINGS);
});

test("display modes normalize common CAD aliases", () => {
  assert.equal(resolveDisplayMode({ mode: "edges" }), CAD_DISPLAY_MODE.SOLID);
  assert.equal(resolveDisplayMode({ mode: "shaded-with-edges" }), CAD_DISPLAY_MODE.SOLID);
  assert.equal(resolveDisplayMode({ mode: "shaded without edges" }), CAD_DISPLAY_MODE.RENDERED);
  assert.equal(resolveDisplayMode({ mode: "x-ray" }), CAD_DISPLAY_MODE.TRANSPARENT);
  assert.equal(resolveDisplayMode({ mode: "hidden edges visible" }), CAD_DISPLAY_MODE.HIDDEN_EDGES);
  assert.equal(resolveDisplayMode({ mode: "hidden-lines-removed" }), CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED);
  assert.equal(resolveDisplayMode({ mode: "flat" }), CAD_DISPLAY_MODE.UNSHADED);
  assert.equal(resolveDisplayMode({ mode: "theme" }), CAD_DISPLAY_MODE.RENDERED);
  assert.equal(resolveDisplayMode({ mode: "wire" }), CAD_DISPLAY_MODE.WIREFRAME);
});

test("display mode policies describe edge and surface behavior", () => {
  assert.equal(displayModeShowsEdges(CAD_DISPLAY_MODE.SOLID, { enabled: false }), true);
  assert.equal(displayModeForcesEdges(CAD_DISPLAY_MODE.SOLID), true);
  assert.equal(displayModeShowsEdges(CAD_DISPLAY_MODE.RENDERED, { enabled: true }), false);
  assert.equal(displayModeShowsThroughEdges(CAD_DISPLAY_MODE.HIDDEN_EDGES), true);
  assert.equal(displayModeShowsThroughEdges(CAD_DISPLAY_MODE.TRANSPARENT), true);
  assert.equal(displayModeUsesUnlitSurfaces(CAD_DISPLAY_MODE.UNSHADED), true);
  assert.equal(displayModeSurfaceOpacity(CAD_DISPLAY_MODE.TRANSPARENT, 1), 0.22);
  assert.equal(displayModeSurfaceOpacity(CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED, 1), 0.045);
});

test("display settings compare after normalization", () => {
  assert.equal(displaySettingsEqual(
    { mode: "wireframe", clip: { enabled: true, axis: "x", offset: 0.5 } },
    { mode: CAD_DISPLAY_MODE.WIREFRAME, clip: { enabled: true, axis: "x", offsets: { x: 0.5 } } }
  ), true);
  assert.equal(displaySettingsEqual(
    { mode: "solid", clip: { enabled: true } },
    { mode: "wireframe", clip: { enabled: true } }
  ), false);
  assert.equal(displaySettingsEqual(
    { mode: "solid", exploded: { enabled: true } },
    { mode: "solid", exploded: { enabled: false } }
  ), false);
  assert.equal(displaySettingsEqual(
    { mode: "solid", edges: { color: "#111111" } },
    { mode: "solid", edges: { color: "#222222" } }
  ), false);
  // Projection no longer belongs to display settings, so differing projection
  // values do not make two otherwise-equal display settings unequal.
  assert.equal(displaySettingsEqual(
    { mode: "solid", projection: "orthographic" },
    { mode: "solid", projection: "perspective" }
  ), true);
});

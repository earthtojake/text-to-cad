import assert from "node:assert/strict";
import test from "node:test";

import {
  CAD_DISPLAY_MODE,
  DEFAULT_DISPLAY_SETTINGS,
  displayModeForcesEdges,
  displayModeShowsEdges,
  displayModeShowsThroughEdges,
  displayModeSurfaceOpacity,
  displayModeUsesUnlitSurfaces,
  displaySettingsEqual,
  normalizeDisplaySettings,
  resolveDisplayMode
} from "./displaySettings.js";

test("display settings normalize mode and clip independently from appearance settings", () => {
  assert.deepEqual(normalizeDisplaySettings(), DEFAULT_DISPLAY_SETTINGS);
  assert.equal(resolveDisplayMode({ mode: "wireframe" }), CAD_DISPLAY_MODE.WIREFRAME);
  assert.deepEqual(normalizeDisplaySettings({
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
    }
  });
});

test("display modes normalize common CAD aliases", () => {
  assert.equal(resolveDisplayMode({ mode: "edges" }), CAD_DISPLAY_MODE.SOLID);
  assert.equal(resolveDisplayMode({ mode: "shaded-with-edges" }), CAD_DISPLAY_MODE.SOLID);
  assert.equal(resolveDisplayMode({ mode: "shaded without edges" }), CAD_DISPLAY_MODE.RENDERED);
  assert.equal(resolveDisplayMode({ mode: "x-ray" }), CAD_DISPLAY_MODE.TRANSPARENT);
  assert.equal(resolveDisplayMode({ mode: "hidden edges visible" }), CAD_DISPLAY_MODE.HIDDEN_EDGES);
  assert.equal(resolveDisplayMode({ mode: "hidden-lines-removed" }), CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED);
  assert.equal(resolveDisplayMode({ mode: "flat" }), CAD_DISPLAY_MODE.UNSHADED);
  assert.equal(resolveDisplayMode({ mode: "appearance" }), CAD_DISPLAY_MODE.RENDERED);
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
});

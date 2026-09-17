import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeStepClipSettings
} from "@hardcore/core/lib/viewer/clipPlane.js";
import {
  cloneThemePresetSettings,
  normalizeThemeSettings
} from "@hardcore/core/lib/themeSettings.js";
import {
  CAD_DISPLAY_MODE,
  normalizeDisplaySettings
} from "@hardcore/core/lib/displaySettings.js";
import {
  normalizeViewerRenderState
} from "./renderState.js";

test("viewer render-state normalization preserves current theme and display behavior", () => {
  const themeSettings = cloneThemePresetSettings("dark");
  const displaySettings = {
    mode: CAD_DISPLAY_MODE.WIREFRAME,
    clip: {
      enabled: true,
      axis: "z",
      offset: 0.4,
      invert: true
    }
  };
  const state = normalizeViewerRenderState({
    themeSettings,
    displaySettings
  });

  assert.deepEqual(state.themeSettings, normalizeThemeSettings(themeSettings));
  assert.deepEqual(state.displaySettings, normalizeDisplaySettings(displaySettings));
  assert.equal(state.displayMode, CAD_DISPLAY_MODE.WIREFRAME);
  assert.deepEqual(state.clipSettings, normalizeStepClipSettings({
    enabled: true,
    axis: "z",
    offset: 0.4,
    invert: true
  }));
});

test("viewer render-state normalization keeps viewer-side defaults local", () => {
  const state = normalizeViewerRenderState();

  assert.deepEqual(state.themeSettings, normalizeThemeSettings({}));
  assert.deepEqual(state.displaySettings, normalizeDisplaySettings(null));
  assert.equal(state.displayMode, "shaded_edges");
  assert.deepEqual(state.clipSettings, normalizeStepClipSettings(null));
});


test("Inspect edge visibility does not revive legacy custom outline styling", () => {
  const state = normalizeViewerRenderState({
    themeSettings: { edges: { color: "#28e2a3", thickness: 2.7, opacity: 0.6 } },
    displaySettings: { edges: { enabled: false, silhouette: true } },
  });
  const defaults = normalizeViewerRenderState({ displaySettings: { edges: { enabled: false, silhouette: true } } });
  assert.deepEqual(state.edgeSettings, defaults.edgeSettings);
  assert.equal(state.edgeSettings.enabled, false);
  assert.equal(state.edgeSettings.silhouette, true);
});

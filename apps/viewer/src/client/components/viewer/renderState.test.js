import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeStepClipSettings
} from "cadgen-js/lib/viewer/clipPlane.js";
import {
  cloneThemePresetSettings,
  normalizeThemeSettings
} from "cadgen-js/lib/themeSettings.js";
import {
  CAD_DISPLAY_MODE,
  normalizeDisplaySettings
} from "cadgen-js/lib/displaySettings.js";
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
  assert.equal(state.displayMode, "solid");
  assert.deepEqual(state.clipSettings, normalizeStepClipSettings(null));
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeStepClipSettings
} from "@text-to-cad/core/lib/viewer/clipPlane.js";
import {
  cloneThemePresetSettings,
  normalizeThemeSettings
} from "@text-to-cad/core/lib/themeSettings.js";
import {
  CAD_DISPLAY_MODE,
  normalizeDisplaySettings
} from "@text-to-cad/core/lib/displaySettings.js";
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
      at: 0.4,
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
    at: 0.4,
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

test("grouped View passes independent surface and edge choices through to the renderer", async () => {
  const { resolveViewSceneSettings } = await import('@text-to-cad/core/common/sceneSettings.js');
  // Each mode, and Preview's look over the file's display (`preview`).
  for (const [mode, preview] of [['solid'], ['shaded'], ['parts'], ['xray'], ['hidden-line'], ['wireframe'], ['solid', true]]) {
    const resolved = resolveViewSceneSettings({ preview, display: { mode, grid: true } });
    const normalized = normalizeViewerRenderState({ themeSettings: resolved.theme, displaySettings: resolved.display });
    assert.deepEqual(normalized.displaySettings.surfaces, resolved.view.surfaces);
    assert.equal(normalized.edgeSettings.enabled, resolved.view.edges.enabled);
    assert.equal(normalized.edgeSettings.color, resolved.view.edges.color);
    assert.equal(normalized.edgeSettings.depthTest, resolved.view.edges.visibility !== "all");
  }
});

// The parity page dresses a GLB, a mesh or a robot with the look the viewport would put on
// it (`headlessSceneDress`, from the job's resolved scene settings). The viewport resolves its
// look from the same settings AFTER normalizing them here, so this pins that the two routes to
// `resolveSceneSurfaceLook` land on one look for every preset, appearance and surface choice.
test("the viewport and the parity page resolve one surface look from one setting", async () => {
  const { resolveSceneSurfaceLook, resolveViewSceneSettings } = await import('@text-to-cad/core/common/sceneSettings.js');
  const { headlessSceneDress } = await import('@text-to-cad/core/common/headlessScene.js');
  const { EDGELESS_VIEW_FEATURES } = await import('@text-to-cad/core/common/viewSettings.js');
  // Solid and Parts, or Preview (asked for on its own, `preview`) with its own part colours.
  const features = { ...EDGELESS_VIEW_FEATURES, modes: ['solid', 'parts'] };
  const looks = [];
  for (const appearance of ['light', 'dark']) {
    for (const mode of ['solid', 'parts']) looks.push({ preview: false, display: { appearance, mode } });
    for (const parts of [undefined, { colorMode: 'by-part' }, { colorMode: 'single', color: '#ff8800' }]) {
      looks.push({ preview: true, display: { appearance }, previewSettings: parts ? { parts } : {} });
    }
  }
  looks.push({ preview: true, display: {}, previewSettings: { floor: { enabled: false } } });
  for (const { preview, display, previewSettings } of looks) {
    const scene = resolveViewSceneSettings({ display, preview, previewSettings, features });
    const viewport = normalizeViewerRenderState({ themeSettings: scene.theme, displaySettings: scene.display });
    const look = resolveSceneSurfaceLook({ themeSettings: viewport.themeSettings, displaySettings: viewport.displaySettings,
      renderMode: scene.render.enabled, renderConfiguration: scene.render.configuration });
    assert.deepEqual(look, headlessSceneDress(scene).look, JSON.stringify(display));
    assert.equal(headlessSceneDress(scene).receiveShadows, scene.view.lighting.enabled, JSON.stringify(display));
  }
});

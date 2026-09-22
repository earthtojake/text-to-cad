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

test("grouped View passes independent surface and edge choices through to the renderer", async () => {
  const { resolveViewSceneSettings } = await import('@hardcore/core/common/sceneSettings.js');
  for (const mode of ['solid', 'render', 'xray', 'hidden-line', 'wireframe']) {
    const resolved = resolveViewSceneSettings({ display: { mode,
      edges: { enabled: false, color: '#bada55', visibility: 'visible' },
      surfaces: { opacity: 0.4 } } });
    const normalized = normalizeViewerRenderState({ themeSettings: resolved.theme, displaySettings: resolved.display });
    assert.deepEqual(normalized.displaySettings.surfaces, resolved.view.surfaces);
    assert.equal(normalized.edgeSettings.enabled, false);
    assert.equal(normalized.edgeSettings.color, resolved.view.edges.color);
    assert.equal(normalized.edgeSettings.depthTest, true);
  }
});

// The snapshot CLI dresses a GLB, a mesh or a robot with the look the viewport would put on
// it (`headlessSceneDress`, from the job's resolved scene settings). The viewport resolves its
// look from the same settings AFTER normalizing them here, so this pins that the two routes to
// `resolveSceneSurfaceLook` land on one look for every preset, appearance and surface choice.
test("the viewport and the snapshot CLI resolve one surface look from one setting", async () => {
  const { resolveSceneSurfaceLook, resolveViewSceneSettings } = await import('@hardcore/core/common/sceneSettings.js');
  const { headlessSceneDress } = await import('@hardcore/core/common/headlessScene.js');
  const { EDGELESS_VIEW_FEATURES } = await import('@hardcore/core/common/viewSettings.js');
  const displays = [];
  for (const mode of ['solid', 'render']) for (const appearance of ['light', 'dark']) {
    for (const surfaces of [undefined, { colorMode: 'by-part' }, { colorMode: 'single', color: '#ff8800' }, { style: 'flat', opacity: 0.5 }]) {
      displays.push({ mode, appearance, ...(surfaces ? { surfaces } : {}) });
    }
  }
  displays.push({ mode: 'solid', floor: { enabled: true } }, { mode: 'render', lighting: { enabled: false } });
  for (const display of displays) {
    const scene = resolveViewSceneSettings({ display, features: EDGELESS_VIEW_FEATURES });
    const viewport = normalizeViewerRenderState({ themeSettings: scene.theme, displaySettings: scene.display });
    const look = resolveSceneSurfaceLook({ themeSettings: viewport.themeSettings, displaySettings: viewport.displaySettings,
      renderMode: scene.render.enabled, renderConfiguration: scene.render.configuration });
    assert.deepEqual(look, headlessSceneDress(scene).look, JSON.stringify(display));
    assert.equal(headlessSceneDress(scene).receiveShadows, scene.view.lighting.enabled, JSON.stringify(display));
  }
});

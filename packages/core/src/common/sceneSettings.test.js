import assert from "node:assert/strict";
import test from "node:test";

import {
  SCENE_QUALITY,
  resolveDisplayMaterialSettings,
  resolveRenderQuality,
  resolveViewSceneSettings
} from "./sceneSettings.js";
import { PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS } from "./photographicStudioRig.js";

test("normal CAD stays an orthographic responsive inspection scene", () => {
  const light = resolveViewSceneSettings({ appearance: "light" });
  const dark = resolveViewSceneSettings({ appearance: "dark" });

  assert.equal(light.render.enabled, false);
  assert.equal(light.render.configuration, null);
  assert.equal(light.camera.projection, "orthographic");
  assert.equal(light.display.mode, "shaded_edges");
  assert.equal(light.theme.materials.overrideSourceColors, false);
  assert.equal(light.materialOverrides, null);
  assert.equal(dark.materialOverrides, null);
  assert.equal(light.quality.id, SCENE_QUALITY.INTERACTIVE);
  assert.equal(light.theme.background.solidColor, "#f0f4f9");
  assert.equal(dark.theme.background.solidColor, "#25272b");
  assert.deepEqual(dark.theme.materials, light.theme.materials);
  assert.deepEqual(dark.theme.lighting, light.theme.lighting);
  assert.deepEqual(dark.theme.environment, light.theme.environment);
});

test("Render quality maps to the existing bounded scene-quality ladder", () => {
  assert.equal(resolveRenderQuality("preview").id, SCENE_QUALITY.STANDARD);
  assert.equal(resolveRenderQuality("final").id, SCENE_QUALITY.HIGH);
  assert.equal(resolveRenderQuality().id, SCENE_QUALITY.HIGH);
  assert.throws(() => resolveRenderQuality("high"), /Unknown render quality/);
});

test("the studio's finish is a constant of the rig, with no colour grading", () => {
  assert.equal(PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS.overrideSourceColors, false);
  for (const channel of ["saturation", "contrast", "brightness"]) {
    assert.equal(Object.hasOwn(PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS, channel), false);
  }
});

test("part-color policy stays display-owned and preserves its editable palette", () => {
  const byPart = resolveViewSceneSettings({ display: { mode: "parts" } });
  assert.equal(byPart.theme.materials.overrideSourceColors, true);
  assert.equal(byPart.theme.materials.cycleColors, true);
  assert.deepEqual(byPart.theme.materials.fillColors, byPart.view.surfaces.colors);

  assert.deepEqual(resolveDisplayMaterialSettings(
    { defaultColor: "#ffffff", overrideSourceColors: false },
    { mode: "single", color: "#123456" }
  ), {
    defaultColor: "#123456",
    fillColors: ["#123456"],
    cycleColors: false,
    overrideSourceColors: true
  });
  assert.deepEqual(resolveDisplayMaterialSettings({}, { mode: "by_part", colors: ["#112233", "#abcdef"] }), {
    defaultColor: "#112233",
    fillColors: ["#112233", "#abcdef"],
    cycleColors: true,
    overrideSourceColors: true
  });
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  SCENE_QUALITY,
  normalizeRenderPayload,
  resolveDisplayMaterialSettings,
  resolveRenderConfiguration,
  resolveRenderQuality,
  resolveSceneSettings
} from "./sceneSettings.js";

test("normal CAD stays an orthographic responsive inspection scene", () => {
  const light = resolveSceneSettings({ appearance: "light" });
  const dark = resolveSceneSettings({ appearance: "dark" });

  assert.equal(light.render.enabled, false);
  assert.equal(light.camera.projection, "orthographic");
  assert.equal(light.display.mode, "shaded_edges");
  assert.equal(light.display.guides.grid.enabled, true);
  assert.equal(light.display.guides.axis.enabled, true);
  assert.equal(light.render.settings.materials.overrideSourceColors, false);
  assert.equal(light.quality.id, SCENE_QUALITY.INTERACTIVE);
  assert.equal(light.render.settings.background.solidColor, "#f0f4f9");
  assert.equal(dark.render.settings.background.solidColor, "#333333");
  assert.deepEqual(dark.render.settings.materials, light.render.settings.materials);
  assert.deepEqual(dark.render.settings.lighting, light.render.settings.lighting);
  assert.deepEqual(dark.render.settings.environment, light.render.settings.environment);
});

test("omitted Render fields stay sparse while configuration expands effective defaults", () => {
  assert.deepEqual(normalizeRenderPayload({}), {});

  const light = resolveSceneSettings({ appearance: "light", render: {} });
  const dark = resolveSceneSettings({ appearance: "dark", render: {} });
  assert.deepEqual(light.render.payload, {});
  assert.deepEqual(light.render.configuration, {
    studio: "light",
    quality: "final",
    exposure: 0,
    lighting: { rotation: 0, size: 1, fill: 0.25 },
    backdrop: { color: "#e7e7e5", transparent: false, ground: true, groundPlacement: "origin" }
  });
  assert.equal(dark.render.configuration.studio, "dark");
  assert.equal(dark.render.configuration.backdrop.color, "#121315");
  assert.equal(Object.hasOwn(light.render.payload, "studio"), false);
  assert.equal(light.camera.projection, "perspective");
  assert.equal(light.camera.focalLength, 50);
  assert.equal(light.display.mode, "shaded");
  assert.equal(light.display.guides.grid.enabled, false);
  assert.equal(light.quality.id, SCENE_QUALITY.HIGH);
});

test("explicit studios pin only the backdrop default", () => {
  const pinned = resolveSceneSettings({ appearance: "dark", render: { studio: "light" } });
  assert.equal(pinned.appearance, "dark");
  assert.equal(pinned.render.payload.studio, "light");
  assert.equal(pinned.render.configuration.studio, "light");
  assert.equal(pinned.render.configuration.backdrop.color, "#e7e7e5");

  const custom = resolveRenderConfiguration({
    studio: "dark",
    exposure: 1.5,
    lighting: { rotation: -45, size: 2, fill: 0 },
    backdrop: { color: "#123456", transparent: true, ground: false, groundPlacement: "lowest" }
  }, "light");
  assert.deepEqual(custom, {
    studio: "dark",
    quality: "final",
    exposure: 1.5,
    lighting: { rotation: -45, size: 2, fill: 0 },
    backdrop: { color: "#123456", transparent: true, ground: false, groundPlacement: "lowest" }
  });
});

test("Render quality maps to the existing bounded scene-quality ladder", () => {
  assert.equal(resolveRenderQuality("preview").id, SCENE_QUALITY.STANDARD);
  assert.equal(resolveRenderQuality("final").id, SCENE_QUALITY.HIGH);
  assert.equal(resolveRenderQuality().id, SCENE_QUALITY.HIGH);

  const preview = resolveSceneSettings({ render: { quality: "preview" } });
  assert.equal(preview.render.payload.quality, "preview");
  assert.equal(preview.render.configuration.quality, "preview");
  assert.equal(preview.quality.id, SCENE_QUALITY.STANDARD);
});

test("Render uses a fixed neutral photographic engine policy without authored PBR overrides", () => {
  const light = resolveSceneSettings({ render: { studio: "light", exposure: -1 } });
  const dark = resolveSceneSettings({ render: { studio: "dark", exposure: -1 } });

  assert.deepEqual(light.render.materialOverrides, {});
  assert.equal(light.render.settings.materials.overrideSourceColors, false);
  assert.equal(light.render.settings.materials.saturation, 1);
  assert.equal(light.render.settings.materials.contrast, 1);
  assert.equal(light.render.settings.materials.brightness, 1);
  assert.deepEqual(light.render.settings.materials, dark.render.settings.materials);
  assert.deepEqual(light.render.settings.lighting, dark.render.settings.lighting);
  assert.equal(light.render.settings.floor.mode, "none");
  assert.equal(light.render.settings.lighting.directional.enabled, false);
  assert.equal(light.render.settings.lighting.ambient.enabled, false);
  assert.deepEqual(light.render.settings.renderer, { toneMapping: "neutral", exposure: -1 });
});

test("Render camera, quality, and display are isolated from hostile CAD overrides", () => {
  const baseline = resolveSceneSettings({
    render: {
      camera: { preset: "top", projection: "orthographic", focalLength: 85 }
    }
  });
  const hostile = resolveSceneSettings({
    render: {
      camera: { preset: "top", projection: "orthographic", focalLength: 85 }
    },
    camera: { preset: "front", projection: "perspective", focalLength: 20 },
    quality: "interactive",
    display: {
      mode: "wireframe",
      clip: { enabled: true },
      exploded: { enabled: true, amount: 1 },
      guides: { grid: { enabled: true }, axis: { enabled: true } },
      partColor: { mode: "single", color: "#ff0000" }
    }
  });

  assert.deepEqual(hostile, baseline);
  assert.equal(hostile.camera.preset, "top");
  assert.equal(hostile.camera.focalLength, 85);
  assert.equal(hostile.display.mode, "shaded");
  assert.equal(hostile.display.guides.grid.enabled, false);
  assert.equal(hostile.display.partColor.mode, "original");
  assert.equal(hostile.quality.id, "high");
});

test("Render camera payload preserves a reusable photographic pose and lens", () => {
  const copiedPose = {
    position: [10, 20, 30],
    target: [1, 2, 3],
    up: [0, 0, 1],
    zoom: 1.4,
    focalLength: 72
  };
  const resolved = resolveSceneSettings({ render: { camera: copiedPose } });
  assert.equal(resolved.camera.focalLength, 72);
  assert.deepEqual(resolved.camera.position, copiedPose.position);
  assert.deepEqual(resolved.camera.target, copiedPose.target);
});

test("part-color policy stays display-owned and preserves its editable palette", () => {
  const single = resolveSceneSettings({
    display: { partColor: { mode: "single", color: "#123456" } }
  });
  const byPart = resolveSceneSettings({
    display: { partColor: { mode: "by_part", colors: ["#112233", "#abcdef"] } }
  });

  assert.equal(single.render.settings.materials.overrideSourceColors, true);
  assert.deepEqual(single.render.settings.materials.fillColors, ["#123456"]);
  assert.equal(single.render.settings.materials.cycleColors, false);
  assert.deepEqual(byPart.render.settings.materials.fillColors, ["#112233", "#abcdef"]);
  assert.equal(byPart.render.settings.materials.cycleColors, true);
  assert.deepEqual(resolveDisplayMaterialSettings(
    { defaultColor: "#ffffff", overrideSourceColors: false },
    { mode: "single", color: "#123456" }
  ), {
    defaultColor: "#123456",
    fillColors: ["#123456"],
    cycleColors: false,
    overrideSourceColors: true
  });
});

test("Render validation rejects old and malformed fields with generic schema errors", () => {
  const invalid = [
    [{ settings: {} }, /Unsupported render fields: settings/],
    [{ appearance: "dark" }, /Unsupported render fields: appearance/],
    [{ studio: "studio-light" }, /Unknown render studio/],
    [{ quality: "high" }, /Unknown render quality/],
    [{ exposure: "1" }, /render\.exposure must be a finite number/],
    [{ exposure: 6 }, /render\.exposure must be a finite number/],
    [{ lighting: { rotation: 181 } }, /render\.lighting\.rotation/],
    [{ lighting: { size: 0 } }, /render\.lighting\.size/],
    [{ lighting: { fill: true } }, /render\.lighting\.fill/],
    [{ lighting: { key: 2 } }, /Unsupported render\.lighting fields: key/],
    [{ backdrop: { color: "red" } }, /render\.backdrop\.color must be a hex color/],
    [{ backdrop: { transparent: 1 } }, /render\.backdrop\.transparent must be a boolean/],
    [{ backdrop: { groundPlacement: "auto" } }, /render\.backdrop\.groundPlacement must be origin or lowest/],
    [{ backdrop: { floor: true } }, /Unsupported render\.backdrop fields: floor/],
    [{ camera: { focalLength: 19 } }, /camera\.focalLength/],
    [{ display: {} }, /Unsupported render fields: display/]
  ];
  for (const [render, pattern] of invalid) {
    assert.throws(() => normalizeRenderPayload(render), pattern);
    try {
      normalizeRenderPayload(render);
    } catch (error) {
      assert.doesNotMatch(error.message, /removed|migrat|instead|use /i);
    }
  }
});

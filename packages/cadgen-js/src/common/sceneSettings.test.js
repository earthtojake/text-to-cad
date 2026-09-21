import assert from "node:assert/strict";
import test from "node:test";

import {
  SCENE_QUALITY,
  normalizeRenderPayload,
  resolveDisplayMaterialSettings,
  resolveRenderQuality,
  resolveSceneSettings
} from "./sceneSettings.js";
import { PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS } from "./photographicStudioRig.js";

test("normal CAD stays an orthographic responsive inspection scene", () => {
  const light = resolveSceneSettings({ appearance: "light" });
  const dark = resolveSceneSettings({ appearance: "dark" });

  assert.equal(light.render.enabled, false);
  assert.equal(light.render.configuration, null);
  assert.equal(light.camera.projection, "orthographic");
  assert.equal(light.display.mode, "shaded_edges");
  assert.equal(light.display.guides.grid.enabled, true);
  assert.equal(light.display.guides.axis.enabled, true);
  assert.equal(light.theme.materials.overrideSourceColors, false);
  assert.equal(light.quality.id, SCENE_QUALITY.INTERACTIVE);
  assert.equal(light.theme.background.solidColor, "#f0f4f9");
  assert.equal(dark.theme.background.solidColor, "#333333");
  assert.deepEqual(dark.theme.materials, light.theme.materials);
  assert.deepEqual(dark.theme.lighting, light.theme.lighting);
  assert.deepEqual(dark.theme.environment, light.theme.environment);
});

test("omitted Render fields stay sparse while configuration expands effective defaults", () => {
  assert.deepEqual(normalizeRenderPayload({}), {});

  const light = resolveSceneSettings({ appearance: "light", render: {} });
  const dark = resolveSceneSettings({ appearance: "dark", render: {} });
  assert.deepEqual(light.render.payload, {});
  const { camera, ...envelope } = light.render.configuration;
  assert.deepEqual(envelope, {
    studio: "light",
    quality: "final",
    exposure: 0,
    lighting: { rotation: 0, size: 1, fill: 0.25 },
    backdrop: { color: "#e7e7e5", transparent: false, ground: true, groundPlacement: "lowest" }
  });
  // The recipe carries the Render camera, and it is the scene's camera.
  assert.equal(camera.projection, "perspective");
  assert.equal(camera.focalLength, 50);
  assert.deepEqual(light.camera, camera);
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

  const { camera: _camera, ...custom } = resolveSceneSettings({
    appearance: "light",
    render: {
      studio: "dark",
      exposure: 1.5,
      lighting: { rotation: -45, size: 2, fill: 0 },
      backdrop: { color: "#123456", transparent: true, ground: false, groundPlacement: "lowest" }
    }
  }).render.configuration;
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

test("Render resolves a recipe and no CAD scene settings at all", () => {
  const light = resolveSceneSettings({ render: { studio: "light", exposure: -1 } });
  const dark = resolveSceneSettings({ render: { studio: "dark", exposure: -1 } });

  // No theme means no way to reach the CAD lighting rig, stage floor or
  // background gradients from Render — not a theme that disables them.
  assert.equal(light.theme, null);
  assert.equal(light.materialOverrides, null);
  assert.equal(light.render.configuration.exposure, -1);
  assert.equal(
    Object.keys(light.render.configuration).sort().join(","),
    "backdrop,camera,exposure,lighting,quality,studio"
  );
  // The two studios differ only in their backdrop default.
  assert.notEqual(light.render.configuration.backdrop.color, dark.render.configuration.backdrop.color);
  assert.deepEqual(
    { ...light.render.configuration, studio: null, backdrop: null },
    { ...dark.render.configuration, studio: null, backdrop: null }
  );
  // The studio's finish is a constant of the rig, with no colour grading.
  assert.equal(PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS.overrideSourceColors, false);
  for (const channel of ["saturation", "contrast", "brightness"]) {
    assert.equal(Object.hasOwn(PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS, channel), false);
  }
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

  assert.equal(single.theme.materials.overrideSourceColors, true);
  assert.deepEqual(single.theme.materials.fillColors, ["#123456"]);
  assert.equal(single.theme.materials.cycleColors, false);
  assert.deepEqual(byPart.theme.materials.fillColors, ["#112233", "#abcdef"]);
  assert.equal(byPart.theme.materials.cycleColors, true);
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

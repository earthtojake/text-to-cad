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
  assert.equal(light.materialOverrides, null);
  assert.equal(dark.materialOverrides, null);
  assert.equal(light.quality.id, SCENE_QUALITY.INTERACTIVE);
  assert.equal(light.theme.background.solidColor, "#f0f4f9");
  assert.equal(dark.theme.background.solidColor, "#333333");
  assert.deepEqual(dark.theme.materials, light.theme.materials);
  assert.deepEqual(dark.theme.lighting, light.theme.lighting);
  assert.deepEqual(dark.theme.environment, light.theme.environment);
});

test("legacy supplied themes cannot alter the fixed Inspect or Render scene bases", () => {
  const legacy = {
    ...resolveSceneSettings({ appearance: "light" }).theme,
    projection: "perspective",
    background: { solidColor: "#123456" },
    materials: { roughness: 0.7 },
    floor: { reflectivity: 0.33 },
    edges: { color: "#ff6600" }
  };
  assert.deepEqual(
    resolveSceneSettings({ appearance: "light", theme: legacy }),
    resolveSceneSettings({ appearance: "light" })
  );
  assert.deepEqual(
    resolveSceneSettings({ appearance: "dark", display: { mode: "render" }, theme: legacy }),
    resolveSceneSettings({ appearance: "dark", display: { mode: "render" } })
  );
});

test("omitted Render fields stay sparse while configuration expands effective defaults", () => {
  assert.deepEqual(normalizeRenderPayload({}), {});

  const light = resolveSceneSettings({ appearance: "light", display: { mode: "render" } });
  const dark = resolveSceneSettings({ appearance: "dark", display: { mode: "render" } });
  assert.deepEqual(light.render.payload, {});
  const { camera, ...envelope } = light.render.configuration;
  assert.deepEqual(envelope, {
    studio: "light",
    quality: "final",
    exposure: 0,
    lighting: { rotation: 0, size: 1, fill: 0.25 },
    backdrop: { color: "#ffffff", transparent: false, ground: true, groundPlacement: "origin", groundColor: "#e7e7e5", groundOpacity: 0.6 }
  });
  assert.equal(camera.projection, "orthographic");
  assert.deepEqual(light.camera, camera);
  assert.equal(dark.render.configuration.studio, "dark");
  assert.equal(dark.render.configuration.backdrop.color, "#121315");
  assert.equal(Object.hasOwn(light.render.payload, "studio"), false);
  assert.equal(light.camera.projection, "orthographic");
  assert.equal(light.display.mode, "render");
  assert.equal(light.quality.id, SCENE_QUALITY.HIGH);
});

test("explicit studios pin only the backdrop default", () => {
  const pinned = resolveSceneSettings({ appearance: "dark", display: { mode: "render", render: { studio: "light" } } });
  assert.equal(pinned.appearance, "dark");
  assert.equal(pinned.render.payload.studio, "light");
  assert.equal(pinned.render.configuration.studio, "light");
  assert.equal(pinned.render.configuration.backdrop.color, "#ffffff");

  const { camera: _camera, ...custom } = resolveSceneSettings({
    appearance: "light",
    display: { mode: "render", render: {
      studio: "dark", exposure: 1.5,
      lighting: { rotation: -45, size: 2, fill: 0 },
      backdrop: { color: "#123456", transparent: true, ground: false, groundPlacement: "lowest" }
    } }
  }).render.configuration;
  assert.deepEqual(custom, {
    studio: "dark",
    quality: "final",
    exposure: 1.5,
    lighting: { rotation: -45, size: 2, fill: 0 },
    backdrop: { color: "#123456", transparent: true, ground: false, groundPlacement: "lowest", groundColor: "#123456", groundOpacity: 0.6 }
  });
});

test("Render quality maps to the existing bounded scene-quality ladder", () => {
  assert.equal(resolveRenderQuality("preview").id, SCENE_QUALITY.STANDARD);
  assert.equal(resolveRenderQuality("final").id, SCENE_QUALITY.HIGH);
  assert.equal(resolveRenderQuality().id, SCENE_QUALITY.HIGH);

  const preview = resolveSceneSettings({ display: { mode: "render", render: { quality: "preview" } } });
  assert.equal(preview.render.payload.quality, "preview");
  assert.equal(preview.render.configuration.quality, "preview");
  assert.equal(preview.quality.id, SCENE_QUALITY.STANDARD);
});

test("Render resolves a recipe and no CAD scene settings at all", () => {
  const light = resolveSceneSettings({ display: { mode: "render", render: { studio: "light", exposure: -1 } } });
  const dark = resolveSceneSettings({ display: { mode: "render", render: { studio: "dark", exposure: -1 } } });

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

test("Render uses the common reusable camera pose and lens", () => {
  const copiedPose = {
    position: [10, 20, 30],
    target: [1, 2, 3],
    up: [0, 0, 1],
    zoom: 1.4,
    focalLength: 72
  };
  const resolved = resolveSceneSettings({ camera: copiedPose, display: { mode: "render" } });
  assert.equal(resolved.camera.focalLength, 72);
  assert.deepEqual(resolved.camera.position, copiedPose.position);
  assert.deepEqual(resolved.camera.target, copiedPose.target);
});

test("unified render display preserves the common orthographic camera and inspection display", () => {
  const resolved = resolveSceneSettings({
    appearance: "dark",
    camera: {
      preset: "front",
      projection: "orthographic",
      orthographicHalfHeight: 24,
      zoom: 1.25
    },
    display: {
      mode: "render",
      render: { studio: "dark", exposure: 1 },
      clip: { enabled: true, axis: "z", offsets: { z: 0.4 } },
      exploded: { enabled: true, amount: 0.6 },
      guides: { grid: { enabled: true }, axis: { enabled: false } },
      partColor: { mode: "single", color: "#123456" }
    }
  });

  assert.equal(resolved.render.enabled, true);
  assert.equal(resolved.camera.projection, "orthographic");
  assert.equal(resolved.camera.orthographicHalfHeight, 24);
  assert.deepEqual(resolved.render.configuration.camera, resolved.camera);
  assert.equal(resolved.display.mode, "render");
  assert.equal(resolved.display.clip.enabled, true);
  assert.equal(resolved.display.exploded.amount, 0.6);
  assert.equal(resolved.display.guides.grid.enabled, true);
  assert.equal(resolved.display.partColor.mode, "single");
  assert.equal(resolved.render.configuration.exposure, 1);
});

test("render display without an explicit camera retains the normal orthographic view", () => {
  const resolved = resolveSceneSettings({ display: { mode: "render" } });
  assert.equal(resolved.camera.projection, "orthographic");
  assert.equal(resolved.camera.preset, "iso");
  assert.equal(resolved.render.configuration.camera.projection, "orthographic");
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
    [{ backdrop: { groundColor: "blue" } }, /render\.backdrop\.groundColor must be a hex color/],
    [{ backdrop: { groundOpacity: 1.1 } }, /render\.backdrop\.groundOpacity must be a finite number/],
    [{ backdrop: { transparent: 1 } }, /render\.backdrop\.transparent must be a boolean/],
    [{ backdrop: { groundPlacement: "auto" } }, /render\.backdrop\.groundPlacement must be origin or lowest/],
    [{ backdrop: { floor: true } }, /Unsupported render\.backdrop fields: floor/],
    [{ camera: { focalLength: 19 } }, /Unsupported render fields: camera/],
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


test("explicit floor appearance survives sparse resolution independently of background", () => {
  const render = { backdrop: { groundColor: "#123456", groundOpacity: 0 } };
  const resolved = resolveSceneSettings({ appearance: "dark", display: { mode: "render", render } });
  assert.deepEqual(resolved.render.payload, render);
  assert.equal(resolved.render.configuration.backdrop.groundColor, "#123456");
  assert.equal(resolved.render.configuration.backdrop.groundOpacity, 0);
  assert.equal(resolved.render.configuration.backdrop.color, "#121315");
});

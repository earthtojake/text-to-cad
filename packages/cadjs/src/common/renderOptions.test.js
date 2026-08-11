import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import {
  cloneThemeSettings,
  normalizeThemeSettings,
  resolveThemeSettingsForColorMode
} from "./themeSettings.js";
import {
  addFloor,
  createSharedRenderOptions,
  RENDER_SCENE_SCALE,
  boundsFromVertices,
  centerAndRadiusFromBounds,
  fitOrthographicCamera,
  frameHalfHeightForView,
  framePadding,
  inferRenderSceneScale,
  outputSize,
  resolveRenderView,
  resolveThemeJobConfig,
  resolveThemeSettings
} from "./renderOptions.js";

const SCALE_SETTINGS = Object.freeze({
  [RENDER_SCENE_SCALE.CAD]: Object.freeze({
    minBoundsSpan: 1,
    minModelRadius: 1,
    minFloorSize: 100,
    minCameraDistance: 10,
    minCameraFar: 1000
  }),
  [RENDER_SCENE_SCALE.URDF]: Object.freeze({
    minBoundsSpan: 0.05,
    minModelRadius: 0.05,
    minFloorSize: 0.05,
    minCameraDistance: 0.5,
    minCameraFar: 10
  })
});

function assertClose(actual, expected, epsilon = 1e-6) {
  assert.ok(Math.abs(actual - expected) <= epsilon, `${actual} !== ${expected}`);
}

test("shared render options preserve explicit caller-owned values without defaults", () => {
  const options = createSharedRenderOptions({
    displayMode: "wireframe",
    background: false,
    renderScale: 0
  });

  assert.equal(options.themeSettings, null);
  assert.equal(options.display, null);
  assert.equal(Object.hasOwn(options, "displayMode"), false);
  assert.equal(options.background, false);
  assert.equal(options.renderScale, 0);
});

test("theme resolution uses saved theme ids or direct theme settings", () => {
  assert.deepEqual(
    resolveThemeSettings({}, { defaultThemeId: "workbench" }),
    normalizeThemeSettings(cloneThemeSettings("workbench"))
  );
  assert.deepEqual(
    resolveThemeSettings({ theme: "dark" }, { defaultThemeId: "workbench" }),
    resolveThemeSettingsForColorMode(cloneThemeSettings("dark"), { prefersDark: false })
  );
  assert.deepEqual(
    resolveThemeJobConfig({
      theme: {
        materials: { defaultColor: "#123456" }
      }
    }, { defaultThemeId: "workbench" }),
    {
      themeId: "workbench",
      settings: { materials: { defaultColor: "#123456" } }
    }
  );
});

test("view presets and azimuth/elevation camera parsing remain stable", () => {
  const top = resolveRenderView("top");
  assert.equal(top.name, "top");
  assert.deepEqual(top.direction, [0, 0, 1]);
  assert.deepEqual(top.up, [0, 1, 0]);

  const custom = resolveRenderView("45:30");
  assert.equal(custom.name, "45:30");
  assertClose(custom.direction[0], Math.SQRT1_2 * Math.cos(Math.PI / 6));
  assertClose(custom.direction[1], -Math.SQRT1_2 * Math.cos(Math.PI / 6));
  assertClose(custom.direction[2], 0.5);
});

test("scene scale inference, bounds, and camera framing are policy-free helpers", () => {
  assert.equal(inferRenderSceneScale({ explicit: "urdf" }), RENDER_SCENE_SCALE.URDF);
  assert.equal(inferRenderSceneScale({ kind: "sdf" }), RENDER_SCENE_SCALE.URDF);
  assert.equal(inferRenderSceneScale({ parts: [{ linkName: "base_link" }] }), RENDER_SCENE_SCALE.URDF);
  assert.equal(inferRenderSceneScale({ kind: "glb", parts: [] }), RENDER_SCENE_SCALE.CAD);

  const bounds = boundsFromVertices(new Float32Array([0, 0, 0, 2, 4, 6]));
  assert.deepEqual(bounds, { min: [0, 0, 0], max: [2, 4, 6] });

  const { center, radius } = centerAndRadiusFromBounds(bounds, RENDER_SCENE_SCALE.CAD, SCALE_SETTINGS);
  assert.deepEqual(center.toArray(), [1, 2, 3]);
  assertClose(radius, Math.sqrt(56) / 2);

  const view = resolveRenderView("iso");
  const halfHeight = frameHalfHeightForView(view, bounds, 800, 600, 0.12, RENDER_SCENE_SCALE.CAD, SCALE_SETTINGS);
  assert.ok(halfHeight > 0);

  const camera = new THREE.OrthographicCamera();
  fitOrthographicCamera(camera, view, bounds, 800, 600, {
    padding: 0.12,
    sceneScale: RENDER_SCENE_SCALE.CAD,
    settingsByScale: SCALE_SETTINGS
  });
  assertClose(camera.top, halfHeight);
  assertClose(camera.bottom, -halfHeight);
  assertClose(camera.left, -halfHeight * (800 / 600));
  assertClose(camera.right, halfHeight * (800 / 600));
  assert.equal(camera.near, 0.01);
  assert.equal(camera.far >= 1000, true);
});

test("output sizing and padding helpers preserve snapshot fallback semantics", () => {
  assert.deepEqual(outputSize({}, {}), { width: 1400, height: 900 });
  assert.deepEqual(outputSize({ width: 320, height: 240 }, { width: 1400, height: 900 }), { width: 320, height: 240 });
  assert.deepEqual(outputSize({}, { width: 1600, height: 1200 }), { width: 1600, height: 1200 });
  assert.equal(framePadding({}), 0.04);
  assert.equal(framePadding({ render: { padding: 0 } }), 0);
  assert.equal(framePadding({ render: { padding: 0.02 } }), 0.02);
  assert.equal(framePadding({ render: { padding: -0.02 } }), 0);
  assert.equal(framePadding({ paddingPercent: 0.25 }), 0.15);
  assert.equal(framePadding({ render: { paddingPercent: 0.13 } }), 0.13);
});

test("grid floors use theme line opacity and density for snapshots", () => {
  const scene = new THREE.Scene();
  addFloor(
    scene,
    { min: [0, 0, 0], max: [10, 10, 10] },
    normalizeThemeSettings({
      floor: {
        mode: "grid",
        gridCenterColor: "#123456",
        gridCellColor: "#abcdef",
        gridOpacity: 0.37,
        gridDensity: 2
      }
    }),
    RENDER_SCENE_SCALE.CAD,
    SCALE_SETTINGS
  );

  const grid = scene.children[0];
  const materials = Array.isArray(grid.material) ? grid.material : [grid.material];
  assert.equal(grid.type, "GridHelper");
  assert.equal(grid.geometry.getAttribute("position").count, 4 * (56 + 1));
  assert.equal(materials[0].opacity, 0.37);
  assert.equal(materials[0].transparent, true);
  assert.equal(materials[0].depthWrite, false);
});

test("snapshot floors render grid independently from the stage floor", () => {
  const scene = new THREE.Scene();
  addFloor(
    scene,
    { min: [0, 0, 0], max: [10, 10, 10] },
    normalizeThemeSettings({
      floor: {
        mode: "stage",
        enabled: true,
        color: "#ddeeff",
        shadowOpacity: 0.25,
        grid: {
          enabled: true,
          centerColor: "#123456",
          cellColor: "#abcdef",
          opacity: 0.37,
          density: 2
        }
      }
    }),
    RENDER_SCENE_SCALE.CAD,
    SCALE_SETTINGS
  );

  const grid = scene.children.find((child) => child.type === "GridHelper");
  const plane = scene.children.find((child) => child.type === "Mesh");
  const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material];

  assert.ok(grid);
  assert.ok(plane);
  assert.equal(gridMaterials[0].opacity, 0.37);
  assert.equal(plane.receiveShadow, true);
  assert.equal(plane.material.opacity, 0.25);
});

test("resolveThemeSettings applies colorMode to object themes", () => {
  // colorMode was previously honoured only for saved-theme-id STRINGS, which
  // made it an accepted-but-inert key in theme JSON: "light" and "dark"
  // produced byte-identical renders.
  const base = normalizeThemeSettings(cloneThemeSettings("workbench"));
  const withModes = {
    ...base,
    modeColors: {
      light: { background: { solidColor: "#ffffff" } },
      dark: { background: { solidColor: "#000000" } }
    }
  };

  const light = resolveThemeSettings({
    theme: { ...withModes, colorMode: "light" }
  });
  const dark = resolveThemeSettings({
    theme: { ...withModes, colorMode: "dark" }
  });

  assert.equal(light.background.solidColor, "#ffffff");
  assert.equal(dark.background.solidColor, "#000000");
});

test("resolveThemeSettings is the identity for settings without modeColors", () => {
  // The safety property of applying colorMode unconditionally: when no explicit
  // modeColors block is supplied, normalizeThemeModeColors derives it from the
  // settings themselves, so re-applying it must not alter anything.
  const settings = normalizeThemeSettings(cloneThemeSettings("workbench"));
  const explicit = { ...settings, background: { ...settings.background, solidColor: "#123456" } };
  delete explicit.modeColors;

  const resolved = resolveThemeSettings({ theme: explicit });

  assert.equal(resolved.background.solidColor, "#123456");
});

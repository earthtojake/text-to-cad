import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";
import { THEME_FLOOR_MODES } from "../themeSettings.js";
import { VIEWER_SCENE_SCALE } from "./sceneScale.js";
import {
  applySceneBackground,
  BASE_VIEWER_THEME,
  createSafeColor,
  createStageFloorGlowPlane,
  createStageFloorPlane,
  createStageShadowPlane,
  getViewerThemeNumber,
  getViewerThemeValue,
  getStageFloorSize,
  normalizeFloorMode,
  normalizeGradientStops,
  resolveFloorMode,
  resolveStageFloorGlassFactor,
  resolveWireframeEdgeColor,
  updateSpotLightTarget
} from "./stageTheme.js";

const EPSILON = 1e-6;

function assertNear(actual, expected, message = "") {
  assert.ok(Math.abs(actual - expected) < EPSILON, `${message} expected ${expected}, received ${actual}`);
}

test("stage theme helpers normalize floor modes, theme values, and gradient stops", () => {
  assert.equal(normalizeFloorMode("glass"), THEME_FLOOR_MODES.STAGE);
  assert.equal(normalizeFloorMode("grid"), THEME_FLOOR_MODES.GRID);
  assert.equal(normalizeFloorMode("unknown", THEME_FLOOR_MODES.NONE), THEME_FLOOR_MODES.NONE);
  assert.equal(resolveFloorMode({ mode: "none" }), THEME_FLOOR_MODES.NONE);
  assert.equal(getViewerThemeValue({ edge: "#123456" }, "edge", "#ffffff"), "#123456");
  assert.equal(getViewerThemeValue({}, "edge", "#ffffff"), BASE_VIEWER_THEME.edge);
  assert.equal(getViewerThemeNumber({ edgeThickness: "2.5" }, "edgeThickness", 1), 2.5);
  assert.equal(getViewerThemeNumber({ edgeThickness: "bad" }, "edgeThickness", 1), 1);

  assert.deepEqual(normalizeGradientStops(["#fff", { offset: 0.25, color: "#000" }]), [
    { offset: 0, color: "#fff" },
    { offset: 0.25, color: "#000" }
  ]);
});

test("stage color and floor sizing helpers preserve rendering defaults", () => {
  const fallback = createSafeColor(THREE, "not-a-color", "#112233");
  assert.equal(fallback.getHexString(), "112233");

  assertNear(resolveStageFloorGlassFactor({
    materials: {
      roughness: 0.2,
      clearcoat: 0.6,
      envMapIntensity: 2
    },
    environment: {
      enabled: true,
      intensity: 1.5
    }
  }), 0.85, "glass factor");

  assert.equal(getStageFloorSize(0.25, VIEWER_SCENE_SCALE.URDF), 40);
  assert.equal(getStageFloorSize(2, VIEWER_SCENE_SCALE.CAD), 22400);
});

test("wireframe edge color uses contrast-safe colors on dark and light backgrounds", () => {
  assert.equal(resolveWireframeEdgeColor({
    edgeColor: "#132232",
    themeSettings: {
      background: {
        type: "solid",
        solidColor: "#09090b"
      }
    },
    viewerTheme: BASE_VIEWER_THEME
  }), "#dbeafe");

  assert.equal(resolveWireframeEdgeColor({
    edgeColor: "#66ff99",
    themeSettings: {
      background: {
        type: "solid",
        solidColor: "#09090b"
      }
    },
    viewerTheme: BASE_VIEWER_THEME
  }), "#66ff99");

  assert.equal(resolveWireframeEdgeColor({
    edgeColor: "#dbeafe",
    themeSettings: {
      background: {
        type: "solid",
        solidColor: "#fbfdff"
      }
    },
    viewerTheme: BASE_VIEWER_THEME
  }), "#111827");
});

test("stage plane factories return deterministic Three.js objects", () => {
  const floor = createStageFloorPlane(THREE, BASE_VIEWER_THEME, {
    floor: {
      color: "#202830",
      horizonBlend: 0.5,
      reflectivity: 0.2,
      roughness: 0.7
    },
    materials: {
      roughness: 0.6,
      clearcoat: 0.1,
      envMapIntensity: 0.5,
      defaultColor: "#ffffff"
    },
    environment: {
      enabled: true,
      intensity: 1
    }
  }, 120, -0.5);
  assert.equal(floor.type, "Mesh");
  assert.equal(floor.renderOrder, -3);
  assert.equal(floor.scale.x, 120);
  assert.equal(floor.position.z, -0.5);
  assert.equal(floor.material.transparent, true);

  const shadow = createStageShadowPlane(THREE, { floor: { shadowOpacity: 0.3 } }, 80, -0.25);
  assert.equal(shadow.type, "Mesh");
  assert.equal(shadow.receiveShadow, true);
  assert.equal(shadow.material.opacity, 0.3);
  assert.equal(createStageShadowPlane(THREE, { floor: { shadowOpacity: 0 } }, 80, 0), null);

  assert.equal(createStageFloorGlowPlane(THREE, { lighting: { spot: { enabled: false } } }, 1, 80, 0, VIEWER_SCENE_SCALE.CAD), null);
});

test("stage runtime helpers update background and spotlight targets without owning lifecycle", () => {
  const alphaValues = [];
  const runtime = {
    THREE,
    scene: {
      background: new THREE.Color("#ffffff")
    },
    renderer: {
      setClearAlpha(value) {
        alphaValues.push(value);
      }
    },
    sceneBackgroundTexture: {
      disposed: false,
      dispose() {
        this.disposed = true;
      }
    }
  };

  applySceneBackground(runtime, BASE_VIEWER_THEME, { type: "transparent" });
  assert.equal(runtime.sceneBackgroundTexture, null);
  assert.equal(runtime.scene.background, null);
  assert.deepEqual(alphaValues, [0]);

  applySceneBackground(runtime, BASE_VIEWER_THEME, { type: "solid", solidColor: "#123456" });
  assert.equal(runtime.scene.background.getHexString(), "123456");
  assert.deepEqual(alphaValues, [0, 1]);

  const targetPositions = [];
  const spotRuntime = {
    floorMode: THEME_FLOOR_MODES.STAGE,
    gridFloorZ: -0.75,
    spotLight: {
      target: {
        position: {
          set(x, y, z) {
            targetPositions.push([x, y, z]);
          }
        },
        updateMatrixWorld() {}
      }
    }
  };
  updateSpotLightTarget(spotRuntime);
  spotRuntime.floorMode = THEME_FLOOR_MODES.NONE;
  updateSpotLightTarget(spotRuntime);
  assert.deepEqual(targetPositions, [
    [0, 0, -0.75],
    [0, 0, 0]
  ]);
});

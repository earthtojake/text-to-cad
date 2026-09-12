import assert from "node:assert/strict";
import test from "node:test";

import {
  clampSceneModelRadius,
  defaultSceneGridRadius,
  getLightingScopeRadius,
  getProportionalLightingScopeRadius,
  getShadowCameraSettings,
  getSceneScaleSettings,
  normalizeSceneScaleMode,
  VIEWER_SCENE_SCALE
} from "./sceneScale.js";

test("CAD scenes keep the existing large minimum framing scale", () => {
  assert.equal(normalizeSceneScaleMode("anything-else"), VIEWER_SCENE_SCALE.CAD);
  assert.equal(clampSceneModelRadius(0.14, VIEWER_SCENE_SCALE.CAD), 1);
  assert.equal(defaultSceneGridRadius(VIEWER_SCENE_SCALE.CAD), 140);
  assert.equal(getLightingScopeRadius(VIEWER_SCENE_SCALE.CAD), 140);
  assert.deepEqual(getSceneScaleSettings(VIEWER_SCENE_SCALE.CAD), {
    minModelRadius: 1,
    minGridSize: 280,
    lightingScopeRadius: 140,
    lightingReferenceModelRadius: 760
  });
});

test("URDF scenes use meter-appropriate framing and lighting minimums", () => {
  assert.equal(normalizeSceneScaleMode(VIEWER_SCENE_SCALE.URDF), VIEWER_SCENE_SCALE.URDF);
  assert.equal(clampSceneModelRadius(0.14, VIEWER_SCENE_SCALE.URDF), 0.14);
  assert.equal(clampSceneModelRadius(0.01, VIEWER_SCENE_SCALE.URDF), 0.05);
  assert.equal(defaultSceneGridRadius(VIEWER_SCENE_SCALE.URDF), 0.14);
  assert.equal(getLightingScopeRadius(VIEWER_SCENE_SCALE.URDF), 0.14);
  assert.deepEqual(getSceneScaleSettings(VIEWER_SCENE_SCALE.URDF), {
    minModelRadius: 0.05,
    minGridSize: 0.28,
    lightingScopeRadius: 0.14,
    lightingReferenceModelRadius: 0.76
  });
});

test("shadow camera settings keep CAD lighting but preserve scene-unit shadow resolution", () => {
  assert.deepEqual(getShadowCameraSettings(VIEWER_SCENE_SCALE.CAD, {
    radius: 100,
    keyLightDistance: 420
  }), {
    scopeRadius: 100,
    extent: 280,
    far: 800,
    normalBias: 0.024,
    radius: 14
  });

  assert.deepEqual(getShadowCameraSettings(VIEWER_SCENE_SCALE.URDF, {
    radius: 0.1,
    keyLightDistance: 420
  }), {
    scopeRadius: 0.1,
    extent: 0.55,
    far: 421.6,
    normalBias: 0.000012,
    radius: 14
  });
});

test("proportional lighting scope scales from the reference model size", () => {
  assert.equal(getProportionalLightingScopeRadius(760, VIEWER_SCENE_SCALE.CAD), 140);
  assert.equal(getProportionalLightingScopeRadius(380, VIEWER_SCENE_SCALE.CAD), 70);
  assert.equal(getProportionalLightingScopeRadius(1520, VIEWER_SCENE_SCALE.CAD), 280);
  assert.equal(getProportionalLightingScopeRadius(0.76, VIEWER_SCENE_SCALE.URDF), 0.14);
  assert.equal(getProportionalLightingScopeRadius(0.38, VIEWER_SCENE_SCALE.URDF), 0.07);
});

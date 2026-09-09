import assert from "node:assert/strict";
import test from "node:test";

import {
  cameraSpecUsesPerspectiveProjection,
  normalizeCameraSpec,
  resolveCameraSnapshot
} from "./camera.js";
import {
  RENDER_SCENE_SCALE
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

test("camera preset strings expand like JSON preset specs", () => {
  const stringSpec = normalizeCameraSpec("iso");
  const jsonSpec = normalizeCameraSpec({ preset: "iso" });

  assert.equal(stringSpec.name, jsonSpec.name);
  assert.equal(stringSpec.preset, jsonSpec.preset);
  assert.deepEqual(stringSpec.direction, jsonSpec.direction);
  assert.deepEqual(stringSpec.up, jsonSpec.up);
  assert.equal(stringSpec.zoom, jsonSpec.zoom);
});

test("camera JSON preset overrides merge onto the preset defaults", () => {
  const spec = normalizeCameraSpec({
    preset: "top",
    up: [0, 0, 1],
    zoom: 1.4
  });

  assert.equal(spec.name, "top");
  assert.deepEqual(spec.direction, [0, 0, 1]);
  assert.deepEqual(spec.up, [0, 0, 1]);
  assert.equal(spec.zoom, 1.4);
  assert.equal(spec.hasExplicitZoom, true);
});

test("an explicit camera object without a preset is named custom", () => {
  const custom = normalizeCameraSpec({ direction: [1, 1, 1], up: [0, 0, 1], zoom: 1.2 });
  assert.equal(custom.name, "custom");
  // The default preset still supplies fallbacks, silently, without lending its name.
  assert.equal(custom.preset, "iso");

  const preset = normalizeCameraSpec({ preset: "front", zoom: 2 });
  assert.equal(preset.name, "front");

  const named = normalizeCameraSpec({ name: "hero", direction: [1, 0, 0] });
  assert.equal(named.name, "hero");
});

test("explicit camera state passes through resolved snapshots", () => {
  const snapshot = resolveCameraSnapshot({
    position: [10, 20, 30],
    target: [1, 2, 3],
    up: [0, 0, 1],
    zoom: 1.4
  }, { min: [0, 0, 0], max: [2, 4, 6] }, {
    sceneScale: RENDER_SCENE_SCALE.CAD,
    settingsByScale: SCALE_SETTINGS
  });

  assert.deepEqual(snapshot.position, [10, 20, 30]);
  assert.deepEqual(snapshot.target, [1, 2, 3]);
  assert.deepEqual(snapshot.up, [0, 0, 1]);
  assert.equal(snapshot.zoom, 1.4);
  assert.equal(cameraSpecUsesPerspectiveProjection({ position: [10, 20, 30] }), true);
});

test("omitted camera fields derive from model bounds", () => {
  const snapshot = resolveCameraSnapshot({ preset: "top" }, { min: [0, 0, 0], max: [2, 4, 6] }, {
    sceneScale: RENDER_SCENE_SCALE.CAD,
    settingsByScale: SCALE_SETTINGS
  });

  assert.deepEqual(snapshot.target, [1, 2, 3]);
  assertClose(snapshot.position[0], 1);
  assertClose(snapshot.position[1], 2);
  assert.ok(snapshot.position[2] > 3);
  assert.deepEqual(snapshot.up, [0, 1, 0]);
  assert.equal(snapshot.zoom, 1);
  assert.equal(cameraSpecUsesPerspectiveProjection({ preset: "top" }), false);
});

test("invalid camera specs fail clearly", () => {
  assert.throws(() => normalizeCameraSpec({ preset: "wat" }), /Unknown camera preset/);
  assert.throws(() => normalizeCameraSpec({ position: [1, 2, "x"] }), /camera.position/);
  assert.throws(() => normalizeCameraSpec({ up: [0, 0, 0] }), /camera.up/);
  assert.throws(() => normalizeCameraSpec({ zoom: 0 }), /camera.zoom/);
  assert.throws(() => normalizeCameraSpec({ preset: "iso", extra: true }), /Unsupported camera fields/);
});

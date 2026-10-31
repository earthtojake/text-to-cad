import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { keepOrthographicEyeOutside } from "./orthographicEye.js";

// A 120 × 80 × 8 plate; the eye 8 above a hole near its middle, as a look-at at the hole leaves it.
const plate = { min: [-60, -40, 0], max: [60, 40, 8] };

test("an orthographic eye inside the model steps back along its view until the whole model is in front of it; the picture is the same", () => {
  const camera = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.01, 1000);
  const target = new THREE.Vector3(4, 8, 8);
  camera.position.set(4, 0, 16);
  camera.lookAt(target);
  camera.updateMatrixWorld();
  const view = new THREE.Vector3(); camera.getWorldDirection(view);
  const before = new THREE.Vector3(30, -40, 0).project(camera);
  assert.equal(keepOrthographicEyeOutside(camera, target, plate), true);
  const after = new THREE.Vector3(); camera.getWorldDirection(after);
  assert.ok(after.distanceTo(view) < 1e-9, "the same direction");
  const moved = new THREE.Vector3(30, -40, 0).project(camera);
  assert.ok(Math.abs(moved.x - before.x) < 1e-9 && Math.abs(moved.y - before.y) < 1e-9, "the same picture");
  camera.updateMatrixWorld();
  for (const x of [-60, 60]) for (const y of [-40, 40]) for (const z of [0, 8]) {
    assert.ok(-new THREE.Vector3(x, y, z).applyMatrix4(camera.matrixWorldInverse).z > 0, `corner ${[x, y, z]} in front of the eye`);
  }
  // Outside already: left as it is.
  assert.equal(keepOrthographicEyeOutside(camera, target, plate), false);
});

test("a perspective eye is never moved: its distance is its picture", () => {
  const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 1000);
  camera.position.set(4, 0, 16);
  assert.equal(keepOrthographicEyeOutside(camera, new THREE.Vector3(4, 8, 8), plate), false);
  assert.deepEqual(camera.position.toArray(), [4, 0, 16]);
});

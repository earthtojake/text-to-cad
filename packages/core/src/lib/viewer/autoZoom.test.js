import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { fitDistanceForRadius, mergeBoundsList } from "./autoZoom.js";

test("auto zoom merges bounds, skipping what is not a box", () => {
  assert.deepEqual(
    mergeBoundsList([{ min: [0, 0, 0], max: [1, 1, 1] }, null, { min: [2, 0, 0], max: [3, 1, 1] }]),
    { min: [0, 0, 0], max: [3, 1, 1] }
  );
});

test("auto zoom fits a padded radius inside the narrower half angle", () => {
  const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 1000);
  const distance = fitDistanceForRadius(camera, Math.sqrt(3), { aspect: 1, padding: 1.2 });
  assert.ok(Math.abs(distance - (1.2 * Math.sqrt(3)) / Math.sin((24 * Math.PI) / 180)) < 1e-9);
  assert.ok(fitDistanceForRadius(camera, Math.sqrt(3), { aspect: 0.5, padding: 1.2 }) > distance, "a narrow frame stands further back");
});

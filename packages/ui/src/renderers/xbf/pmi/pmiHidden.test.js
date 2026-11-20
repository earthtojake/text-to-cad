// A point the model hides from the camera (`pmiHidden.js`): a surface in front of it, nearer than
// the tolerance allows, hides it; the point's own face, at its depth, does not; nor does anything
// for a point off the view.
import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { createHiddenTest } from "./pmiHidden.js";

// Looking down at the origin from z = 100, a 40 mm view.
const camera = new THREE.OrthographicCamera(-20, 20, 20, -20, 0.1, 1000);
camera.position.set(0, 0, 100);
camera.lookAt(0, 0, 0);
camera.updateMatrixWorld();
const hidden = createHiddenTest(THREE);

test("a point under a nearer surface is hidden; one on the surface the ray meets first is not", () => {
  const surfaceAt = z => ray => ({ point: [ray.origin.x, ray.origin.y, z] });
  assert.equal(hidden({ camera, pick: surfaceAt(5), point: [3, 4, 0], tolerance: 0.05 }), true, "a top 5 mm above it");
  assert.equal(hidden({ camera, pick: surfaceAt(0.01), point: [3, 4, 0], tolerance: 0.05 }), false, "its own face, within the tolerance");
  assert.equal(hidden({ camera, pick: () => null, point: [3, 4, 0], tolerance: 0.05 }), false, "nothing in the way");
  assert.equal(hidden({ camera, pick: surfaceAt(5), point: [300, 0, 0], tolerance: 0.05 }), false, "off the view");
});

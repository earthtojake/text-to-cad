import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { createZoomPivotReanchor } from "./zoomPivotReanchor.js";

function fixture() {
  const camera = new THREE.PerspectiveCamera();
  camera.position.set(0, 0, 20);
  camera.lookAt(0, 0, 0);
  const modelGroup = new THREE.Group();
  modelGroup.position.z = 5;
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial());
  modelGroup.add(mesh);
  modelGroup.updateMatrixWorld(true);
  const calls = { raycasts: 0 };
  mesh.raycast = function (...args) {
    calls.raycasts += 1;
    return THREE.Mesh.prototype.raycast.apply(this, args);
  };
  return {
    runtime: { camera, controls: { target: new THREE.Vector3(), minDistance: 0, maxDistance: Infinity },
      modelBounds: { min: [0, 0, 0], max: [0, 0, 2] }, modelGroup, raycaster: new THREE.Raycaster() },
    calls,
    dispose() { mesh.geometry.dispose(); mesh.material.dispose(); }
  };
}

test("Render wheel anchors at translated model bounds without raycasting, deformation or BVH requests", () => {
  const f = fixture();
  try {
    const anchor = createZoomPivotReanchor(THREE, { renderMode: true });
    const originalBounds = structuredClone(f.runtime.modelBounds);
    for (let i = 0; i < 3; i += 1) anchor.apply(f.runtime);
    assert.deepEqual(f.runtime.controls.target.toArray(), [0, 0, 6]);
    assert.deepEqual(f.runtime.camera.position.toArray(), [0, 0, 20]);
    assert.equal(f.calls.raycasts, 0, "no mesh raycast can request a BVH or materialize deformation");
    assert.deepEqual(f.runtime.modelBounds, originalBounds);
  } finally { f.dispose(); }
});

test("Inspect retains exact surface-hit zoom depth and falls back to model bounds after a miss", () => {
  const f = fixture();
  try {
    const anchor = createZoomPivotReanchor(THREE);
    anchor.apply(f.runtime);
    assert.deepEqual(f.runtime.controls.target.toArray(), [0, 0, 5.5]);
    assert.equal(f.calls.raycasts, 1);
    anchor.pointer.set(10, 10);
    anchor.apply(f.runtime);
    assert.deepEqual(f.runtime.controls.target.toArray(), [0, 0, 6]);
  } finally { f.dispose(); }
});

test("Render uses the existing target for missing bounds and respects pivot distance limits", () => {
  const f = fixture();
  try {
    const anchor = createZoomPivotReanchor(THREE, { renderMode: true });
    for (const bounds of [null, { min: [NaN, 0, 0], max: [1, 1, 1] }]) {
      f.runtime.modelBounds = bounds;
      f.runtime.controls.target.set(4, 3, 8);
      anchor.apply(f.runtime);
      assert.deepEqual(f.runtime.controls.target.toArray(), [0, 0, 8]);
    }
    f.runtime.controls.maxDistance = 5;
    anchor.apply(f.runtime);
    assert.deepEqual(f.runtime.controls.target.toArray(), [0, 0, 15]);
    f.runtime.controls.target.z = 30;
    f.runtime.controls.minDistance = 2;
    anchor.apply(f.runtime);
    assert.deepEqual(f.runtime.controls.target.toArray(), [0, 0, 18]);
    assert.equal(f.calls.raycasts, 0);
    f.runtime.camera = new THREE.OrthographicCamera();
    anchor.apply(f.runtime);
    assert.deepEqual(f.runtime.controls.target.toArray(), [0, 0, 18]);
  } finally { f.dispose(); }
});

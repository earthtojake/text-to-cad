import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { ensureFacePickBvh, scheduleRuntimeRaycastBvh } from "./raycastBvh.js";

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

// Two triangles over four SHARED vertices (the indexed surf shape), the second
// one raised so a ray down each column hits a known face index.
function indexedGeometry() {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array([
    0, 0, 0,
    1, 0, 0,
    1, 1, 0,
    0, 1, 0,
    2, 0, 1,
    3, 0, 1,
    3, 1, 1
  ]), 3));
  geometry.setIndex(new THREE.BufferAttribute(new Uint32Array([0, 1, 2, 0, 2, 3, 4, 5, 6]), 1));
  return geometry;
}

test("scheduleRuntimeRaycastBvh builds an indirect BVH over indexed geometry and keeps triangle order", async () => {
  const geometry = indexedGeometry();
  const savedIndex = geometry.index.array.slice();
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
  mesh.userData.faceIds = new Uint32Array([10, 11, 12]);
  mesh.updateMatrixWorld();
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh }] });
  await tick();

  assert.ok(geometry.boundsTree, "BVH built on the indexed geometry");
  assert.deepEqual(geometry.index.array, savedIndex, "indirect build leaves the index buffer untouched");
  assert.equal(geometry.attributes.position.count, 7, "no de-indexed copy was made");
  const hitFirst = new THREE.Raycaster(new THREE.Vector3(0.6, 0.3, 5), new THREE.Vector3(0, 0, -1)).intersectObject(mesh, false);
  const hitLast = new THREE.Raycaster(new THREE.Vector3(2.9, 0.5, 5), new THREE.Vector3(0, 0, -1)).intersectObject(mesh, false);
  assert.equal(hitFirst[0]?.faceIndex, 0);
  assert.equal(hitLast[0]?.faceIndex, 2);
  assert.equal(mesh.userData.faceIds[hitLast[0].faceIndex], 12, "faceRuns keyed by triangle index resolve");
});

test("ensureFacePickBvh rebuilds when the proxy index array identity changes", async () => {
  const proxy = {
    facePositions: new Float32Array([0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0]),
    faceIndices: new Uint32Array([0, 1, 2, 0, 2, 3])
  };
  const makeMesh = () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(proxy.facePositions, 3));
    geometry.setIndex(new THREE.BufferAttribute(proxy.faceIndices, 1));
    return new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  };
  const runtime = { facePickMesh: makeMesh() };
  ensureFacePickBvh(runtime, { proxy });
  await tick();
  const first = runtime.facePickMesh.geometry.boundsTree;
  assert.ok(first, "first BVH built in idle time");
  assert.equal(first.__builtFromIndexArray, proxy.faceIndices);

  // Same arrays, fresh geometry (a selector sync): the cached BVH is reattached.
  runtime.facePickMesh = makeMesh();
  ensureFacePickBvh(runtime, { proxy });
  assert.equal(runtime.facePickMesh.geometry.boundsTree, first);

  // New index array (a LOD swap): the cache misses and a new BVH is built.
  proxy.faceIndices = new Uint32Array([0, 2, 1, 0, 3, 2]);
  runtime.facePickMesh = makeMesh();
  ensureFacePickBvh(runtime, { proxy });
  await tick();
  const second = runtime.facePickMesh.geometry.boundsTree;
  assert.ok(second && second !== first, "index identity change rebuilds the BVH");
  assert.equal(second.__builtFromIndexArray, proxy.faceIndices);
});

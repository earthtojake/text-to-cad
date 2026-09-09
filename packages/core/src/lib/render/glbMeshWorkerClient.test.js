import assert from "node:assert/strict";
import test from "node:test";

import { loadGlbMeshDataInWorker } from "./glbMeshWorkerClient.js";
import { meshDataTransferList } from "./meshTransfer.js";

test("GLB mesh worker client falls back when Worker is unavailable", () => {
  assert.equal(loadGlbMeshDataInWorker("/mesh.glb"), null);
});

test("mesh transfer list includes unique non-empty typed-array buffers", () => {
  const shared = new ArrayBuffer(16);
  const transferList = meshDataTransferList({
    vertices: new Float32Array(shared),
    normals: new Float32Array(shared),
    indices: new Uint32Array([0, 1, 2]),
    colors: new Float32Array(0),
    surfaceEdgeBarycentric: new Float32Array([1, 0, 0]),
    surfaceEdgeClass: new Uint8Array([1, 0, 0])
  });

  assert.equal(transferList.length, 4);
  assert.equal(transferList[0], shared);
});

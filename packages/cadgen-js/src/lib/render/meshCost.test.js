import assert from "node:assert/strict";
import test from "node:test";

import {
  estimateMeshRenderCost,
  hasMeshGeometry,
  isLargeMeshData,
  isLargeNativeGlbEntry,
  isLargeStepGlbEntry,
  LARGE_MESH_TRIANGLE_COUNT,
  LARGE_MESH_TYPED_ARRAY_BYTES,
  LARGE_STEP_GLB_BYTES,
  shouldUseGlbMeshWorkerForEntry
} from "./meshCost.js";

test("large STEP GLBs are classified from catalog asset bytes", () => {
  const smallStep = {
    kind: "part",
    url: "/parts/.small.step.glb",
    hash: "small-hash",
    bytes: LARGE_STEP_GLB_BYTES - 1
  };
  const largeStep = {
    kind: "part",
    url: "/parts/.large.step.glb",
    hash: "large-hash",
    bytes: LARGE_STEP_GLB_BYTES
  };
  const largeNativeGlb = {
    kind: "glb",
    url: "/meshes/large.glb",
    hash: "large-glb-hash",
    bytes: LARGE_STEP_GLB_BYTES
  };

  assert.equal(isLargeStepGlbEntry(smallStep), false);
  assert.equal(isLargeStepGlbEntry(largeStep), true);
  assert.equal(isLargeNativeGlbEntry(largeNativeGlb), true);
  assert.equal(shouldUseGlbMeshWorkerForEntry(largeStep), true);
  assert.equal(shouldUseGlbMeshWorkerForEntry(largeNativeGlb), true);
});

test("component geometry is renderable and its memory is counted once per array", () => {
  const component = { vertices: new Float32Array(9), indices: new Uint32Array(3) };
  const packageMesh = { parts: [
    { sourceMesh: component, triangleCount: 1 },
    { sourceMesh: component, triangleCount: 1 }
  ] };
  assert.equal(hasMeshGeometry(packageMesh), true);
  assert.equal(hasMeshGeometry(component), true);
  assert.equal(hasMeshGeometry({ parts: [{ sourceMesh: { vertices: [] } }] }), false);
  assert.equal(hasMeshGeometry(null), false);
  assert.deepEqual(estimateMeshRenderCost(packageMesh), { triangleCount: 2, typedArrayBytes: 48 });
  assert.deepEqual(estimateMeshRenderCost({ ...component, parts: packageMesh.parts }), {
    triangleCount: 2, typedArrayBytes: 48
  });
});

test("mesh render cost uses triangle count and typed-array bytes", () => {
  const meshData = {
    vertices: new Float32Array(9),
    normals: new Float32Array(9),
    colors: new Float32Array(0),
    indices: new Uint32Array(3),
    edge_indices: new Uint32Array(2),
    surfaceEdgeBarycentric: new Float32Array(9),
    surfaceEdgeClass: new Uint8Array(9),
    parts: [{ triangleCount: LARGE_MESH_TRIANGLE_COUNT }]
  };

  assert.deepEqual(estimateMeshRenderCost(meshData), {
    triangleCount: LARGE_MESH_TRIANGLE_COUNT,
    typedArrayBytes: 137
  });
  assert.equal(isLargeMeshData(meshData), true);
  assert.equal(isLargeMeshData({
    vertices: new Uint8Array(LARGE_MESH_TYPED_ARRAY_BYTES),
    indices: new Uint32Array(3)
  }), true);
});

import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";
import { toCreasedNormals } from "three/examples/jsm/utils/BufferGeometryUtils.js";

import { buildMeshDataFromStlGeometry } from "./stlMeshData.js";

test("buildMeshDataFromStlGeometry recomputes crease-aware STL display normals", () => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute([
      0, 0, 0,
      1, 0, 0,
      1, 1, 0,
      0, 0, 0,
      1, 1, 0,
      0, 1, 0
    ], 3)
  );
  geometry.setAttribute(
    "normal",
    new THREE.Float32BufferAttribute([
      0, 0, -1,
      0, 0, -1,
      0, 0, -1,
      0, 0, -1,
      0, 0, -1,
      0, 0, -1
    ], 3)
  );

  const meshData = buildMeshDataFromStlGeometry(geometry, { toCreasedNormals });

  assert.equal(meshData.vertices.length, 18);
  assert.equal(meshData.indices.length, 6);
  assert.deepEqual([...meshData.normals.slice(0, 3)], [0, 0, 1]);
  assert.equal(meshData.has_source_colors, false);
  assert.equal(meshData.sourceFormat, "stl");
});

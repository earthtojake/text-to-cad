import assert from "node:assert/strict";
import test from "node:test";

import { meshImplicitCadModel } from "./mesh.js";
import { analyzeImplicitMeshQuality } from "./meshQuality.js";

const sphereModel = {
  schema: "implicit.js/0.1.0",
  name: "quality sphere",
  bounds: [[-6, -6, -6], [6, 6, 6]],
  glsl: "float sdf(vec3 p) { return length(p) - 4.0; }",
};

test("implicit mesh quality reports closed outward sphere mesh", () => {
  const mesh = meshImplicitCadModel(sphereModel, { resolution: 20, smoothNormals: true });
  const quality = analyzeImplicitMeshQuality(mesh, { model: sphereModel });
  assert.ok(quality.triangleCount > 0);
  assert.equal(quality.triangles.nonFinitePositions, 0);
  assert.equal(quality.triangles.degenerate, 0);
  assert.equal(quality.edges.boundary, 0);
  assert.equal(quality.edges.nonManifold, 0);
  assert.equal(quality.orientation.inverted, 0);
  assert.ok(quality.triangles.worstNormalAlignment > 0.4);
});

test("implicit mesh quality detects boundary edges", () => {
  const mesh = {
    positions: new Float32Array([
      0, 0, 0,
      1, 0, 0,
      0, 1, 0,
    ]),
    normals: new Float32Array([
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
    ]),
    grid: { step: [1, 1, 1] },
  };
  const quality = analyzeImplicitMeshQuality(mesh);
  assert.equal(quality.triangleCount, 1);
  assert.equal(quality.edges.boundary, 3);
  assert.equal(quality.edges.nonManifold, 0);
});

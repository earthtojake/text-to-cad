import assert from "node:assert/strict";
import test from "node:test";

import { resolveCadAssetMeshUrl, resolveLocalAssetFileRef } from "./meshAssetUrl.js";

test("a link mesh is served from the description's asset route, versioned with it", () => {
  const description = "/__cad/asset?file=%2Frobots%2Farm.urdf&v=e4-abc";
  assert.equal(resolveCadAssetMeshUrl("../meshes/tetra.stl", description), "/__cad/asset?file=%2Fmeshes%2Ftetra.stl&v=e4-abc");
  assert.equal(resolveCadAssetMeshUrl("/abs/meshes/tetra.stl", description), "/__cad/asset?file=%2Fabs%2Fmeshes%2Ftetra.stl&v=e4-abc");
  // Not from the asset route: nothing to resolve against.
  assert.equal(resolveCadAssetMeshUrl("meshes/tetra.stl", "https://static.example/robots/arm.urdf"), "");
  assert.equal(resolveCadAssetMeshUrl("package://pkg/arm.stl", description), "");
  assert.equal(resolveLocalAssetFileRef("/robots/arm.urdf", "./a/../meshes/tetra.stl"), "/robots/meshes/tetra.stl");
});

test("the asset route keeps its path prefix: a hosted build's meshes come from the build's own route", () => {
  const description = "https://cad.example/b/k7Qx2/__cad/asset?file=%2Frobots%2Farm.urdf&v=e4-abc";
  assert.equal(resolveCadAssetMeshUrl("../meshes/tetra.stl", description),
    "https://cad.example/b/k7Qx2/__cad/asset?file=%2Fmeshes%2Ftetra.stl&v=e4-abc");
  assert.equal(resolveCadAssetMeshUrl("meshes/tetra.stl", "/b/k7Qx2/__cad/asset?file=%2Farm.urdf"), "/b/k7Qx2/__cad/asset?file=%2Fmeshes%2Ftetra.stl");
  // Only the route itself, not a path that merely ends in the words.
  assert.equal(resolveCadAssetMeshUrl("a.stl", "/not__cad/asset?file=%2Farm.urdf"), "");
});

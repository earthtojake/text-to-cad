import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { createPartOcclusionGhostMaterial } from "./partHighlight.js";

test("a selection's ghost is an even blend, drawn once per pixel, not a dither", () => {
  const ghost = createPartOcclusionGhostMaterial(THREE);
  // A dither's pattern read as grain on the hidden surface (it was a discard in onBeforeCompile).
  assert.equal(ghost.onBeforeCompile.toString(), new THREE.MeshBasicMaterial().onBeforeCompile.toString());
  assert.deepEqual([ghost.transparent, ghost.depthFunc, ghost.depthWrite], [true, THREE.GreaterDepth, false]);
  assert.deepEqual(
    [ghost.stencilWrite, ghost.stencilFunc, ghost.stencilZPass, ghost.stencilFail, ghost.stencilZFail],
    [true, THREE.NotEqualStencilFunc, THREE.ReplaceStencilOp, THREE.KeepStencilOp, THREE.KeepStencilOp]
  );
  assert.ok(ghost.stencilRef > 251, "past the stencil values an annotation's strokes use");
});

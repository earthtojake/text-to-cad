import assert from "node:assert/strict";
import test from "node:test";
import { meshVolume, nodeVolume, partVolume } from "./partVolume.js";

// A unit cube, outward-wound: 8 corners, 12 triangles.
const vertices = new Float32Array([0,0,0, 1,0,0, 1,1,0, 0,1,0, 0,0,1, 1,0,1, 1,1,1, 0,1,1]);
const indices = new Uint32Array([0,2,1, 0,3,2, 4,5,6, 4,6,7, 0,1,5, 0,5,4, 1,2,6, 1,6,5, 2,3,7, 2,7,6, 3,0,4, 3,4,7]);
const cube = { vertices, indices };

test("a closed mesh's volume, whatever its winding", () => {
  assert.equal(meshVolume(vertices, indices), 1);
  assert.equal(meshVolume(vertices, indices.slice().reverse()), 1);
  assert.equal(meshVolume(new Float32Array(0), indices), null);
});

test("a part places its component: rigid keeps the volume, scale multiplies it", () => {
  const moved = [1,0,0,40, 0,1,0,-3, 0,0,1,9, 0,0,0,1];
  const doubled = [2,0,0,0, 0,2,0,0, 0,0,2,0, 0,0,0,1];
  assert.equal(partVolume({ sourceMesh: cube, transform: moved }), 1);
  assert.equal(partVolume({ sourceMesh: cube, transform: doubled }), 8);
});

test("a subassembly is the sum of its parts, and unknown if any part is", () => {
  const meshData = { parts: [{ id: "a", sourceMesh: cube }, { id: "b", sourceMesh: cube, transform: [2,0,0,0, 0,2,0,0, 0,0,2,0, 0,0,0,1] }] };
  assert.equal(nodeVolume({ id: "a" }, meshData), 1);
  assert.equal(nodeVolume({ id: "group", leafPartIds: ["a", "b"] }, meshData), 9);
  assert.equal(nodeVolume({ id: "group", leafPartIds: ["a", "missing"] }, meshData), null);
});

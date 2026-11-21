import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { buildMeshScene } from "./meshScene.js";
import { STL_BODY_LIMIT, withStlBodies } from "./stlBodies.js";
import { buildMeshDataFromStlBuffer } from "./stlMeshData.js";
import { loadStlBodies } from "./stlMeshWorkerClient.js";

// Tiny STLs made here: a cube of `size` at `origin` (12 triangles), a tetrahedron (4).
const CUBE = { corners: [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
  triangles: [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [2, 3, 7], [2, 7, 6], [1, 2, 6], [1, 6, 5], [3, 0, 4], [3, 4, 7]] };
const TETRA = { corners: [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], triangles: [[0, 2, 1], [0, 1, 3], [1, 2, 3], [0, 3, 2]] };
const facets = (shape, [x, y, z], size) => shape.triangles.map(triangle => triangle.map(index => {
  const [a, b, c] = shape.corners[index];
  return [x + a * size, y + b * size, z + c * size];
}));
function binaryStl(triangles) {
  const bytes = Buffer.alloc(84 + triangles.length * 50);
  bytes.writeUInt32LE(triangles.length, 80);
  triangles.forEach((triangle, index) => triangle.flat().forEach((value, at) => bytes.writeFloatLE(value, 84 + index * 50 + 12 + at * 4)));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.length);
}
const asciiStl = solids => new TextEncoder().encode(solids.map(({ name, triangles }) => `solid ${name}\n${triangles.map(triangle =>
  `facet normal 0 0 0\nouter loop\n${triangle.map(corner => `vertex ${corner.join(" ")}`).join("\n")}\nendloop\nendfacet`).join("\n")}\nendsolid ${name}\n`).join("")).buffer;
const rows = scene => scene.nodeTree.map(({ id, label }) => [id, label]);

test("an STL's bodies are its rows, largest first, and a pick names the body under it", async () => {
  // The small body first in the file: the rows go by size, not file order.
  const meshData = await buildMeshDataFromStlBuffer(binaryStl([...facets(TETRA, [30, 0, 0], 5), ...facets(CUBE, [0, 0, 0], 10)]));
  const split = await loadStlBodies(meshData);
  assert.deepEqual(split.parts.map(({ name, triangleCount, body }) => [name, triangleCount, body]), [["Body 1", 12, 1], ["Body 2", 4, 2]]);
  assert.equal(meshData.parts.length, 0, "the decode the cache holds is never written");
  assert.equal(await loadStlBodies(meshData), split, "a file reopened finds its bodies split");

  const scene = buildMeshScene(THREE, split, { name: "pair.stl" });
  assert.deepEqual(rows(scene), [["b1", "Body 1"], ["b2", "Body 2"]]);
  assert.deepEqual(scene.describePart("b2").facts.map(({ value }) => value), ["2 of 2", "4"]);
  // Straight down onto the cube's top, then onto the tetrahedron's.
  const down = ([x, y]) => new THREE.Ray(new THREE.Vector3(x, y, 100), new THREE.Vector3(0, 0, -1));
  assert.deepEqual([scene.pick(down([5, 5]))?.id, scene.pick(down([31, 1]))?.id, scene.pick(down([20, 20]))], ["b1", "b2", null]);
  scene.dispose();
});

test("one body is one row named for the file, or for its one named solid; named solids stay apart", async () => {
  const cube = await loadStlBodies(await buildMeshDataFromStlBuffer(binaryStl(facets(CUBE, [0, 0, 0], 10))));
  assert.deepEqual(rows(buildMeshScene(THREE, cube, { name: "part.stl" })), [["b1", "part.stl"]]);
  const named = await buildMeshDataFromStlBuffer(asciiStl([{ name: "bracket", triangles: facets(CUBE, [0, 0, 0], 10) }]));
  assert.deepEqual(rows(buildMeshScene(THREE, named, { name: "part.stl" })), [["b1", "bracket"]], "the first frame, before the split");
  assert.deepEqual(rows(buildMeshScene(THREE, await loadStlBodies(named), { name: "part.stl" })), [["b1", "bracket"]]);
  // Two solids that share corners: a row each, by its name, never welded into one.
  const pair = await buildMeshDataFromStlBuffer(asciiStl([{ name: "lid", triangles: facets(CUBE, [0, 0, 10], 10) },
    { name: "base", triangles: facets(CUBE, [0, 0, 0], 10) }]));
  assert.deepEqual(rows(buildMeshScene(THREE, await loadStlBodies(pair))), [["b1", "lid"], ["b2", "base"]]);
});

test(`past ${STL_BODY_LIMIT} bodies an STL is not split: one row`, () => {
  // Loose triangles, each a body of its own.
  const count = STL_BODY_LIMIT + 1;
  const vertices = new Float32Array(count * 9);
  for (let triangle = 0; triangle < count; triangle += 1) vertices.set([triangle * 3, 0, 0, triangle * 3 + 1, 0, 0, triangle * 3, 1, 0], triangle * 9);
  const { parts } = withStlBodies({ vertices, normals: new Float32Array(vertices.length) });
  assert.deepEqual(parts.map(({ name, triangleCount }) => [name, triangleCount]), [["", count]]);
  const under = withStlBodies({ vertices: vertices.subarray(0, STL_BODY_LIMIT * 9), normals: new Float32Array(STL_BODY_LIMIT * 9) });
  assert.equal(under.parts.length, STL_BODY_LIMIT);
});

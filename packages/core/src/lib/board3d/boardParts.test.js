import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { bakeModel, createBoardParts, createModelLoader } from "./boardParts.js";

// A unit cube's mesh as the engine's XBM2 reader hands it (`xbf/xbm.js`): 8 nodes, 12 triangles, two faces
// (the top's two triangles one face, the rest another).
function cube() {
  const positions = new Float32Array([0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1]);
  const normals = new Float32Array(24).fill(0).map((_, index) => (index % 3 === 2 ? 1 : 0));
  const indices = new Uint32Array([4, 5, 6, 4, 6, 7, 0, 2, 1, 0, 3, 2, 0, 1, 5, 0, 5, 4, 1, 2, 6, 1, 6, 5, 2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7]);
  return { positions, normals, indices, faces: new Uint32Array([1, 0, 6, 2, 6, 30]) };
}
const at = (x, y, z) => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1];
// A model of two instances of the cube, one grey and one, its top face painted, red-topped.
const DOCUMENT = {
  structure: {
    prototypes: [{ key: "k1", color: [0.5, 0.5, 0.5, 1] }, { key: "k1", color: [0.1, 0.1, 0.1, 1], faceColors: { 1: [1, 0, 0, 1] } }],
    instances: [{ prototype: 0, matrix: at(0, 0, 0) }, { prototype: 1, matrix: at(2, 0, 0) }]
  },
  parts: new Map([["k1", { mesh: cube() }]])
};
const rect = (cx, cy, w, h) => [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]];
const PARTS = [
  { ref: "R1", at: [10, 10], rotation: 0, side: "top", outline: rect(10, 10, 2, 1), models: [{ name: "${KIPRJMOD}/r.step" }] },
  { ref: "R2", at: [20, 10], rotation: 90, side: "top", outline: rect(20, 10, 2, 1), models: [{ name: "${KIPRJMOD}/r.step" }] },
  { ref: "U1", at: [30, 10], rotation: 0, side: "bottom", outline: rect(30, 10, 4, 4), models: [{ name: "gone.wrl" }] },
  { ref: "H1", at: [5, 5], rotation: 0, side: "top", outline: rect(5, 5, 3, 3) }
];
const TABLE = { "${KIPRJMOD}/r.step": { file: "r.step", document: "d1", api: "/api/v1/documents/step/d1", stamp: "1-10" },
  "gone.wrl": { file: "gone.wrl", missing: "not-found" } };
const down = (x, y) => new THREE.Ray(new THREE.Vector3(x, y, 50), new THREE.Vector3(0, 0, -1));
const up = (x, y) => new THREE.Ray(new THREE.Vector3(x, y, -50), new THREE.Vector3(0, 0, 1));

test("a model's document bakes into one geometry, its instances placed and its triangles grouped by colour", () => {
  const baked = bakeModel(THREE, DOCUMENT);
  assert.equal(baked.triangles, 24);
  assert.deepEqual(baked.colors, [[0.5, 0.5, 0.5, 1], [1, 0, 0, 1], [0.1, 0.1, 0.1, 1]]);
  assert.deepEqual(baked.geometry.groups.map(group => group.count / 3), [12, 2, 10]);
  assert.deepEqual([baked.geometry.boundingBox.min.toArray(), baked.geometry.boundingBox.max.toArray()], [[0, 0, 0], [3, 1, 1]]);
});

test("every placement of a model shares its one geometry; a missing model is a block; a part that names none has neither", () => {
  const parts = createBoardParts(THREE, { thickness: 1.6 });
  parts.setParts(PARTS, TABLE);
  assert.deepEqual(parts.wanted().map(item => [item.key, item.document]), [["d1@1-10", "d1"]]);
  assert.deepEqual(parts.stats().blocks, 1);
  parts.addModel("d1@1-10", bakeModel(THREE, DOCUMENT));
  const stats = parts.stats();
  assert.deepEqual([stats.bodies, stats.blocks, stats.models, stats.triangles, parts.wanted().length], [2, 1, 1, 48, 0]);
  const meshes = [];
  parts.object3D.traverse(object => { if (object.isMesh && object.userData.boardPart?.startsWith("R")) meshes.push(object); });
  assert.equal(meshes.length, 2);
  assert.equal(meshes[0].geometry, meshes[1].geometry);
  // Picked by its body from above (R1's first cube is at its place, 0..1 mm out of the front face), the
  // missing U1 by its block from below.
  assert.equal(parts.pick(down(10.5, -9.5)).ref, "R1");
  const block = parts.pick(up(30, -10));
  assert.equal(block.ref, "U1");
  assert.ok(Math.abs(block.point[2] - (-1.6 - 1)) < 1e-6, `the block hangs a millimetre under the back: ${block.point}`);
  assert.equal(parts.pick(down(5, -5)), null);
  parts.setVisible(false);
  assert.equal(parts.pick(down(10.5, -9.5)), null);
  parts.dispose();
});

test("the models are asked for the largest parts' first, each once", () => {
  const parts = createBoardParts(THREE, { thickness: 1.6 });
  const table = { ...TABLE, "q.step": { file: "q.step", document: "d2", api: "/api/v1/documents/step/d2", stamp: "1-20" } };
  parts.setParts([...PARTS, { ref: "U2", at: [40, 10], rotation: 0, side: "top", outline: rect(40, 10, 14, 14), models: [{ name: "q.step" }] }], table);
  assert.deepEqual(parts.wanted().map(item => item.key), ["d2@1-20", "d1@1-10"]);
  parts.dispose();
});

test("a moved part is placed again alone; a model no part uses any more is let go", () => {
  const parts = createBoardParts(THREE, { thickness: 1.6 });
  parts.setParts(PARTS, TABLE);
  parts.addModel("d1@1-10", bakeModel(THREE, DOCUMENT));
  const holders = () => new Map(parts.object3D.children.map(child => [child.name, child]));
  const before = holders();
  parts.setParts(PARTS.map(part => (part.ref === "R2" ? { ...part, at: [25, 10] } : part)), TABLE);
  const after = holders();
  assert.equal(after.get("R1"), before.get("R1"));
  assert.notEqual(after.get("R2"), before.get("R2"));
  assert.equal(parts.stats().models, 1);
  parts.setParts(PARTS.filter(part => !part.ref.startsWith("R")), TABLE);
  assert.equal(parts.stats().models, 0);
  parts.dispose();
});

test("the highlight lights a picked part's body, and isolation fades the bodies that are not it", () => {
  const parts = createBoardParts(THREE, { thickness: 1.6 });
  parts.setParts(PARTS, TABLE);
  parts.addModel("d1@1-10", bakeModel(THREE, DOCUMENT));
  const body = ref => parts.object3D.children.find(child => child.name === ref).children[0];
  const grey = body("R1").material[0].color.clone();
  assert.equal(parts.setInk({ selected: ["R1"] }), true);
  assert.notDeepEqual(body("R1").material[0].color.toArray(), grey.toArray());
  assert.equal(body("R2").material[0].opacity, 1);
  assert.equal(parts.setInk({ selected: ["R1"] }), false, "the same ink paints nothing");
  parts.setInk({ bright: ["R2"] });
  assert.ok(body("R1").material[0].opacity < 0.2);
  assert.equal(body("R2").material[0].opacity, 1);
  parts.dispose();
});

test("the loader opens each model by its document id once and bakes it, reading no look (the board's materials are its own)", async () => {
  const opened = [];
  const fetch = async url => {
    if (url.endsWith("/structure")) return { ok: true, json: async () => ({ prototypes: [], instances: [] }) };
    throw new Error(`asked for ${url}`);
  };
  const done = [];
  let finished;
  const all = new Promise(resolve => { finished = resolve; });
  const loader = createModelLoader(THREE, {
    open: async document => { opened.push(document); return { url: `http://127.0.0.1:9/api/v1/documents/step/${document}`, fetch }; },
    onModel: key => { done.push(key); if (done.length === 2) finished(); },
    onFailed: (key, message) => { done.push(`${key}: ${message}`); finished(); }
  });
  loader.request([{ key: "a@1", document: "a" }, { key: "b@1", document: "b" }]);
  loader.request([{ key: "a@1", document: "a" }]);
  await all;
  assert.deepEqual([opened.sort(), done.sort()], [["a", "b"], ["a@1", "b@1"]]);
  loader.dispose();
});

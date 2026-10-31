import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { createSceneExplode } from "./sceneExplode.js";

// A root, its placement fixed (a GLB's metres-to-millimetres), holding a rotated assembly node with
// two parts in it, and a third part nested under the second.
function tree() {
  const root = new THREE.Group();
  root.matrix.makeScale(1000, 1000, 1000);
  root.matrixAutoUpdate = false;
  const assembly = new THREE.Group();
  assembly.rotation.z = Math.PI / 2;
  const part = (x, size = 0.01) => { const mesh = new THREE.Mesh(new THREE.BoxGeometry(size, size, size)); const node = new THREE.Group(); node.position.set(x, 0, 0); node.add(mesh); return { node, mesh }; };
  const left = part(-0.02), right = part(0.02), inner = part(0.01, 0.004);
  right.node.add(inner.node);
  assembly.add(left.node, right.node);
  root.add(assembly);
  root.updateMatrixWorld(true);
  const parts = [
    { object: left.node, path: "o1.1", meshes: [left.mesh] },
    { object: right.node, path: "o1.2", meshes: [right.mesh] },
    { object: inner.node, path: "o1.2.1", meshes: [inner.mesh] }
  ];
  return { root, parts, left, right, inner };
}
const worldX = object => new THREE.Vector3().setFromMatrixPosition(object.matrixWorld).toArray();

test("Explode moves each part out along the file's tree in its parent's frame, and puts every part back at zero", () => {
  const { root, parts, left, right, inner } = tree();
  const rest = parts.map(part => part.object.position.clone());
  const restWorld = [left.node, right.node].map(worldX);
  const bounds = new THREE.Box3().setFromObject(root);
  const explode = createSceneExplode(THREE, root, parts, { min: bounds.min.toArray(), max: bounds.max.toArray() });
  assert.equal(explode.parts, 3);
  const out = explode.set(1);
  // The assembly is turned a quarter: its parts lie along world Y, and move further apart along it.
  const [leftOut, rightOut] = [left.node, right.node].map(worldX);
  assert.ok(leftOut[1] < restWorld[0][1] - 1 && rightOut[1] > restWorld[1][1] + 1, JSON.stringify({ restWorld, leftOut, rightOut }));
  assert.ok(Math.abs(leftOut[0] - restWorld[0][0]) < 1e-6, "no part leaves the line its tree spreads it along");
  assert.ok(out.max[1] - out.min[1] > bounds.max.y - bounds.min.y, "the box they make grows");
  // The nested part rides with its carrier and adds only its own share.
  assert.ok(Math.abs(worldX(inner.node)[1] - worldX(right.node)[1]) < 30, "the nested part stays by the part it is under");
  explode.set(0);
  assert.deepEqual(parts.map(part => part.object.position.toArray()), rest.map(position => position.toArray()));
});

test("fewer than two parts explode nothing, and the layout is measured only once Explode is used", () => {
  const { root, parts } = tree();
  assert.equal(createSceneExplode(THREE, root, parts.slice(0, 1), null).parts, 0);
  const explode = createSceneExplode(THREE, root, parts, null);
  parts[0].object.position.x = 5; // a routine moved it; Explode starts from where it was authored
  explode.set(0.5);
  explode.set(0);
  assert.equal(parts[0].object.position.x, -0.02);
});

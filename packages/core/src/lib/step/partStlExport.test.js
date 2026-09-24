import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";

import { buildExportGroup, encodeBase64, exportNameForPart } from "./partStlExport.js";

function placedMesh(x) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshBasicMaterial());
  mesh.position.set(x, 0, 0);
  mesh.updateMatrixWorld(true);
  return mesh;
}

test("an exported part keeps where it sits in the assembly", () => {
  // three's STLExporter reads matrixWorld and never refreshes it, while
  // applyMatrix4 writes the LOCAL matrix -- without the update every part
  // exports at the origin, in a file that opens fine and has lost its place.
  const group = buildExportGroup(THREE, [placedMesh(100)]);
  const centre = new THREE.Vector3().setFromMatrixPosition(group.children[0].matrixWorld);
  assert.equal(Math.round(centre.x), 100);
});

test("several meshes keep their positions relative to each other", () => {
  const group = buildExportGroup(THREE, [placedMesh(-50), placedMesh(50)]);
  const xs = group.children.map((c) => Math.round(new THREE.Vector3().setFromMatrixPosition(c.matrixWorld).x));
  assert.deepEqual(xs, [-50, 50]);
});

test("a mesh with no geometry is skipped rather than added empty", () => {
  assert.equal(buildExportGroup(THREE, [null, {}]).children.length, 0);
});

test("the part name becomes a filename the server will accept unchanged", () => {
  assert.equal(exportNameForPart("plant_1_02"), "plant_1_02.stl");
  assert.equal(exportNameForPart("plant_1_02.stl"), "plant_1_02.stl");
  assert.equal(exportNameForPart("column_1 deck socket"), "column_1_deck_socket.stl");
  assert.equal(exportNameForPart(""), "part.stl");
});

test("base64 survives a buffer larger than one chunk", () => {
  // Encoded naively through apply(), a part of any real size overflows the
  // argument limit and throws.
  const big = new Uint8Array(0x8000 * 2 + 5).fill(65);
  const encoded = encodeBase64(big);
  assert.equal(atob(encoded).length, big.length);
});

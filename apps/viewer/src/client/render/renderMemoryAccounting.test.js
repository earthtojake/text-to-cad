import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { renderMemoryAccounting } from "./renderMemoryAccounting.js";

test("render memory accounting counts shared component buffers once and splits edges from surfaces", () => {
  const surface = new THREE.BufferGeometry();
  surface.setAttribute("position", new THREE.BufferAttribute(new Float32Array(12), 3));
  surface.setIndex(new THREE.BufferAttribute(new Uint32Array(6), 1));
  surface.boundsTree = { _roots: [new ArrayBuffer(64), new ArrayBuffer(32)] };
  const edge = new THREE.BufferGeometry();
  edge.setAttribute("position", new THREE.BufferAttribute(new Float32Array(6), 3));
  edge.setAttribute("color", new THREE.BufferAttribute(new Uint16Array(8), 4, true));
  edge.setIndex(new THREE.BufferAttribute(new Uint32Array(2), 1));
  const records = [0, 1].map(() => ({
    mesh: new THREE.Mesh(surface, new THREE.MeshBasicMaterial()),
    edges: new THREE.LineSegments(edge, new THREE.LineBasicMaterial())
  }));
  const totals = renderMemoryAccounting({ displayRecords: records });
  assert.equal(totals.occurrences, 2);
  assert.equal(totals.edgeObjects, 2);
  assert.equal(totals.geometries, 2);
  assert.equal(totals.buffers, 5);
  assert.equal(totals.materials, 4);
  assert.equal(totals.surfaceBytes, 12 * 4 + 6 * 4);
  assert.equal(totals.edgeBytes, 6 * 4 + 8 * 2 + 2 * 4);
  assert.equal(totals.bvhBytes, 96);
  assert.equal(totals.bvhGeometries, 1);
  assert.equal(typeof totals.assetCaches.surfPayload.entries, "number");
  assert.deepEqual(renderMemoryAccounting(null).occurrences, 0);
});

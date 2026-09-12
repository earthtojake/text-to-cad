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

function geometry(triangles) {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(triangles * 9), 3));
  g.setIndex(new THREE.BufferAttribute(new Uint32Array(triangles * 3), 1));
  return g;
}

// Occurrences of one component share its geometry, so its bytes are counted
// ONCE however many times it is placed — the whole point of the accounting.
test("component bytes are counted once across occurrences, picking is counted separately", () => {
  const shared = geometry(4);
  const records = [0, 1, 2].map((index) => {
    const mesh = new THREE.Mesh(shared, new THREE.MeshStandardMaterial());
    mesh.userData.faceIds = new Uint32Array(4);
    return { partId: `o${index}`, mesh };
  });
  // Two occurrences share one face-id array only if the code hands them one; a
  // per-occurrence map is the real shape, so give the third its own.
  records[1].mesh.userData.faceIds = records[0].mesh.userData.faceIds;

  const facePickMesh = new THREE.Mesh(geometry(9), new THREE.MeshBasicMaterial());
  facePickMesh.userData.faceIds = new Uint32Array(9);
  facePickMesh.geometry.boundsTree = { _roots: [new ArrayBuffer(2048)] };

  const totals = renderMemoryAccounting({ displayRecords: records, facePickMesh });

  assert.equal(totals.occurrences, 3);
  assert.equal(totals.geometries, 2, "one component geometry plus the pick proxy");
  assert.equal(totals.surfaceBytes, 4 * 9 * 4 + 4 * 3 * 4, "the shared component, once");
  assert.equal(totals.faceIdArrays, 3, "two occurrence maps and the proxy's");
  assert.equal(totals.faceIdBytes, (4 + 4 + 9) * 4);
  assert.equal(totals.pickGeometries, 1);
  assert.equal(totals.pickBytes, 9 * 9 * 4 + 9 * 3 * 4, "the proxy's bytes are not surface bytes");
  assert.equal(totals.bvhBytes, 2048);
  assert.equal(totals.bvhGeometries, 1);
});

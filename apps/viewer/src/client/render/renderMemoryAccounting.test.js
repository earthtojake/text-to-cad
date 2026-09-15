import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { componentMemoryAccounting, renderMemoryAccounting } from "./renderMemoryAccounting.js";

test("render memory accounting counts shared component buffers once and splits edges from surfaces", () => {
  const surface = new THREE.BufferGeometry();
  surface.setAttribute("position", new THREE.BufferAttribute(new Float32Array(12), 3));
  surface.setIndex(new THREE.BufferAttribute(new Uint32Array(6), 1));
  surface.boundsTree = { _roots: [new ArrayBuffer(64), new ArrayBuffer(32)], _indirectBuffer: new Uint16Array(2) };
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
  assert.equal(totals.bvhBytes, 100);
  assert.equal(totals.memoryPolicy.retainedByCategory.bvh, 100, "triangle permutation participates in admission");
  assert.equal(totals.bvhGeometries, 1);
  assert.equal(totals.displayCpuBytes, totals.surfaceBytes + totals.edgeBytes);
  assert.equal(totals.gpuEstimatedBytes, totals.surfaceBytes + totals.edgeBytes);
  assert.equal(totals.memoryPolicy.hardRssCap, false);
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
  assert.equal(totals.gpuEstimatedBytes, totals.surfaceBytes + totals.pickBytes);
});

test("surface instances and packed deformation backing buffers are admitted", () => {
  const shared = geometry(2);
  const records = [0, 1].map(() => ({
    mesh: new THREE.Mesh(shared, new THREE.MeshStandardMaterial())
  }));
  const instance = new THREE.InstancedMesh(
    shared,
    new THREE.MeshStandardMaterial(),
    2
  );
  instance.setColorAt(0, new THREE.Color("white"));
  instance.setColorAt(1, new THREE.Color("white"));
  const packed = new ArrayBuffer(128);
  records[0].tubeDeformationState = {
    mapping: [new Uint8Array(packed, 16, 8)]
  };

  const directTotals = renderMemoryAccounting({
    displayRecords: records,
    cadSurfaceInstanceSets: new Set([{ object: instance, records }])
  });
  const totals = renderMemoryAccounting({
    displayRecords: records,
    cadScene: { runtime: { cadSurfaceInstanceSets: new Set([{ object: instance, records }]) } }
  });

  const instanceBytes = instance.instanceMatrix.array.byteLength + instance.instanceColor.array.byteLength;
  assert.equal(directTotals.surfaceInstanceBytes, instanceBytes, "focused callers keep the direct runtime shape");
  assert.equal(totals.surfaceInstanceSets, 1);
  assert.equal(totals.surfaceInstances, 2);
  assert.equal(totals.surfaceInstanceBytes, instanceBytes);
  assert.equal(totals.deformationBytes, packed.byteLength, "a short view retains its full backing allocation");
  assert.equal(totals.materials, 3, "the instance draw's cloned material is owned too");
  assert.equal(totals.displayCpuBytes, totals.surfaceBytes + totals.edgeBytes);
  assert.ok(totals.memoryPolicy.retainedByCategory.displayCpu >= instanceBytes);
});

test("display CPU admission retains whole packed buffers without inflating GPU uploads", () => {
  const packed = new ArrayBuffer(1024);
  const positions = new Float32Array(packed, 64, 9);
  const indices = new Uint32Array(packed, 128, 3);
  const unusedEdges = new Float32Array(12);
  const sourceMesh = { vertices: positions, indices, cadEdgePositions: unusedEdges };
  const surface = new THREE.BufferGeometry();
  surface.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  surface.setIndex(new THREE.BufferAttribute(indices, 1));
  const mesh = new THREE.Mesh(surface, new THREE.MeshBasicMaterial());
  // This selector view is already retained by the displayed packed buffer.
  mesh.userData.faceIds = new Uint32Array(packed, 192, 1);
  const record = { mesh, sourcePart: { sourceMesh } };
  const totals = renderMemoryAccounting({ displayRecords: [record, record] });
  assert.equal(totals.displayCpuBytes, packed.byteLength + unusedEdges.byteLength);
  assert.equal(totals.gpuEstimatedBytes, positions.byteLength + indices.byteLength);
  assert.equal(totals.selectorCpuBytes, 0, "shared backing has one CPU owner");
  assert.equal(totals.memoryPolicy.retainedByCategory.displayCpu, totals.displayCpuBytes);

  const pending = componentMemoryAccounting({ first: sourceMesh, second: sourceMesh });
  assert.equal(pending.displayCpuBytes, totals.displayCpuBytes);
  assert.equal(pending.gpuInputBytes, positions.byteLength + indices.byteLength + unusedEdges.byteLength);
  assert.equal(pending.buffers.size, 2);
});

test("packed picking buffers are counted once independently of displayed geometry", () => {
  const packed = new ArrayBuffer(2048);
  const pick = new THREE.BufferGeometry();
  pick.setAttribute("position", new THREE.BufferAttribute(new Float32Array(packed, 0, 9), 3));
  pick.setIndex(new THREE.BufferAttribute(new Uint32Array(packed, 64, 3), 1));
  const facePickMesh = new THREE.Mesh(pick, new THREE.MeshBasicMaterial());
  facePickMesh.userData.faceIds = new Uint32Array(packed, 96, 1);
  const totals = renderMemoryAccounting({ facePickMesh });
  assert.equal(totals.displayCpuBytes, 0);
  assert.equal(totals.selectorCpuBytes, packed.byteLength);
  assert.equal(totals.memoryPolicy.retainedByCategory.selectors, packed.byteLength);
  assert.equal(totals.gpuEstimatedBytes, 48);
});

test("component accounting follows composed source meshes and shares backing across parts", () => {
  const packed = new ArrayBuffer(256);
  const first = { vertices: new Float32Array(packed, 0, 9) };
  const second = { indices: new Uint32Array(packed, 64, 3) };
  const composed = { parts: [{ sourceMesh: first }, { sourceMesh: first }, { sourceMesh: second }] };
  const totals = componentMemoryAccounting({ composed, first });
  assert.equal(totals.displayCpuBytes, 256);
  assert.equal(totals.gpuInputBytes, 48);
  assert.equal(totals.buffers.size, 1);
  assert.equal(componentMemoryAccounting(null).displayCpuBytes, 0);
});

test("edge texture views retain full CPU backing and share component texture ownership", () => {
  const packedSegments = new ArrayBuffer(512);
  const packedInstances = new ArrayBuffer(256);
  const segmentData = new Float32Array(packedSegments, 64, 8);
  const instanceData = new Float32Array(packedInstances, 32, 16);
  const segments = { texture: { image: { data: segmentData } }, byteLength: segmentData.byteLength };
  const makeSet = () => ({ segments, instanceData, instanceByteLength: instanceData.byteLength, materials: [] });
  const totals = renderMemoryAccounting({ cadEdgeInstanceSets: new Set([makeSet(), makeSet()]) });
  assert.equal(totals.edgeBytes, segmentData.byteLength + 2 * instanceData.byteLength);
  assert.equal(totals.displayCpuBytes, packedSegments.byteLength + packedInstances.byteLength);
  assert.equal(totals.gpuEstimatedBytes, totals.edgeBytes);
});

test("uncached whole-scene edge inputs and private color baselines remain CPU owners", () => {
  const surface = geometry(1);
  const edgeInputs = new Float32Array(12);
  const rawColors = new Float32Array(9);
  const record = { mesh: new THREE.Mesh(surface, new THREE.MeshBasicMaterial()), rawColors };
  const source = { vertices: surface.attributes.position.array, indices: surface.index.array, cadEdgePositions: edgeInputs };
  const totals = renderMemoryAccounting({ displayRecords: [record], cadScene: { meshData: source } });
  assert.equal(totals.displayCpuBytes, totals.surfaceBytes + edgeInputs.byteLength + rawColors.byteLength);
  assert.equal(totals.gpuEstimatedBytes, totals.surfaceBytes);
  const next = renderMemoryAccounting({ displayRecords: [] });
  assert.equal(next.displayCpuBytes, 0, "dropped owners release their CPU charge");
});

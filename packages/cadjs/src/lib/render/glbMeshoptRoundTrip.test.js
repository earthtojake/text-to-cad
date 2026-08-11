// A render-preset GLB must survive the loader the CAD Viewer actually uses.
//
// `EXT_meshopt_compression` is a REQUIRED extension: without the decoder registered,
// GLTFLoader rejects the file outright rather than degrading, so every render-artifact
// package would fail to open. This test writes a compressed GLB with the real encoder and
// reads it back through `buildMeshDataFromGlbBuffer` -- the same entry point the main thread
// and the GLB worker both use -- so a missing or mis-registered decoder fails here rather
// than in the viewer.

import assert from "node:assert/strict";
import test from "node:test";

import { MeshoptEncoder } from "meshoptimizer";
import { writeGlb } from "implicitjs/glb/writeGlb.js";

import { buildMeshDataFromGlbBuffer } from "./glbMeshData.js";

/** A unit cube as a non-indexed triangle soup (12 triangles). */
function cubeSoup() {
  const v = [
    [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
    [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
  ];
  const faces = [
    [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
    [0, 4, 5], [0, 5, 1], [1, 5, 6], [1, 6, 2],
    [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0],
  ];
  const positions = new Float32Array(faces.length * 9);
  faces.forEach((face, index) => {
    face.forEach((corner, slot) => {
      positions.set(v[corner], index * 9 + slot * 3);
    });
  });
  return positions;
}

async function renderPresetGlb() {
  await MeshoptEncoder.ready;
  return writeGlb(
    { primitives: [{ positions: cubeSoup(), color: "#3366cc", name: "cube" }], name: "cube" },
    { preset: "render", encoder: MeshoptEncoder }
  );
}

test("a render-preset GLB declares EXT_meshopt_compression as required", async () => {
  const bytes = await renderPresetGlb();
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const jsonLength = view.getUint32(12, true);
  const json = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + jsonLength)));
  assert.ok(
    (json.extensionsRequired || []).includes("EXT_meshopt_compression"),
    "the render preset must actually compress -- otherwise this test proves nothing"
  );
});

test("buildMeshDataFromGlbBuffer decodes a meshopt-compressed render artifact", async () => {
  const bytes = await renderPresetGlb();
  const meshData = await buildMeshDataFromGlbBuffer(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
  );
  // 12 triangles survive the weld/quantize/compress round trip.
  assert.equal(meshData.indices.length, 36);
  assert.ok(meshData.vertices.length > 0);
  // Quantization carries placement on the NODE (scale + translation), so decoded world
  // bounds must be the real cube rather than the raw SHORT range -- a dropped node
  // transform would show up here as bounds of ±32767. The loader also converts glTF metres
  // to CAD millimetres (GLB_CAD_UNIT_SCALE), so the 1-unit cube lands at 1000 mm; asserting
  // the scaled value pins that conversion at the same time.
  const { min, max } = meshData.bounds;
  for (let axis = 0; axis < 3; axis += 1) {
    assert.ok(Math.abs(min[axis] - 0) < 1, `min[${axis}] ${min[axis]} should be ~0 mm`);
    assert.ok(Math.abs(max[axis] - 1000) < 1, `max[${axis}] ${max[axis]} should be ~1000 mm`);
  }
});

test("render-preset normals survive quantization + meshopt as UNIT vectors", async () => {
  // The regression this pins. Attribute buffers must be padded to their declared stride
  // PER ELEMENT (VEC3/SHORT -> 8, VEC3/BYTE -> 4), not just at the tail: handing
  // encodeVertexBuffer fewer bytes than count*stride decodes as corrupted attributes.
  // Positions degrade gracefully enough to keep a recognisable silhouette, so the failure
  // shows up as NORMALS -- a shattered, facet-noise surface. Asserting indices and bounds
  // (as this file originally did) does not catch it; unit-length normals do.
  const bytes = await renderPresetGlb();
  const meshData = await buildMeshDataFromGlbBuffer(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
  );
  const normals = meshData.normals;
  assert.ok(normals && normals.length > 0, "the render preset must emit normals");
  let offBy = 0;
  for (let i = 0; i < normals.length; i += 3) {
    const magnitude = Math.hypot(normals[i], normals[i + 1], normals[i + 2]);
    // BYTE quantization costs at most ~0.7% of magnitude on a unit vector.
    if (Math.abs(magnitude - 1) > 0.02) {
      offBy += 1;
    }
  }
  assert.equal(offBy, 0, `${offBy} of ${normals.length / 3} normals are not unit length`);
});

test("an uncompressed export-preset GLB still loads with no decoder involvement", async () => {
  const bytes = writeGlb(
    { primitives: [{ positions: cubeSoup(), color: "#cc3366" }], name: "cube" },
    { preset: "export" }
  );
  const meshData = await buildMeshDataFromGlbBuffer(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
  );
  assert.equal(meshData.indices.length, 36);
});

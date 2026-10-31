// A meshopt-compressed GLB must survive the loader the CAD Viewer actually uses.
//
// `EXT_meshopt_compression` is a REQUIRED extension: without the decoder registered,
// GLTFLoader rejects the file outright rather than degrading, so a compressed GLB a person
// opens would fail to. This test reads one (`fixtures/cube.meshopt.glb`: a unit cube, welded,
// quantized and compressed; `fixtures/README.md` says how it was made) through
// `buildMeshDataFromGlbBuffer` -- the same entry point the main thread and the GLB worker
// both use -- so a missing or mis-registered decoder fails here rather than in the viewer.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildMeshDataFromGlbBuffer } from "./glbMeshData.js";

function fixture(name) {
  const bytes = readFileSync(new URL(`./fixtures/${name}`, import.meta.url));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

test("the compressed sample declares EXT_meshopt_compression as required", () => {
  const bytes = new Uint8Array(fixture("cube.meshopt.glb"));
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const jsonLength = view.getUint32(12, true);
  const json = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + jsonLength)));
  assert.ok(
    (json.extensionsRequired || []).includes("EXT_meshopt_compression"),
    "the sample must actually be compressed -- otherwise this test proves nothing"
  );
});

test("buildMeshDataFromGlbBuffer decodes a meshopt-compressed GLB", async () => {
  const meshData = await buildMeshDataFromGlbBuffer(fixture("cube.meshopt.glb"));
  // 12 triangles survive the weld/quantize/compress round trip.
  assert.equal(meshData.indices.length, 36);
  assert.ok(meshData.vertices.length > 0);
  // Quantization carries placement on the NODE (scale + translation), so decoded world
  // bounds must be the real cube rather than the raw SHORT range -- a dropped node
  // transform would show up here as bounds of ±32767. The loader also converts glTF metres
  // to CAD millimetres (GLB_CAD_UNIT_SCALE), so the 1-unit cube lands at 1000 mm; asserting
  // the scaled value pins that conversion at the same time.
  //
  // The cube spans 0..1 in glTF's frame, which the file declares Y-up (`cadUpAxis`), so the
  // loader also applies the Y-up -> CAD Z-up correction (x, y, z) -> (x, -z, y): the corner
  // at the CAD origin keeps X and Z positive and puts Y NEGATIVE. Asserting 0..1000 on all
  // three axes only passed while that correction was being wrongly skipped for any file
  // carrying occurrence ids.
  const { min, max } = meshData.bounds;
  const expectedMin = [0, -1000, 0];
  const expectedMax = [1000, 0, 1000];
  for (let axis = 0; axis < 3; axis += 1) {
    assert.ok(
      Math.abs(min[axis] - expectedMin[axis]) < 1,
      `min[${axis}] ${min[axis]} should be ~${expectedMin[axis]} mm`
    );
    assert.ok(
      Math.abs(max[axis] - expectedMax[axis]) < 1,
      `max[${axis}] ${max[axis]} should be ~${expectedMax[axis]} mm`
    );
  }
});

test("quantized, compressed normals decode as UNIT vectors", async () => {
  // Corrupted attributes keep a recognisable silhouette, so a decode that goes wrong shows up
  // as NORMALS -- a shattered, facet-noise surface. Indices and bounds do not catch it;
  // unit-length normals do.
  const meshData = await buildMeshDataFromGlbBuffer(fixture("cube.meshopt.glb"));
  const normals = meshData.normals;
  assert.ok(normals && normals.length > 0, "the sample carries normals");
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

test("an uncompressed GLB, cadgen's own, loads through the same entry point", async () => {
  // Two boxes, 12 triangles each.
  const meshData = await buildMeshDataFromGlbBuffer(fixture("pair.glb"));
  assert.equal(meshData.indices.length, 72);
});

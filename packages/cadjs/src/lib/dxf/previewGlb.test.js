// The DXF bake, end to end in JS: parse -> mesh -> render-preset GLB -> the loader the CAD
// Viewer actually uses.
//
// This is the round trip the whole phase rests on. `preview.glb` is written with
// EXT_meshopt_compression, which is a REQUIRED extension: if the bake and the loader disagree
// about anything -- the decoder, the node transform quantization writes, the unit scale --
// the viewport shows nothing at all, and the package still validates as ready. So the test
// asserts geometry that came back out, not just that bytes were produced.

import assert from "node:assert/strict";
import test from "node:test";

import { MeshoptEncoder } from "meshoptimizer";

import { buildMeshDataFromGlbBuffer } from "../render/glbMeshData.js";
import { parseDxf } from "./parseDxf.js";
import {
  buildDxfPreviewGlb,
  DXF_PREVIEW_REFERENCE_THICKNESS_MM,
  dxfPreviewPositions,
} from "./previewGlb.js";

// The bake is parameter-free: the prism is stored at the reference thickness and scaled at
// render time, so this is what comes back rather than any caller's choice.
const THICKNESS_MM = DXF_PREVIEW_REFERENCE_THICKNESS_MM;

/** A 40x20 closed rectangle on the CUT layer, as a real DXF document. */
function rectangleDxf() {
  return `${[
    "0", "SECTION",
    "2", "ENTITIES",
    "0", "LWPOLYLINE",
    "8", "CUT",
    "90", "4",
    "70", "1",
    "10", "0", "20", "0",
    "10", "40", "20", "0",
    "10", "40", "20", "20",
    "10", "0", "20", "20",
    "0", "ENDSEC",
    "0", "EOF",
  ].join("\n")}\n`;
}

async function bake() {
  await MeshoptEncoder.ready;
  return buildDxfPreviewGlb(parseDxf(rectangleDxf(), { fileRef: "rect.dxf" }), {
    encoder: MeshoptEncoder,
    name: "rect.dxf",
  });
}

test("preview positions are the triangle soup in glTF metres, rotated to CAD Z-up", () => {
  const meshData = {
    vertices: new Float32Array([0, 0, 0, 1000, 0, 0, 0, 1000, 0, 7, 7, 7]),
    indices: new Uint32Array([0, 1, 2]),
  };
  const positions = dxfPreviewPositions(meshData);
  // Three corners, nine floats -- the trailing (edge-overlay) vertex is dropped because it
  // is not referenced by a triangle.
  assert.equal(positions.length, 9);
  // (x, y, z) -> (x, z, -y). The mesher builds Y-up; this GLB carries cadOccurrenceId extras,
  // which the viewer's loader reads as "already CAD space", so it must leave here Z-up or the
  // drawing stands on its edge in the scene.
  assert.deepEqual([...positions].map((v) => v + 0), [0, 0, 0, 1, 0, 0, 0, 0, -1]);
});

test("the CAD Z-up rotation does not mirror the part", () => {
  // (x, z, y) would map the axes just as plausibly and has determinant -1, silently flipping
  // every asymmetric profile. Feed the three unit axes and require a right-handed basis.
  const meshData = {
    vertices: new Float32Array([1000, 0, 0, 0, 1000, 0, 0, 0, 1000]),
    indices: new Uint32Array([0, 1, 2]),
  };
  const p = [...dxfPreviewPositions(meshData)];
  const [ax, ay, az, bx, by, bz, cx, cy, cz] = p;
  const determinant = ax * (by * cz - bz * cy)
    - ay * (bx * cz - bz * cx)
    + az * (bx * cy - by * cx);
  assert.equal(Math.round(determinant), 1);
});

test("an empty flat pattern fails loudly rather than baking an empty GLB", () => {
  assert.throws(
    () => dxfPreviewPositions({ vertices: new Float32Array(0), indices: new Uint32Array(0) }),
    /no triangles/u
  );
});

test("a baked DXF preview declares meshopt compression and reloads through the viewer loader", async () => {
  const { bytes, stats } = await bake();
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const jsonLength = view.getUint32(12, true);
  const json = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + jsonLength)));
  assert.ok((json.extensionsRequired || []).includes("EXT_meshopt_compression"));

  const meshData = await buildMeshDataFromGlbBuffer(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
  );
  // A closed rectangular slab: 2 faces + 4 walls, two triangles each.
  assert.equal(stats.triangleCount, 12);
  assert.equal(meshData.indices.length, 36);
  assert.equal(meshData.parts.length, 1);
  assert.equal(meshData.parts[0].occurrenceId, "dxf:0");
});

test("the reloaded preview is the drawing at millimetre scale", async () => {
  const { bytes } = await bake();
  const meshData = await buildMeshDataFromGlbBuffer(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
  );
  // Written in metres, read back in millimetres: the 40x20 outline extruded to 2 mm, with
  // thickness on Z now that the preview is written CAD Z-up. A dropped unit scale or a
  // dropped node transform would show up here as 1000x or as the raw SHORT quantization
  // range; a lost rotation would show up as the thickness landing on Y again.
  const { min, max } = meshData.bounds;
  const expectedMin = [0, 0, -THICKNESS_MM / 2];
  const expectedMax = [40, 20, THICKNESS_MM / 2];
  for (let axis = 0; axis < 3; axis += 1) {
    assert.ok(
      Math.abs(min[axis] - expectedMin[axis]) < 0.05,
      `min[${axis}] ${min[axis]} should be ~${expectedMin[axis]} mm`
    );
    assert.ok(
      Math.abs(max[axis] - expectedMax[axis]) < 0.05,
      `max[${axis}] ${max[axis]} should be ~${expectedMax[axis]} mm`
    );
  }
});

// An implicit render package must be loadable by the viewer, end to end.
//
// The implicit builder bakes a model with the implicitjs mesher and writes it with the shared
// `writeGlb` render preset; the CAD Viewer reads it with `buildMeshDataFromGlbBuffer`. Those
// two live in different packages and neither imports the other, so nothing but this test
// pins that what the builder writes is what the viewer can open -- and the failure mode it
// guards is total: a required extension the loader cannot decode, or a unit convention off by
// 1000, yields an empty or absurd viewport rather than a warning.
//
// It stops short of spawning the builder: the process/lock/NDJSON half is covered by
// tests/python/packages/cadgen/test_implicit_artifact.py against the real child. What is
// verified here is the geometry contract.

import assert from "node:assert/strict";
import test from "node:test";

import { MeshoptEncoder } from "meshoptimizer";
import { meshImplicitCadModel } from "implicitjs/mesh";
import { normalizeImplicitCadModel } from "implicitjs/model";
import { buildImplicitRenderGlb } from "implicitjs/lib/implicitCad/renderGlb.js";

import { buildMeshDataFromGlbBuffer } from "./glbMeshData.js";

const MODEL = {
  name: "implicit package round trip",
  units: "mm",
  bounds: 12,
  glsl: `
    float sdf(vec3 p) {
      return max(length(p) - 8.0, p.z - 3.0);
    }
    vec3 color(vec3 p, vec3 normal) {
      return vec3(0.25, 0.5, 0.75);
    }
  `,
};

async function bakePackageGlb() {
  await MeshoptEncoder.ready;
  const model = normalizeImplicitCadModel(MODEL);
  const mesh = meshImplicitCadModel(model, { resolution: 12, smoothNormals: true });
  const baked = buildImplicitRenderGlb(mesh, { model, encoder: MeshoptEncoder });
  return { ...baked, mesh };
}

test("a baked implicit package loads through the viewer's GLB reader", async () => {
  const { bytes, mesh, stats } = await bakePackageGlb();
  const data = await buildMeshDataFromGlbBuffer(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
  );

  assert.equal(data.indices.length / 3, mesh.triangleCount, "every triangle survives");
  assert.equal(data.parts.length, 1, "one primitive, one part");
  assert.equal(data.parts[0].occurrenceId, "implicit-cad:0");
  assert.ok(data.has_source_colors, "the baked display colour reaches the viewer");
  // The bake now writes the model's color() PER VERTEX (COLOR_0) and turns the material
  // white so three's vertex-colour multiply shows the pattern, not pattern-times-average.
  // The de-indexed colour array must cover every vertex, or the viewer silently drops it.
  assert.equal(data.sourceColor, "#ffffff");
  assert.equal(data.colors.length, data.vertices.length, "COLOR_0 must survive de-indexing");
  assert.ok(data.colors.some((value) => value > 0 && value < 1), "colours should be a real pattern");
  // The reader de-indexes, so the part carries three vertices per triangle while the package
  // stored the welded count -- the welding the render preset does is real, and is what the
  // package's size depends on.
  assert.equal(data.parts[0].vertexCount, mesh.triangleCount * 3);
  assert.ok(stats.vertexCount < data.parts[0].vertexCount);
});

test("the package's units survive the round trip", async () => {
  const { bytes, mesh } = await bakePackageGlb();
  const data = await buildMeshDataFromGlbBuffer(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
  );
  // The writer scales millimetres to glTF metres and the reader multiplies by 1000 on the way
  // back in. Getting either half wrong loads the model at 1000x (or 1/1000th) its size, which
  // is the single most likely mistake in a new baked format and is invisible in the bytes.
  let expectedMax = -Infinity;
  for (let index = 0; index < mesh.positions.length; index += 3) {
    expectedMax = Math.max(expectedMax, mesh.positions[index]);
  }
  // Quantization is 16-bit over the primitive's own bounds, so agreement is close but not
  // exact; a unit error would be off by three orders of magnitude, not by a quantization step.
  assert.ok(
    Math.abs(data.bounds.max[0] - expectedMax) < Math.abs(expectedMax) * 0.001,
    `expected ~${expectedMax} mm, got ${data.bounds.max[0]}`
  );
});

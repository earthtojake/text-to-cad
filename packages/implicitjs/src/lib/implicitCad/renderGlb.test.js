import assert from "node:assert/strict";
import test from "node:test";

import { MeshoptEncoder } from "meshoptimizer";

import { meshImplicitCadModel } from "./mesh.js";
import { normalizeImplicitCadModel } from "./model.js";
import {
  IMPLICIT_MM_TO_GLB_SCALE,
  buildImplicitExportGlb,
  buildImplicitRenderGlb,
  implicitDisplayColor,
  positionBounds,
  weldImplicitMesh,
} from "./renderGlb.js";

const MODEL = {
  name: "render glb test shape",
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

function bakedMesh() {
  return meshImplicitCadModel(MODEL, { resolution: 12, smoothNormals: true });
}

function glbJson(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const jsonLength = view.getUint32(12, true);
  return JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + jsonLength)));
}

test("welding happens in model units, and the scale is applied afterwards", () => {
  const mesh = bakedMesh();
  const welded = weldImplicitMesh(mesh);
  assert.ok(welded.positions.length < mesh.positions.length, "welding must remove duplicates");
  assert.equal(welded.indices.length, mesh.positions.length / 3);
  for (let index = 0; index < welded.positions.length; index += 1) {
    // Scaling before welding would divide the weld tolerance along with the coordinates.
    assert.ok(
      Math.abs(welded.positions[index] - welded.unscaled[index] * IMPLICIT_MM_TO_GLB_SCALE) < 1e-9
    );
  }
});

test("the render preset is quantized, compressed, and in glTF metres", async () => {
  await MeshoptEncoder.ready;
  const mesh = bakedMesh();
  const model = normalizeImplicitCadModel(MODEL);
  const { bytes, stats, bounds } = buildImplicitRenderGlb(mesh, { model, encoder: MeshoptEncoder });
  const json = glbJson(bytes);
  assert.deepEqual(
    [...json.extensionsRequired].sort(),
    ["EXT_meshopt_compression", "KHR_mesh_quantization"]
  );
  assert.equal(json.nodes.length, 1);
  assert.equal(json.nodes[0].extras.cadOccurrenceId, "implicit-cad:0");
  assert.equal(json.nodes[0].extras.cadUnits, "mm");
  // The descriptor's bbox describes the MODEL, so it stays in the model's own units even
  // though the payload is in metres.
  assert.ok(bounds.max[0] > 1, `model-unit bounds, got ${JSON.stringify(bounds)}`);
  assert.deepEqual(bounds, positionBounds(weldImplicitMesh(mesh).unscaled));
  assert.equal(stats.triangleCount, mesh.triangleCount);
  assert.ok(stats.bytes > 0);
});

test("the export preset stays openable by a loader with no decoder", () => {
  const mesh = bakedMesh();
  const model = normalizeImplicitCadModel(MODEL);
  const json = glbJson(buildImplicitExportGlb(mesh, { model }));
  // The sibling `<name>.glb` a user asks for with --write must not require an extension: a
  // slicer that cannot read EXT_meshopt_compression would simply refuse the file.
  assert.equal(json.extensionsRequired, undefined);
  const positions = json.accessors[json.meshes[0].primitives[0].attributes.POSITION];
  assert.equal(positions.componentType, 5126, "export positions stay float");
  // ... and in model units, which is what every other exporter writes.
  assert.ok(Math.max(...positions.max) > 1);
});

test("the display colour averages the model's colour field", () => {
  const mesh = bakedMesh();
  const model = normalizeImplicitCadModel(MODEL);
  assert.equal(implicitDisplayColor(model, mesh.positions), "#4080bf");
});

test("a model whose colour source cannot be evaluated still gets a colour", () => {
  // Geometry must never be lost to a colour failure: a model with an unparseable colour
  // function bakes in the colour its material declares rather than failing the build.
  const mesh = bakedMesh();
  const model = { ...normalizeImplicitCadModel(MODEL), colorSource: "vec3 color(" };
  assert.equal(implicitDisplayColor(model, mesh.positions), model.material.color);
  // A model with no colour function at all takes the same fallback, without going near the
  // evaluator.
  const plain = { ...normalizeImplicitCadModel(MODEL), colorSource: "" };
  assert.equal(implicitDisplayColor(plain, mesh.positions), plain.material.color);
});

test("an empty mesh is an error, not an empty package", () => {
  assert.throws(
    () => buildImplicitRenderGlb({ positions: new Float32Array() }, { model: null }),
    /no triangles/
  );
});

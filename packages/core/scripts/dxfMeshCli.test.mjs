// bin/dxf-mesh.mjs is the snapshot mesher: DXF text on stdin, one GLB out, which
// cadgen then renders through the ORDINARY glb path (snapshot_cli.resolve_drawing_render_job).
// That makes the drawing's orientation a property of the round trip, not of either half:
// the script pre-rotates its positions into CAD Z-up (dxfSoupToGlbPositions) and must
// declare that, or the reader applies its Y-up correction on top and stands the sheet on
// its edge — the failure the previewGlb.js header describes, reintroduced from the other
// side once the reader stopped inferring the space from cadOccurrenceId.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { buildMeshDataFromGlbBuffer } from "../src/lib/render/glbMeshData.js";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MESHER = path.join(packageRoot, "bin", "dxf-mesh.mjs");

/** A closed 40 x 20 mm rectangle as one LWPOLYLINE — the smallest cuttable contour. */
const RECTANGLE_DXF = [
  "0", "SECTION", "2", "ENTITIES",
  "0", "LWPOLYLINE", "8", "0", "90", "4", "70", "1",
  "10", "0.0", "20", "0.0",
  "10", "40.0", "20", "0.0",
  "10", "40.0", "20", "20.0",
  "10", "0.0", "20", "20.0",
  "0", "ENDSEC", "0", "EOF", "",
].join("\n");

function meshDxf(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "dxf-mesh-cli-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const out = path.join(dir, "plate.glb");
  const stdout = execFileSync(process.execPath, [MESHER, "--out", out, "--name", "plate"], {
    input: RECTANGLE_DXF,
    encoding: "utf8",
  });
  assert.equal(JSON.parse(stdout.trim().split("\n").pop()).ok, true);
  return fs.readFileSync(out);
}

test("the drawing mesher declares CAD Z-up, because its positions already are", (t) => {
  const bytes = meshDxf(t);
  const jsonLength = bytes.readUInt32LE(12);
  const gltf = JSON.parse(bytes.subarray(20, 20 + jsonLength).toString("utf8"));
  assert.ok(gltf.nodes.length > 0);
  for (const node of gltf.nodes) {
    assert.equal(node.extras?.cadUpAxis, "z", `node ${node.name} must declare its space`);
  }
});

test("a meshed drawing loads FLAT: the reference thickness stays on Z", async (t) => {
  const bytes = meshDxf(t);
  const meshData = await buildMeshDataFromGlbBuffer(
    bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
  );
  const size = [0, 1, 2].map((axis) => meshData.bounds.max[axis] - meshData.bounds.min[axis]);
  // The sheet is 40 x 20 mm at DXF_PREVIEW_REFERENCE_THICKNESS_MM = 1 mm.
  const expected = [40, 20, 1];
  size.forEach((value, axis) => assert.ok(
    Math.abs(value - expected[axis]) < 1e-3,
    `axis ${axis}: ${value} mm, expected ${expected[axis]} mm — the sheet came back on its edge`,
  ));
});

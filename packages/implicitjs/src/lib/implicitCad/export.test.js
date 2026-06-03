import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  exportImplicitCadAnimatedGlb,
  exportImplicitCadFile,
  exportImplicitCadModel,
} from "./export.js";

const sphereModel = {
  schema: "implicit.js/0.1.0",
  name: "export sphere",
  bounds: [[-8, -8, -8], [8, 8, 8]],
  glsl: `
float sdf(vec3 p) { return implicit_sphere(p, vec3(0.0), 5.0); }
vec3 color(vec3 p, vec3 normal) { return vec3(0.53, 0.80, 1.0); }
`,
};

function parseGlbJson(buffer) {
  assert.equal(buffer.toString("utf-8", 0, 4), "glTF");
  assert.equal(buffer.readUInt32LE(4), 2);
  assert.equal(buffer.readUInt32LE(16), 0x4e4f534a);
  const jsonLength = buffer.readUInt32LE(12);
  return JSON.parse(buffer.toString("utf-8", 20, 20 + jsonLength).trim());
}

test("exportImplicitCadModel writes GLB, STL, and 3MF buffers", () => {
  for (const format of ["glb", "stl", "3mf"]) {
    const result = exportImplicitCadModel(sphereModel, { format, resolution: 12 });
    assert.equal(result.format, format);
    assert.ok(result.body.length > 100);
    assert.ok(result.mesh.triangleCount > 0);
    if (format === "glb") {
      assert.equal(result.body.toString("utf-8", 0, 4), "glTF");
    }
    if (format === "3mf") {
      assert.equal(result.body.readUInt32LE(0), 0x04034b50);
      assert.ok(result.body.includes(Buffer.from('displaycolor="#87CCFFFF"')));
    }
  }
});

test("exportImplicitCadModel applies parameter values before meshing", () => {
  const result = exportImplicitCadModel({
    schema: "implicit.js/0.1.0",
    name: "param sphere",
    params: {
      radius: { type: "number", min: 2, max: 10, default: 3 }
    },
    bounds: ({ params }) => {
      const radius = params.radius + 1;
      return [[-radius, -radius, -radius], [radius, radius, radius]];
    },
    glsl: "float sdf(vec3 p) { return length(p) - radius; }"
  }, {
    format: "glb",
    params: { radius: 6 },
    resolution: 10,
  });
  assert.equal(result.model.parameterValues.radius, 6);
  assert.equal(result.model.bounds.max[0], 7);
  assert.ok(result.mesh.triangleCount > 0);
});

test("exportImplicitCadFile applies parameter values and writes next to source by default", async () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "implicit-cad-export-"));
  const input = path.join(tempDir, "orb.implicit.js");
  fs.writeFileSync(input, `
export default {
  schema: "implicit.js/0.1.0",
  name: "param orb",
  params: {
    radius: { type: "number", min: 2, max: 8, default: 3 }
  },
  bounds: ({ params }) => [[-params.radius - 2, -params.radius - 2, -params.radius - 2], [params.radius + 2, params.radius + 2, params.radius + 2]],
  glsl: \`float sdf(vec3 p) { return length(p) - radius; }\`
};
`, "utf-8");

  const result = await exportImplicitCadFile({
    input,
    format: "stl",
    params: { radius: 6 },
    resolution: 10,
  });
  assert.equal(result.ok, true);
  assert.equal(result.output, path.join(tempDir, "orb.stl"));
  assert.equal(fs.existsSync(result.output), true);
  assert.ok(result.triangleCount > 0);
});

test("implicit GLB exports include CAD-native millimeter metadata", () => {
  const result = exportImplicitCadModel(sphereModel, { format: "glb", resolution: 12 });
  const json = parseGlbJson(result.body);
  assert.equal(json.nodes[0].extras.cadOccurrenceId, "implicit-cad:0");
  assert.equal(json.nodes[0].extras.cadSourceKind, "implicit-cad");
  assert.equal(json.nodes[0].extras.cadUnits, "mm");
  assert.equal(json.materials[0].extras.cadSourceColor, true);
  assert.deepEqual(json.meshes[0].primitives[0].attributes, { POSITION: 0, NORMAL: 1 });
});

test("implicit animated GLB exports morph target animation", () => {
  const result = exportImplicitCadAnimatedGlb({
    schema: "implicit.js/0.1.0",
    name: "animated sphere",
    params: {
      radius: { type: "number", min: 2, max: 8, default: 4 }
    },
    animations: {
      pulse: {
        duration: 1,
        update({ progress, set }) {
          set("radius", 4 + Math.sin(progress * Math.PI) * 0.75);
        }
      }
    },
    bounds: ({ params }) => [[-params.radius - 2, -params.radius - 2, -params.radius - 2], [params.radius + 2, params.radius + 2, params.radius + 2]],
    glsl: "float sdf(vec3 p) { return length(p) - radius; }"
  }, {
    animationId: "pulse",
    frames: 4,
    resolution: 10,
  });
  assert.equal(result.format, "glb");
  assert.ok(result.body.length > 100);
  const json = parseGlbJson(result.body);
  assert.equal(json.animations.length, 1);
  assert.ok(json.meshes[0].primitives[0].targets.length > 0);
  assert.equal(json.nodes[0].extras.implicitjsAnimated, true);
});

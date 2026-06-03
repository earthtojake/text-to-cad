import assert from "node:assert/strict";
import test from "node:test";

import { meshImplicitCadModel } from "./mesh.js";

const sphereModel = {
  schema: "implicit.js/0.1.0",
  name: "orientation sphere",
  bounds: [[-6, -6, -6], [6, 6, 6]],
  glsl: "float sdf(vec3 p) { return length(p) - 4.0; }",
};

function triangleFacesOutwardFromOrigin(positions, offset) {
  const ax = positions[offset];
  const ay = positions[offset + 1];
  const az = positions[offset + 2];
  const bx = positions[offset + 3];
  const by = positions[offset + 4];
  const bz = positions[offset + 5];
  const cx = positions[offset + 6];
  const cy = positions[offset + 7];
  const cz = positions[offset + 8];
  const ux = bx - ax;
  const uy = by - ay;
  const uz = bz - az;
  const vx = cx - ax;
  const vy = cy - ay;
  const vz = cz - az;
  const nx = uy * vz - uz * vy;
  const ny = uz * vx - ux * vz;
  const nz = ux * vy - uy * vx;
  const mx = (ax + bx + cx) / 3;
  const my = (ay + by + cy) / 3;
  const mz = (az + bz + cz) / 3;
  return nx * mx + ny * my + nz * mz > 0;
}

test("implicit mesh extraction orients closed SDF triangles outward", () => {
  const mesh = meshImplicitCadModel(sphereModel, { resolution: 14 });
  assert.ok(mesh.triangleCount > 0);
  for (let offset = 0; offset < mesh.positions.length; offset += 9) {
    assert.equal(triangleFacesOutwardFromOrigin(mesh.positions, offset), true);
  }
});

test("implicit mesh extraction evaluates shader uniforms", () => {
  const mesh = meshImplicitCadModel({
    schema: "implicit.js/0.1.0",
    name: "uniform sphere",
    params: {
      radius: { type: "number", min: 1, max: 6, default: 4 }
    },
    bounds: [[-6, -6, -6], [6, 6, 6]],
    glsl: "float sdf(vec3 p) { return length(p) - radius; }",
  }, { resolution: 12 });
  assert.ok(mesh.triangleCount > 0);
});

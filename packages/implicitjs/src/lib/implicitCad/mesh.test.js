import assert from "node:assert/strict";
import test from "node:test";

import { meshImplicitCadModel,
  implicitCadGrid,
  sampleFieldPlanes,
  sampledValueCount,
} from "./mesh.js";
import { normalizeImplicitCadModel } from "./model.js";

function internalsForTest() {
  return { createImplicitCadSdfEvaluator: (model) => createImplicitCadSdfEvaluator(normalizeImplicitCadModel(model)) };
}
import { createImplicitCadSdfEvaluator } from "./sdfEvaluator.js";

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

// A field whose zero set is a sphere of radius 10, but whose VALUE is cubic in the radius, so
// it carries no distance information -- the same defect the algebraic models in the corpus
// have (Chmutov, tanglecube), just isolated and with a surface whose exact answer is known.
const nonlinearSphere = {
  schema: "implicit.js/0.1.0",
  name: "nonlinear sphere",
  bounds: [[-14, -14, -14], [14, 14, 14]],
  glsl: "float sdf(vec3 p) { float r = length(p) / 10.0; return r * r * r - 1.0; }",
};

function worstRadialError(positions, radius) {
  let worst = 0;
  for (let index = 0; index < positions.length; index += 3) {
    const distance = Math.hypot(positions[index], positions[index + 1], positions[index + 2]);
    worst = Math.max(worst, Math.abs(distance - radius));
  }
  return worst;
}

test("edge refinement recovers the true surface on a non-distance field", () => {
  const plain = meshImplicitCadModel(nonlinearSphere, { resolution: 24, refineEdges: false });
  const refined = meshImplicitCadModel(nonlinearSphere, { resolution: 24, refineEdges: true });

  const plainError = worstRadialError(plain.positions, 10);
  const refinedError = worstRadialError(refined.positions, 10);

  // Linear interpolation on a cubic field puts vertices measurably off the real sphere; the
  // false-position solve should pull them back by a wide margin, not a marginal one.
  assert.ok(plainError > 0.1, `expected the unrefined mesh to be visibly wrong, got ${plainError}`);
  assert.ok(
    refinedError < plainError / 10,
    `refinement should cut the error by >10x: plain ${plainError}, refined ${refinedError}`
  );
});

function sampleModel(source, resolution = 24) {
  const model = normalizeImplicitCadModel(source);
  const grid = implicitCadGrid(model, { resolution });
  const values = sampleFieldPlanes(
    createImplicitCadSdfEvaluator(model),
    grid,
    new Float32Array(sampledValueCount(grid))
  );
  return { grid, values, sdf: createImplicitCadSdfEvaluator(model) };
}

test("refinement improves a true distance field too, rather than disturbing it", () => {
  // Refinement is unconditional, so it must never make a well-behaved model worse. It does
  // not merely leave a true SDF alone: even an exact distance field is CURVED along an
  // axis-aligned cell edge, so the linear guess is slightly off the sphere and the solve
  // pulls it on. Accuracy is the assertion; "barely moves" would have been the wrong one.
  const plain = meshImplicitCadModel(sphereModel, { resolution: 24, refineEdges: false });
  const refined = meshImplicitCadModel(sphereModel, { resolution: 24, refineEdges: true });
  assert.equal(refined.positions.length, plain.positions.length);
  assert.ok(
    worstRadialError(refined.positions, 4) < worstRadialError(plain.positions, 4),
    `refined ${worstRadialError(refined.positions, 4)} should beat plain ${worstRadialError(plain.positions, 4)}`
  );
});



// A box rotated off every lattice axis: each sharp edge crosses cells diagonally, which is
// the worst case for marching tetrahedra's chamfer. The QEF snap must pull the interior
// vertices onto the true surface -- measured as |sdf| at the emitted vertices, which the
// chamfer inflates by a large fraction of a cell and the snap should cut sharply.
const rotatedBox = {
  schema: "implicit.js/0.1.0",
  name: "rotated box",
  bounds: [[-9, -9, -9], [9, 9, 9]],
  glsl: `
    float sdf(vec3 p) {
      vec3 rx = vec3(0.866025, -0.433013, 0.25);
      vec3 ry = vec3(0.5, 0.75, -0.433013);
      vec3 rz = vec3(0.0, 0.5, 0.866025);
      vec3 q = abs(vec3(dot(rx, p), dot(ry, p), dot(rz, p))) - vec3(4.0, 4.0, 4.0);
      vec3 outside = max(q, vec3(0.0, 0.0, 0.0));
      return length(outside) + min(max(q.x, max(q.y, q.z)), 0.0);
    }
  `,
};

test("feature snapping puts vertices on the true edge line", () => {
  // The chamfer's failure mode is NOT off-surface vertices -- edge refinement puts every
  // vertex on the surface -- it is that no vertex lies near the sharp EDGE, so the bevel
  // facet cuts the corner. Measure the mean distance from points along one true box edge
  // to the nearest mesh vertex: chamfered meshing leaves a gap of a large fraction of a
  // cell; the QEF snap should close most of it.
  const rx = [0.866025, -0.433013, 0.25];
  const ry = [0.5, 0.75, -0.433013];
  const rz = [0, 0.5, 0.866025];
  const edgePoint = (s) => [0, 1, 2].map((k) => 4 * rx[k] + 4 * ry[k] + s * rz[k]);
  // Off-line error only: bucket vertices by their projection along the edge and take the
  // minimum PERPENDICULAR distance per bucket. A naive nearest-vertex metric conflates the
  // spacing BETWEEN snapped vertices with the chamfer gap and undersells a perfect snap.
  const gapTo = (mesh) => {
    const p0 = edgePoint(0);
    const bins = new Array(28).fill(Infinity);
    for (let i = 0; i < mesh.positions.length; i += 3) {
      const dx = mesh.positions[i] - p0[0];
      const dy = mesh.positions[i + 1] - p0[1];
      const dz = mesh.positions[i + 2] - p0[2];
      const along = dx * rz[0] + dy * rz[1] + dz * rz[2];
      if (along < -3.5 || along > 3.5) {
        continue;
      }
      const px = dx - along * rz[0];
      const py = dy - along * rz[1];
      const pz = dz - along * rz[2];
      const perpendicular = Math.hypot(px, py, pz);
      const bin = Math.min(27, Math.floor((along + 3.5) / 0.25));
      bins[bin] = Math.min(bins[bin], perpendicular);
    }
    const filled = bins.filter((v) => Number.isFinite(v));
    return filled.reduce((s, v) => s + v, 0) / filled.length;
  };
  const plain = meshImplicitCadModel(rotatedBox, { resolution: 20, smoothNormals: true, snapFeatures: false });
  const snapped = meshImplicitCadModel(rotatedBox, { resolution: 20, smoothNormals: true, snapFeatures: true });
  assert.equal(snapped.triangleCount, plain.triangleCount, "snapping must not change topology");
  const before = gapTo(plain);
  const after = gapTo(snapped);
  assert.ok(before > 0.08, `expected a visible edge gap without snapping, got ${before}`);
  // Coverage is PARTIAL by design: only existing diagonal crossings may move (cube-edge
  // crossings are shared four ways and pinned), and a diagonal only crosses the surface in
  // ~half the crease cells -- measured ~38% mean gap reduction on this worst-case oblique
  // edge. The bar guards that improvement; closing the rest requires true EMC vertex
  // insertion (a topology change), which is the recorded escalation path.
  assert.ok(after < before * 0.75, `snap should cut the edge gap by >=25%: ${before} -> ${after}`);
});


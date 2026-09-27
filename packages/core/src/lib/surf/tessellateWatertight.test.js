// Phase 1 gates (design/unified-tessellation.md): the tessellated component is
// WATERTIGHT across faces — every model edge's boundary is one shared polyline
// both adjacent faces conform to, with bit-identical vertex coordinates — and
// every boundary vertex lies on the exact edge curve.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { parseSurf } from "./container.js";
import { evaluateCurve3 } from "./evaluate.js";
import { tessellateComponent } from "./tessellate.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));

function loadFixture(name) {
  const buffer = fs.readFileSync(path.join(HERE, "fixtures", `${name}.surf`));
  return parseSurf(buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength));
}

function checkComponent(t, name) {
  const { index, floats } = loadFixture(name);
  const component = tessellateComponent(index, floats, { collectBoundaryDebug: true });
  const { boundaryDebug } = component;
  assert.ok(boundaryDebug?.length, "debug boundary data collected");

  // 1. BIT-IDENTITY: every (edge, fraction) a face pins is at exactly the same
  // coordinates on every face that pins it — the property that makes exported
  // meshes weld by exact coordinate comparison.
  const byKey = new Map();
  for (const dbg of boundaryDebug) {
    for (const [vert, labels] of dbg.boundaryByVert) {
      for (const { ord, f } of labels) {
        const key = `${ord}:${f.toFixed(9)}`;
        let entry = byKey.get(key);
        if (!entry) byKey.set(key, (entry = []));
        entry.push(dbg.xyz[vert]);
      }
    }
  }
  let mismatches = 0;
  for (const entries of byKey.values()) {
    const first = entries[0];
    for (const p of entries) {
      if (p[0] !== first[0] || p[1] !== first[1] || p[2] !== first[2]) mismatches += 1;
    }
  }
  assert.equal(mismatches, 0, `${name}: shared boundary vertices must be bit-identical`);

  // 2. GEOMETRIC CLOSURE: every region-boundary mesh segment (identified by
  // its exact endpoint coordinates) is used by exactly two faces — no
  // T-junctions, no cracks. A closed solid's boundary graph is 2-covered.
  const spans = new Map();
  for (const dbg of boundaryDebug) {
    const counts = new Map();
    const pairKey = (p, q) => (p < q ? p * 4294967296 + q : q * 4294967296 + p);
    for (let t3 = 0; t3 < dbg.triangles.length; t3 += 3) {
      const tri = [dbg.triangles[t3], dbg.triangles[t3 + 1], dbg.triangles[t3 + 2]];
      for (const [p, q] of [[tri[0], tri[1]], [tri[1], tri[2]], [tri[2], tri[0]]]) {
        counts.set(pairKey(p, q), (counts.get(pairKey(p, q)) || 0) + 1);
      }
    }
    for (let t3 = 0; t3 < dbg.triangles.length; t3 += 3) {
      const tri = [dbg.triangles[t3], dbg.triangles[t3 + 1], dbg.triangles[t3 + 2]];
      for (const [p, q] of [[tri[0], tri[1]], [tri[1], tri[2]], [tri[2], tri[0]]]) {
        if (counts.get(pairKey(p, q)) !== 1) continue;
        if (!dbg.boundaryByVert.has(p) || !dbg.boundaryByVert.has(q)) continue;
        const P = dbg.xyz[p];
        const Q = dbg.xyz[q];
        const kp = `${P[0]},${P[1]},${P[2]}`;
        const kq = `${Q[0]},${Q[1]},${Q[2]}`;
        const key = kp < kq ? `${kp}|${kq}` : `${kq}|${kp}`;
        spans.set(key, (spans.get(key) || 0) + 1);
      }
    }
  }
  const uncovered = [...spans.values()].filter((count) => count !== 2).length;
  assert.equal(uncovered, 0, `${name}: every boundary segment must be shared by exactly two faces`);

  // 3. ON-CURVE: boundary vertices lie on the exact model edge (their pinned
  // label's curve), within the curve-sampling resolution of this check.
  const edgesByOrd = new Map(index.edges.map((edge) => [edge.ord, edge]));
  let worst = 0;
  for (const dbg of boundaryDebug) {
    for (const [vert, labels] of dbg.boundaryByVert) {
      const edge = edgesByOrd.get(labels[0].ord);
      if (!edge?.curve) continue;
      const p = dbg.xyz[vert];
      let best = Infinity;
      const [t0, t1] = edge.curve.range;
      const SAMPLES = 2048;
      for (let i = 0; i <= SAMPLES; i += 1) {
        const q = evaluateCurve3(edge.curve, floats, t0 + ((t1 - t0) * i) / SAMPLES);
        const d = Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
        if (d < best) best = d;
      }
      worst = Math.max(worst, best);
    }
  }
  // Bounded by this check's own curve-sampling density plus the shared
  // polyline's chord tolerance; the pinned points themselves are ON the curve.
  const scale = Math.hypot(
    component.bounds.max[0] - component.bounds.min[0],
    component.bounds.max[1] - component.bounds.min[1],
    component.bounds.max[2] - component.bounds.min[2],
  );
  assert.ok(worst <= scale * 1e-3, `${name}: worst boundary-vertex curve distance ${worst} (scale ${scale})`);
}

for (const fixture of ["sun_gear", "mixed"]) {
  test(`${fixture}: tessellation is watertight across faces, on the exact curves`, (t) => {
    checkComponent(t, fixture);
  });
}

// 4. NON-DEGENERACY. Boundary snapping deliberately moves two of a face's
// vertices onto ONE model point; the weld that follows is what turns them back
// into one vertex and drops the triangle that collapsed. When that weld misses,
// the collapsed triangle survives with zero area, and because it still carries
// its edges the mesh stops being manifold — the shape reported in issue #371,
// where a plate with a single cylindrical cut exported edges shared by 4, 5 and
// 7 faces and no computable volume.
//
// The miss used to depend on MESH DENSITY: the weld asked "are these two uv
// points near each other?" against an epsilon scaled off the uv span, so it
// stopped recognizing duplicates as soon as the spacing around a small bore's
// rim outgrew it. That is why these cases run at COARSE chord tolerances — they
// are the ones that reproduce, and a density-dependent weld would fail them
// again. Fine tolerances are covered by the fixtures' default-tolerance runs.
function meshDefects(name, options) {
  const { index, floats } = loadFixture(name);
  const component = tessellateComponent(index, floats, { ...options, collectBoundaryDebug: true });
  const twiceArea = (p, q, r) => {
    const ux = q[0] - p[0], uy = q[1] - p[1], uz = q[2] - p[2];
    const vx = r[0] - p[0], vy = r[1] - p[1], vz = r[2] - p[2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    return Math.sqrt(nx * nx + ny * ny + nz * nz);
  };
  // Keyed by exact position, which is how a mesh consumer welds an exported
  // STL: it is the model's own triangle set that must be sound, not any one
  // face's index space.
  const at = (p) => `${p[0]},${p[1]},${p[2]}`;
  let degenerate = 0;
  let triangles = 0;
  const byCorners = new Map();
  const byEdge = new Map();
  for (const dbg of component.boundaryDebug) {
    for (let t = 0; t < dbg.triangles.length; t += 3) {
      const corners = [
        dbg.xyz[dbg.triangles[t]],
        dbg.xyz[dbg.triangles[t + 1]],
        dbg.xyz[dbg.triangles[t + 2]],
      ];
      triangles += 1;
      if (twiceArea(corners[0], corners[1], corners[2]) === 0) degenerate += 1;
      const keys = corners.map(at);
      const face = [...keys].sort().join("|");
      byCorners.set(face, (byCorners.get(face) || 0) + 1);
      for (const [a, b] of [[keys[0], keys[1]], [keys[1], keys[2]], [keys[2], keys[0]]]) {
        const edge = a < b ? `${a}|${b}` : `${b}|${a}`;
        byEdge.set(edge, (byEdge.get(edge) || 0) + 1);
      }
    }
  }
  return {
    triangles,
    degenerate,
    duplicated: [...byCorners.values()].filter((used) => used > 1).length,
    unshared: [...byEdge.values()].filter((used) => used !== 2).length,
  };
}

for (const [fixture, chordTolerance] of [
  ["sun_gear", undefined],
  ["sun_gear", 2e-2],
  ["mixed", 5e-3],
  ["cam_follower_roller", 2e-2],
]) {
  const label = chordTolerance === undefined ? "default tolerance" : `chord ${chordTolerance}`;
  test(`${fixture} @ ${label}: no degenerate or duplicated triangles, every edge shared by two`, () => {
    const defects = meshDefects(fixture, chordTolerance === undefined ? {} : { chordTolerance });
    assert.ok(defects.triangles > 0, "the fixture tessellates to something");
    assert.equal(defects.degenerate, 0, "a zero-area triangle carries no surface and must not be emitted");
    assert.equal(defects.duplicated, 0, "no triangle may be emitted more than once");
    assert.equal(defects.unshared, 0, "a closed solid's every mesh edge is used by exactly two triangles");
  });
}

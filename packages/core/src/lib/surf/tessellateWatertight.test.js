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
//
// curved_wall_hole is issue #433's part: a 2.2 mm strip of a 90 mm-radius
// wall with one 3.3 mm hole drilled through it. The rim's uv curve on the bore
// is nearly straight and bends AWAY from the face, so earcut built every rim
// cell as a stack of slivers; their refined chords left vertices microns inside
// the rim, and the conformity pass folded triangles over them — one triangle
// emitted twice, edges on four faces. Every tolerance failed somewhere.
//
// half_disc is a half-round puck (a 20 mm-radius cylinder halved through its
// axis, 10 mm thick). Each flat end is bounded by only two model edges, the arc
// and its diameter, so the diameter's two ends lie on both. The conformity pass
// split the diameter, which runs along the line, with the ARC's points, and its
// weld folded that fan into the arc's own vertices: each end came out half
// folded over itself (edges on three triangles, the volume a third short), what
// the hypercar's tub showed as hatched streaks on its rear bulkhead in Render.
function meshDefects(name, options) {
  const { index, floats } = loadFixture(name);
  const component = tessellateComponent(index, floats, { ...options, collectBoundaryDebug: true });
  const twiceArea = (p, q, r) => {
    const ux = q[0] - p[0], uy = q[1] - p[1], uz = q[2] - p[2];
    const vx = r[0] - p[0], vy = r[1] - p[1], vz = r[2] - p[2];
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    return Math.sqrt(nx * nx + ny * ny + nz * nz);
  };
  // Keyed by exact Float32 position, which is what an exported STL carries
  // and how a mesh consumer welds it: it is the model's own triangle set that
  // must be sound, not any one face's index space. Two vertices a double ULP
  // apart are one vertex in the file.
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
      ].map((p) => Array.from(Float32Array.from(p)));
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
  ["mixed", undefined],
  ["mixed", 5e-3],
  ["mixed", 2e-2],
  ["cam_follower_roller", 2e-2],
  ["curved_wall_hole", undefined],
  ["curved_wall_hole", 1e-2],
  ["curved_wall_hole", 2e-2],
  ["half_disc", undefined],
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

// 5. A PLANAR FACE MESHES ONCE OVER, every triangle wound with the face.
//
// plenum_end is the hypercar's intake plenum: a blunt ruled loft whose two end
// faces are each bounded by ONE spline, and that spline closes to 0.18 um, so
// sampleSharedEdge's relative test calls it open although both its ends weld
// into one corner. The seam then carried fraction 1 alone, conformity read the
// mesh edge from the seam to the loop's first point as the whole loop, split it
// with every point of the edge, and the weld folded each end face over itself:
// the streaks and blocks that crawled across the plenum while the showcase played.
// Only its planar faces are held here: the rings between its curved bands are not
// pinned to their shared edge yet, so the solid as a whole is not watertight.
test("plenum_end: a face bounded by one spline that barely closes meshes once over, wound with the face", () => {
  const { index, floats } = loadFixture("plenum_end");
  const { positions, normals, indices, faceRanges } = tessellateComponent(index, floats);
  const planes = index.faces.filter((face) => face.surfaceType === "plane");
  assert.equal(planes.length, 2, "the plenum's two end faces");
  const at = (i) => [positions[3 * i], positions[3 * i + 1], positions[3 * i + 2]];
  for (const face of planes) {
    const range = faceRanges.find((r) => r.ord === face.ord);
    let against = 0;
    let area = 0;
    for (let i = range.indexStart; i < range.indexStart + range.indexCount; i += 3) {
      const [a, b, c] = [at(indices[i]), at(indices[i + 1]), at(indices[i + 2])];
      const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
      const v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
      const n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
      const k = 3 * indices[i];
      const signed = 0.5 * (n[0] * normals[k] + n[1] * normals[k + 1] + n[2] * normals[k + 2]);
      if (signed < 0) against += 1;
      area += signed;
    }
    assert.equal(against, 0, `face ${face.ord}: no triangle wound against the face`);
    assert.ok(Math.abs(area - face.area) <= face.area * 0.02, `face ${face.ord}: meshed ${area} mm2 of ${face.area}`);
  }
});

// 6. AN EDGE SHORTER THAN ITS FLOAT32 KNOTS meshes as the point it is.
//
// The w16's intercooler lids are boolean results whose straight seams are split by edges a fifth of
// a micron long, at parameters around 242 along the line they lie on. The index keeps such an edge's
// range in doubles, but its pcurve's knots are Float32, and both ends round to 242: a domain of one
// point, where every basis denominator is zero, so every uv the pcurve gave was NaN. The planar face
// holding it then lost the labels of the edge before it and conformity threw ("Cannot read
// properties of undefined (reading 'filter')"), stopping the whole engine at 120 of its 777 parts.
// Here two planar faces meet along a line split as the lids' seams are. Before, neither meshed at
// all; with the NaN gone but the edge still sampled, the line cracked.
test("a line split by an edge shorter than its Float32 knots: both faces mesh whole, watertight along it", () => {
  const floats = [];
  const span = (values) => { const at = floats.length; floats.push(...values); return [at, values.length]; };
  const pcurve = (edgeOrd, from, to, t0, t1, reversed = false) => ({ deg: 1, n: 2, periodic: false,
    poles: span([...from, ...to]), knots: span([t0, t0, t1, t1]), range: [t0, t1], edgeOrd, reversed });
  const line = (ord, origin, dir, t0, t1) => ({ ord, curve: { kind: "line", origin, dir, range: [t0, t1] } });
  const s = 241.99999981545; // Math.fround(s) === Math.fround(242)
  const plane = (ord, ydir, zdir, loop) => ({ ord, surfaceType: "plane", area: 426 * 20, reversed: false,
    uv: [0, 426, 0, 20], surface: { kind: "plane", origin: [0, 0, 0], xdir: [1, 0, 0], ydir, zdir }, loops: [loop] });
  const index = {
    edges: [
      line(1, [0, 0, 0], [1, 0, 0], 0, s), line(2, [0, 0, 0], [1, 0, 0], s, 242), line(3, [0, 0, 0], [1, 0, 0], 242, 426),
      line(4, [426, 0, 0], [0, 1, 0], 0, 20), line(5, [0, 20, 0], [1, 0, 0], 0, 426), line(6, [0, 0, 0], [0, 1, 0], 0, 20),
      line(7, [426, 0, 0], [0, 0, -1], 0, 20), line(8, [0, 0, -20], [1, 0, 0], 0, 426), line(9, [0, 0, 0], [0, 0, -1], 0, 20),
    ],
    faces: [
      // z = 0, uv = (x, y): the split line is its bottom side.
      plane(1, [0, 1, 0], [0, 0, 1], [pcurve(1, [0, 0], [s, 0], 0, s), pcurve(2, [s, 0], [242, 0], s, 242),
        pcurve(3, [242, 0], [426, 0], 242, 426), pcurve(4, [426, 0], [426, 20], 0, 20),
        pcurve(5, [0, 20], [426, 20], 0, 426, true), pcurve(6, [0, 0], [0, 20], 0, 20, true)]),
      // y = 0, uv = (x, -z): the split line is its top side, walked the other way.
      plane(2, [0, 0, -1], [0, 1, 0], [pcurve(9, [0, 0], [0, 20], 0, 20), pcurve(8, [0, 20], [426, 20], 0, 426),
        pcurve(7, [426, 0], [426, 20], 0, 20, true), pcurve(3, [242, 0], [426, 0], 242, 426, true),
        pcurve(2, [s, 0], [242, 0], s, 242, true), pcurve(1, [0, 0], [s, 0], 0, s, true)]),
    ],
  };
  const { positions, indices, faceRanges } = tessellateComponent(index, Float32Array.from(floats));
  const at = (i) => [positions[3 * i], positions[3 * i + 1], positions[3 * i + 2]];
  const onLine = (p) => p[1] === 0 && p[2] === 0;
  const uses = new Map();
  for (const face of index.faces) {
    const range = faceRanges.find((r) => r.ord === face.ord);
    assert.ok(range, `face ${face.ord} is meshed`);
    let area = 0;
    for (let i = range.indexStart; i < range.indexStart + range.indexCount; i += 3) {
      const [a, b, c] = [at(indices[i]), at(indices[i + 1]), at(indices[i + 2])];
      const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
      const v = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
      area += Math.hypot(u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]) / 2;
      for (const [p, q] of [[a, b], [b, c], [c, a]]) {
        if (onLine(p) && onLine(q)) {
          const key = [p[0], q[0]].sort((x, y) => x - y).join("|");
          uses.set(key, (uses.get(key) || 0) + 1);
        }
      }
    }
    assert.ok(Math.abs(area - face.area) <= face.area * 1e-6, `face ${face.ord}: meshed ${area} mm2 of ${face.area}`);
  }
  assert.ok(uses.size > 0, "the split line carries mesh edges");
  for (const [edge, count] of uses) assert.equal(count, 2, `mesh edge ${edge} on the split line is used by both faces`);
});

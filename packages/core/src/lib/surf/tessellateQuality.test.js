import assert from "node:assert/strict";
import test from "node:test";

import { tessellateComponent } from "./tessellate.js";
import { decodeComponentTessellation, edgeClassesFromSurfIndex, encodeComponentTessellation } from "./tessellationCache.js";

const SURFACE_INPUT = "1".repeat(64);
const SURFACE_OBJECT = "2".repeat(64);
const encodeV4 = (mesh, index, chordTolerance) => encodeComponentTessellation(mesh, {
  surfaceInput: SURFACE_INPUT,
  surfaceObject: SURFACE_OBJECT,
  tessellation: { chordTolerance },
  edgeClasses: edgeClassesFromSurfIndex(index),
});

// Analytic counterpart of the planetary carrier: a plate with three small
// bores. Rational circle pcurves use Float32 coefficients, as SURF does, while
// the shared circles and cylinder UV ranges retain exact double parameters.
function perforatedPlate(height = 4) {
  const values = [], faces = [], edges = [];
  const span = (items) => { const result = [values.length, items.length]; values.push(...items); return result; };
  const pcurve = (a, b, edgeOrd, reversed = false) => ({
    deg: 1, n: 2, poles: span([...a, ...b]), knots: span([0, 0, 1, 1]),
    range: [0, 1], edgeOrd, reversed,
  });
  const circlePCurve = (x, y, radius, edgeOrd, reversed) => {
    const poles = [], weights = [];
    for (let i = 0; i <= 6; i += 1) {
      const angle = i * Math.PI / 3, w = i % 2 ? 0.5 : 1;
      poles.push(x + radius * Math.cos(angle) / w, y + radius * Math.sin(angle) / w);
      weights.push(w);
    }
    return { deg: 2, n: 7, poles: span(poles), weights: span(weights),
      knots: span([0, 0, 0, 2 * Math.PI / 3, 2 * Math.PI / 3, 4 * Math.PI / 3, 4 * Math.PI / 3, 2 * Math.PI, 2 * Math.PI, 2 * Math.PI]),
      range: [0, 2 * Math.PI], edgeOrd, reversed };
  };
  const frame = (origin) => ({ origin, xdir: [1, 0, 0], ydir: [0, 1, 0], zdir: [0, 0, 1] });
  const top = [], bottom = [];
  for (const [i, [x, y, radius]] of [[0, 0, 52.5], [-21, -21 * Math.sqrt(3), 3.2], [42, 0, 3.2], [-21, 21 * Math.sqrt(3), 3.2]].entries()) {
    const topOrd = i * 3 + 1, bottomOrd = i * 3 + 2, seamOrd = i * 3 + 3;
    for (const [ord, z] of [[topOrd, -1], [bottomOrd, -1 - height]]) {
      edges.push({ ord, class: "feature", curve: { kind: "circle", ...frame([x, y, z]), radius, range: [0, 2 * Math.PI] } });
    }
    edges.push({ ord: seamOrd, class: "seam", curve: { kind: "line", origin: [x + radius, y, -1 - height], dir: [0, 0, 1], range: [0, height] } });
    faces.push({ ord: i + 1, reversed: i > 0, uv: [0, 2 * Math.PI, 0.1, height + 0.1],
      surface: { kind: "cylinder", ...frame([x, y, -height - 1.1]), radius },
      loops: [[pcurve([0, height + 0.1], [2 * Math.PI, height + 0.1], topOrd, true),
        pcurve([0, 0.1], [0, height + 0.1], seamOrd, true),
        pcurve([0, 0.1], [2 * Math.PI, 0.1], bottomOrd),
        pcurve([2 * Math.PI, 0.1], [2 * Math.PI, height + 0.1], seamOrd)]] });
    top.push([circlePCurve(x, y, radius, topOrd, i > 0)]);
    bottom.push([circlePCurve(x, y, radius, bottomOrd, i === 0)]);
  }
  faces.push({ ord: 5, surface: { kind: "plane", ...frame([0, 0, -1]) }, uv: [-52.5, 52.5, -52.5, 52.5], loops: top });
  faces.push({ ord: 6, reversed: true, surface: { kind: "plane", ...frame([0, 0, -1 - height]) }, uv: [-52.5, 52.5, -52.5, 52.5], loops: bottom });
  return { index: { faces, edges }, floats: Float32Array.from(values) };
}

function checkClosedOrientedMesh(mesh) {
  const { positions: p, normals: n, indices, scale } = mesh;
  const epsilon = scale * 1e-6;
  const key = (i) => [p[i * 3], p[i * 3 + 1], p[i * 3 + 2]].map((x) => Math.round(x / epsilon)).join(",");
  const edges = new Map();
  for (let t = 0; t < indices.length; t += 3) {
    const ids = Array.from(indices.slice(t, t + 3));
    const [a, b, c] = ids.map((i) => i * 3);
    const u = [p[b] - p[a], p[b + 1] - p[a + 1], p[b + 2] - p[a + 2]];
    const v = [p[c] - p[a], p[c + 1] - p[a + 1], p[c + 2] - p[a + 2]];
    const cross = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
    const length = Math.hypot(...cross);
    assert.ok(length > epsilon * epsilon, `triangle ${t / 3} collapses in Float32 transport`);
    const dot = cross.reduce((sum, value, d) => sum + value * (n[a + d] + n[b + d] + n[c + d]), 0);
    assert.ok(dot > 0, `triangle ${t / 3} faces against its surface normal`);
    for (let j = 0; j < 3; j += 1) {
      const first = key(ids[j]), second = key(ids[(j + 1) % 3]);
      const id = first < second ? `${first}|${second}` : `${second}|${first}`;
      const before = edges.get(id) ?? [0, 0];
      edges.set(id, [before[0] + 1, before[1] + (first < second ? 1 : -1)]);
    }
  }
  for (const [count, winding] of edges.values()) assert.deepEqual([count, winding], [2, 0]);
  for (const range of mesh.faceRanges) {
    for (let i = range.indexStart; i < range.indexStart + range.indexCount; i += 1) {
      assert.equal(mesh.faceOrds[indices[i]], range.ord);
    }
  }
  const ords = new Set(mesh.edges.map((edge) => edge.ord));
  for (const ord of mesh.sideOrds) assert.ok(ord === 0 || ords.has(ord));
}

function periodicPrimitive(kind) {
  const values = [], span = (items) => { const ref = [values.length, items.length]; values.push(...items); return ref; };
  const frame = { origin: [0, 0, 0], xdir: [1, 0, 0], ydir: [0, 1, 0], zdir: [0, 0, 1] };
  const surface = kind === "sphere" ? { kind, ...frame, radius: 10 } :
    kind === "cone" ? { kind, ...frame, radius: 8, semiAngle: -Math.atan2(8, 12) } :
      { kind, ...frame, majorRadius: 10, minorRadius: 2 };
  const [v0, v1] = kind === "sphere" ? [-Math.PI / 2, Math.PI / 2] :
    kind === "cone" ? [0, Math.hypot(8, 12)] : [0, 2 * Math.PI];
  const line = (a, b, edgeOrd, reversed) => ({ deg: 1, n: 2, poles: span([...a, ...b]),
    knots: span([0, 0, 1, 1]), range: [0, 1], edgeOrd, reversed });
  const circle = (radius) => ({ kind: "circle", ...frame, radius, range: [0, 2 * Math.PI] });
  const edges = kind === "sphere" ? [
    { ord: 1, class: "degenerate", curve: null },
    { ord: 2, class: "seam", curve: { ...circle(10), ydir: [0, 0, 1], zdir: [0, -1, 0], range: [v0, v1] } },
    { ord: 3, class: "degenerate", curve: null },
  ] : kind === "cone" ? [
    { ord: 1, class: "degenerate", curve: null },
    { ord: 2, class: "seam", curve: { kind: "line", origin: [8, 0, 0], dir: [-8 / v1, 0, 12 / v1], range: [0, v1] } },
    { ord: 3, class: "feature", curve: circle(8) },
  ] : [
    { ord: 1, class: "seam", curve: circle(12) },
    { ord: 2, class: "seam", curve: { ...circle(2), origin: [10, 0, 0], ydir: [0, 0, 1], zdir: [0, -1, 0] } },
  ];
  const bottomOrd = kind === "torus" ? 1 : 3;
  const faces = [{ ord: 1, surface, uv: [0, 2 * Math.PI, v0, v1], loops: [[
    line([0, v1], [2 * Math.PI, v1], 1, true), line([0, v0], [0, v1], 2, true),
    line([0, v0], [2 * Math.PI, v0], bottomOrd, false), line([2 * Math.PI, v0], [2 * Math.PI, v1], 2, false),
  ]] }];
  if (kind === "cone") {
    const poles = [], weights = [];
    for (let i = 0; i <= 6; i += 1) {
      const w = i % 2 ? 0.5 : 1;
      poles.push(8 * Math.cos(i * Math.PI / 3) / w, 8 * Math.sin(i * Math.PI / 3) / w);
      weights.push(w);
    }
    faces.push({ ord: 2, reversed: true, surface: { kind: "plane", ...frame }, uv: [-8, 8, -8, 8], loops: [[{
      deg: 2, n: 7, poles: span(poles), weights: span(weights),
      knots: span([0, 0, 0, 2 * Math.PI / 3, 2 * Math.PI / 3, 4 * Math.PI / 3, 4 * Math.PI / 3, 2 * Math.PI, 2 * Math.PI, 2 * Math.PI]),
      range: [0, 2 * Math.PI], edgeOrd: 3, reversed: true,
    }]] });
  }
  return { index: { faces, edges }, floats: Float32Array.from(values) };
}

function splineRevolution(z) {
  const values = [], span = (items) => { const ref = [values.length, items.length]; values.push(...items); return ref; };
  const length = Math.hypot(5, 4);
  const frame = { origin: [0, 0, z], xdir: [1, 0, 0], ydir: [0, 1, 0], zdir: [0, 0, 1] };
  const profile = { kind: "bspline", deg: 2, n: 3, poles: span([8, 0, z - 2, 13, 0, z, 8, 0, z + 2]),
    knots: span([0, 0, 0, length, length, length]), range: [0, length] };
  const line = (a, b, edgeOrd, reversed) => ({ deg: 1, n: 2, poles: span([...a, ...b]),
    knots: span([0, 0, 1, 1]), range: [0, 1], edgeOrd, reversed });
  const loop = (height, bottom, top, seam) => [[line([0, 0], [2 * Math.PI, 0], bottom, false),
    line([2 * Math.PI, 0], [2 * Math.PI, height], seam, false),
    line([0, height], [2 * Math.PI, height], top, true), line([0, 0], [0, height], seam, true)]];
  const faces = [
    { ord: 1, uv: [0, 2 * Math.PI, 0, length], surface: { kind: "revolution", origin: [0, 0, 0], dir: [0, 0, 1], profile }, loops: loop(length, 1, 2, 3) },
    { ord: 2, uv: [0, 2 * Math.PI, 0, 4], surface: { kind: "cylinder", ...frame, origin: [0, 0, z + 2], zdir: [0, 0, -1], radius: 8 }, loops: loop(4, 2, 1, 4) },
  ];
  const edges = [
    ...[z - 2, z + 2].map((height, i) => ({ ord: i + 1, class: "feature", curve: { kind: "circle", ...frame, origin: [0, 0, height], radius: 8, range: [0, 2 * Math.PI] } })),
    { ord: 3, class: "seam", curve: profile },
    { ord: 4, class: "seam", curve: { kind: "line", origin: [8, 0, z + 2], dir: [0, 0, -1], range: [0, 4] } },
  ];
  return { index: { faces, edges }, floats: Float32Array.from(values) };
}

test("coarse display tolerance does not merge short open edges or distinct corners", () => {
  const vertices = [[0, 0, 0], [100, 0, 0], [100, 1, 0], [0, 1, 0],
    [0, 0, 0.01], [100, 0, 0.01], [100, 1, 0.01], [0, 1, 0.01]];
  const values = [], edges = [], edgeMap = new Map();
  const span = (items) => { const ref = [values.length, items.length]; values.push(...items); return ref; };
  const difference = (a, b) => a.map((v, d) => v - b[d]);
  const faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [3, 7, 6, 2], [0, 4, 7, 3], [1, 2, 6, 5]].map((ids, i) => {
    const origin = vertices[ids[0]], alongU = difference(vertices[ids[1]], origin), alongV = difference(vertices[ids[3]], origin);
    const width = Math.hypot(...alongU), height = Math.hypot(...alongV);
    const xdir = alongU.map((x) => x / width), ydir = alongV.map((x) => x / height);
    const zdir = [xdir[1] * ydir[2] - xdir[2] * ydir[1], xdir[2] * ydir[0] - xdir[0] * ydir[2], xdir[0] * ydir[1] - xdir[1] * ydir[0]];
    const uv = [[0, 0], [width, 0], [width, height], [0, height]];
    const loop = ids.map((a, j) => {
      const b = ids[(j + 1) % 4], key = a < b ? `${a}:${b}` : `${b}:${a}`;
      let ord = edgeMap.get(key);
      if (!ord) {
        ord = edges.length + 1;
        edgeMap.set(key, ord);
        const vector = difference(vertices[b], vertices[a]), length = Math.hypot(...vector);
        edges.push({ ord, class: "feature", curve: { kind: "line", origin: vertices[a], dir: vector.map((x) => x / length), range: [0, length] } });
      }
      return { deg: 1, n: 2, poles: span([...uv[j], ...uv[(j + 1) % 4]]), knots: span([0, 0, 1, 1]), range: [0, 1], edgeOrd: ord };
    });
    return { ord: i + 1, surface: { kind: "plane", origin, xdir, ydir, zdir }, uv: [0, width, 0, height], loops: [loop] };
  });
  const index = { faces, edges }, floats = Float32Array.from(values);
  const mesh = tessellateComponent(index, floats, { chordTolerance: 0.003 });
  checkClosedOrientedMesh(mesh);
  assert.ok(Math.abs(mesh.bounds.max[2] - mesh.bounds.min[2] - 0.01) < 1e-6);
});

for (const chordTolerance of [0.003, 0.0015]) {
  test(`perforated plate: exact trim conformity remains closed and oriented at chord ${chordTolerance}`, () => {
    const { index, floats } = perforatedPlate();
    const mesh = tessellateComponent(index, floats, { chordTolerance });
    const bytes = encodeV4(mesh, index, chordTolerance);
    const decoded = decodeComponentTessellation(bytes).component;
    checkClosedOrientedMesh(decoded);
    assert.deepEqual(encodeV4(tessellateComponent(index, floats, { chordTolerance }), index, chordTolerance), bytes);
  });
  for (const kind of ["sphere", "cone", "torus"]) {
    test(`${kind}: periodic seams and singularities stay closed at chord ${chordTolerance}`, () => {
      const { index, floats } = periodicPrimitive(kind);
      const mesh = tessellateComponent(index, floats, { chordTolerance });
      checkClosedOrientedMesh(decodeComponentTessellation(encodeV4(mesh, index, chordTolerance)).component);
      if (kind === "sphere") {
        // Sample each edge midpoint and triangle centroid against the exact
        // sphere, including every facet adjacent to the collapsed pole rows.
        for (let i = 0; i < mesh.indices.length; i += 3) {
          const ids = mesh.indices.slice(i, i + 3);
          for (const weights of [[0.5, 0.5, 0], [0, 0.5, 0.5], [0.5, 0, 0.5], [1 / 3, 1 / 3, 1 / 3]]) {
            const p = [0, 1, 2].map((d) => ids.reduce((sum, id, j) => sum + mesh.positions[id * 3 + d] * weights[j], 0));
            const error = Math.abs(10 - Math.hypot(...p));
            assert.ok(error <= chordTolerance * mesh.scale, `${error} > ${chordTolerance * mesh.scale}`);
          }
        }
      }
    });
  }
  for (const z of [0, 60]) {
    test(`spline revolution at z=${z}: Float32 profile bounds preserve seams at chord ${chordTolerance}`, () => {
      const { index, floats } = splineRevolution(z);
      checkClosedOrientedMesh(tessellateComponent(index, floats, { chordTolerance }));
    });
  }
}

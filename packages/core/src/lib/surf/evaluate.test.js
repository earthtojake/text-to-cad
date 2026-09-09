// SURF reference evaluators vs OCCT ground truth. The fixture pair
// (sun_gear.surf + sun_gear.truth.json) is generated from the planetary
// gear assembly by cadgen's extractor; truth points are OCCT Value()
// samples. Tolerance reflects f32 quantization at model scale.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { parseSurf } from "./container.js";
import { evaluateCurve3, evaluatePCurve, evaluateSurface } from "./evaluate.js";

const here = dirname(fileURLToPath(import.meta.url));

function loadFixture(name) {
  const surfBytes = readFileSync(join(here, `fixtures/${name}.surf`));
  const truthData = JSON.parse(readFileSync(join(here, `fixtures/${name}.truth.json`), "utf8"));
  const parsed = parseSurf(
    surfBytes.buffer.slice(surfBytes.byteOffset, surfBytes.byteOffset + surfBytes.byteLength),
  );
  return { ...parsed, truth: truthData, name };
}

// sun_gear: a real assembly part (planes + arc-tooth cylinders, 99 faces).
// mixed: synthetic loft/fillet/torus part exercising the NURBS path.
const FIXTURES = [loadFixture("sun_gear"), loadFixture("mixed")];

const TOLERANCE = 2e-3;

function distance(a, b) {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

test("containers parse with expected shape counts", () => {
  for (const { index } of FIXTURES) {
    assert.equal(index.version, 2);
    assert.equal(index.faces.length, index.counts.faces);
    assert.equal(index.edges.length, index.counts.edges);
  }
});

test("every fixture surface kind evaluates against OCCT samples", () => {
  const kindsSeen = new Set();
  let checked = 0;
  for (const { index, floats, truth, name } of FIXTURES) {
    const facesByOrd = new Map(index.faces.map((face) => [face.ord, face]));
    for (const entry of truth.faces) {
      const face = facesByOrd.get(entry.ord);
      assert.ok(face, `${name}: missing face ${entry.ord}`);
      kindsSeen.add(face.surface.kind);
      for (const [u, v, x, y, z] of entry.samples) {
        const point = evaluateSurface(face.surface, floats, u, v);
        const error = distance(point, [x, y, z]);
        assert.ok(
          error < TOLERANCE,
          `${name}: face ${entry.ord} (${face.surface.kind}) uv=(${u},${v}) off by ${error}`,
        );
        checked += 1;
      }
    }
  }
  assert.ok(checked > 700, `only ${checked} samples checked`);
  for (const kind of ["plane", "cylinder", "torus", "nurbs"]) {
    assert.ok(kindsSeen.has(kind), `no ${kind} coverage: ${[...kindsSeen].join(",")}`);
  }
});

test("every fixture edge curve evaluates against OCCT samples", () => {
  let checked = 0;
  for (const { index, floats, truth, name } of FIXTURES) {
    const edgesByOrd = new Map(index.edges.map((edge) => [edge.ord, edge]));
    for (const entry of truth.edges) {
      const edge = edgesByOrd.get(entry.ord);
      assert.ok(edge?.curve, `${name}: missing curve for edge ${entry.ord}`);
      for (const [t, x, y, z] of entry.samples) {
        const point = evaluateCurve3(edge.curve, floats, t);
        const error = distance(point, [x, y, z]);
        assert.ok(
          error < TOLERANCE,
          `${name}: edge ${entry.ord} (${edge.curve.kind}) t=${t} off by ${error}`,
        );
        checked += 1;
      }
    }
  }
  assert.ok(checked > 1000, `only ${checked} samples checked`);
});

test("pcurve loops close: consecutive pcurves connect within tolerance in UV", () => {
  for (const { index, floats } of FIXTURES) closureCheck(index, floats);
});

function closureCheck(index, floats) {
  for (const face of index.faces) {
    for (const loop of face.loops) {
      for (let i = 0; i < loop.length; i += 1) {
        const current = loop[i];
        const next = loop[(i + 1) % loop.length];
        const endT = current.reversed ? current.range[0] : current.range[1];
        const startT = next.reversed ? next.range[1] : next.range[0];
        const end = evaluatePCurve(current, floats, endT);
        const start = evaluatePCurve(next, floats, startT);
        const [u0, u1, v0, v1] = face.uv;
        const scale = Math.max(u1 - u0, v1 - v0, 1e-9);
        const gap = Math.hypot(end[0] - start[0], end[1] - start[1]) / scale;
        // Seam-crossing loops jump a period in UV; allow those through.
        const period = Math.abs(Math.hypot(end[0] - start[0], end[1] - start[1]) - 2 * Math.PI);
        assert.ok(
          gap < 5e-3 || period < 1e-3,
          `face ${face.ord} loop gap ${gap} between pcurves ${i} and ${(i + 1) % loop.length}`,
        );
      }
    }
  }
}

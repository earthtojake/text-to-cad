// Selector-bundle parity (design/surface-rendering.md R3): the bundle
// synthesized from a .surf must carry the same tables the component GLB's
// STEP_TOPOLOGY selector manifest carried for the same shape. The oracle
// (sun_gear.selector.json) is dumped by the fixture generator from a real
// build_component_glb_from_shape run.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { parseSurf } from "./container.js";
import { buildSelectorBundleFromSurf } from "./surfSelectorBundle.js";

const here = dirname(fileURLToPath(import.meta.url));
const surfBytes = readFileSync(join(here, "fixtures/sun_gear.surf"));
const oracle = JSON.parse(readFileSync(join(here, "fixtures/sun_gear.selector.json"), "utf8"));
const { index, floats } = parseSurf(
  surfBytes.buffer.slice(surfBytes.byteOffset, surfBytes.byteOffset + surfBytes.byteLength),
);
const bundle = buildSelectorBundleFromSurf(index, floats);

function rowsAsObjects(manifest, rowKey, columnsKey) {
  const columns = manifest.tables[columnsKey];
  return manifest[rowKey].map((row) => Object.fromEntries(columns.map((c, i) => [c, row[i]])));
}

function near(a, b, tolerance, message) {
  assert.ok(Math.abs(a - b) <= tolerance, `${message}: ${a} vs ${b}`);
}

test("tables and columns match the GLB manifest schema", () => {
  for (const key of ["occurrenceColumns", "shapeColumns", "faceColumns", "edgeColumns"]) {
    assert.deepEqual(bundle.manifest.tables[key], oracle.tables[key], key);
  }
  assert.equal(bundle.manifest.schemaVersion, oracle.schemaVersion);
  assert.equal(bundle.manifest.faces.length, oracle.faces.length);
  assert.equal(bundle.manifest.edges.length, oracle.edges.length);
  assert.equal(bundle.manifest.shapes.length, oracle.shapes.length);
  assert.deepEqual(bundle.manifest.faceProxy.runColumns, oracle.faceProxy.runColumns);
});

test("face rows match the oracle (ids, types, areas, centers, relations)", () => {
  const mine = rowsAsObjects(bundle.manifest, "faces", "faceColumns");
  const truth = rowsAsObjects(oracle, "faces", "faceColumns");
  for (let i = 0; i < truth.length; i += 1) {
    const a = mine[i];
    const b = truth[i];
    assert.equal(a.id, b.id);
    assert.equal(a.shapeId, b.shapeId);
    assert.equal(a.surfaceType, b.surfaceType, a.id);
    near(a.area, b.area, Math.max(b.area * 0.02, 1e-3), `${a.id} area`);
    for (let d = 0; d < 3; d += 1) {
      near(a.center[d], b.center[d], 0.1, `${a.id} center[${d}]`);
      near(a.bbox.min[d], b.bbox.min[d], 0.05, `${a.id} bbox.min[${d}]`);
      near(a.bbox.max[d], b.bbox.max[d], 0.05, `${a.id} bbox.max[${d}]`);
    }
    assert.equal(a.edgeCount, b.edgeCount, `${a.id} edgeCount`);
    assert.equal(a.triangleCount > 0, b.triangleCount > 0, `${a.id} has triangles`);
    if (b.params) {
      assert.ok(a.params, `${a.id} params`);
      for (const key of Object.keys(b.params)) {
        assert.ok(key in a.params, `${a.id} params.${key}`);
      }
    }
  }
});

test("edge rows match the oracle (types, lengths, classes, adjacency)", () => {
  const mine = rowsAsObjects(bundle.manifest, "edges", "edgeColumns");
  const truth = rowsAsObjects(oracle, "edges", "edgeColumns");
  let classMismatches = 0;
  for (let i = 0; i < truth.length; i += 1) {
    const a = mine[i];
    const b = truth[i];
    assert.equal(a.id, b.id);
    assert.equal(a.curveType, b.curveType, a.id);
    near(a.length, b.length, Math.max(b.length * 0.02, 1e-3), `${a.id} length`);
    assert.equal(a.adjacentFaceCount, b.adjacentFaceCount, `${a.id} adjacency`);
    assert.equal(a.faceCount, b.faceCount, `${a.id} faceCount`);
    if (a.visibilityClass !== b.visibilityClass) classMismatches += 1;
  }
  // Classification algorithms are mirrored but not byte-identical
  // (sampled dihedral vs mesh-derived); allow a small disagreement tail.
  assert.ok(
    classMismatches <= Math.ceil(truth.length * 0.02),
    `${classMismatches}/${truth.length} visibility class mismatches`,
  );
});

test("relation and proxy buffers are consistent", () => {
  const faceRows = bundle.manifest.faces;
  const edgeRows = bundle.manifest.edges;
  const edgeStartIndex = bundle.manifest.tables.faceColumns.indexOf("edgeStart");
  const edgeCountIndex = bundle.manifest.tables.faceColumns.indexOf("edgeCount");
  for (const row of faceRows) {
    const start = row[edgeStartIndex];
    const count = row[edgeCountIndex];
    for (let i = start; i < start + count; i += 1) {
      assert.ok(bundle.buffers.faceEdgeRows[i] < edgeRows.length);
    }
  }
  assert.equal(bundle.buffers.faceRuns.length, bundle.manifest.faces.length * 5);
  assert.equal(bundle.buffers.surfaceHalfEdges.length % 7, 0);
  assert.equal(bundle.buffers.edgeIds.length * 2, bundle.buffers.edgeIndices.length);
});

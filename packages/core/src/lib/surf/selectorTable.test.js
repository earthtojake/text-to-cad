// The join of cadgen's selector table to a stored mesh, and the refs the runtime composes
// from it: every id, fact and connected set is the table's (fixtures/<name>.selectors.json,
// written by cadgen), joined to the mesh by ordinal; the page mints none of them.

import assert from "node:assert/strict";
import test from "node:test";

import { buildSelectorRuntime, composeSelectorRuntimes } from "../selectors/runtime.js";
import { SELECTOR_TABLE_SCHEMA_VERSION, joinSelectorTable, parseSelectorTable } from "./selectorTable.js";
import { decodeComponentTessellation, meshEdgePolylines, meshFaceRanges } from "./tessellationCache.js";
import { meshFixture, selectorTableFixture } from "./__tests__/meshFixtures.js";

function rowsOf(manifest, rows, columns) {
  return manifest[rows].map((row) => Object.fromEntries(manifest.tables[columns].map((name, index) => [name, row[index]])));
}

function load(name, level = 1) {
  const mesh = meshFixture(name, level);
  const { component } = decodeComponentTessellation(mesh.bytes, { surfaceInput: mesh.surfaceInput, tessellation: mesh.tessellation || {} });
  const table = selectorTableFixture(name);
  return { table, component, bundle: joinSelectorTable(table, component) };
}

test("parseSelectorTable reads cadgen's table and refuses another schema or shape", () => {
  const table = selectorTableFixture("sun_gear");
  assert.equal(table.schemaVersion, SELECTOR_TABLE_SCHEMA_VERSION);
  // JSON has no -0: the written text is what both readings must agree with.
  const text = JSON.stringify(table);
  assert.deepEqual(parseSelectorTable(text), JSON.parse(text));
  assert.deepEqual(parseSelectorTable(new TextEncoder().encode(text)), JSON.parse(text));
  assert.throws(() => parseSelectorTable(JSON.stringify({ ...table, schemaVersion: 99 })), /schema 99/);
  assert.throws(() => parseSelectorTable(JSON.stringify({ ...table, faces: table.faces.map((row) => row.slice(1)) })), /faces rows/);
  assert.throws(() => parseSelectorTable(JSON.stringify({ ...table, relations: {} })), /faceEdgeRows/);
});

for (const name of ["sun_gear", "cam_follower_roller", "slot"]) {
  test(`${name}: the join keeps every row of the table and ranges each by its ordinal in the mesh`, () => {
    const { table, component, bundle } = load(name);
    const faces = rowsOf(bundle.manifest, "faces", "faceColumns");
    const edges = rowsOf(bundle.manifest, "edges", "edgeColumns");
    assert.equal(faces.length, table.faces.length);
    assert.equal(edges.length, table.edges.length);
    assert.deepEqual(bundle.manifest.vertices, table.vertices, "vertex rows ride through untouched");
    const rangeByOrd = new Map(meshFaceRanges(component).map((range) => [range.ord, range]));
    for (const face of faces) {
      const range = rangeByOrd.get(face.ordinal);
      assert.equal(face.localId, `f${face.ordinal}`);
      assert.equal(face.id, `o1.${face.localId}`);
      assert.equal(face.triangleStart, range.indexStart / 3, `${face.id} starts where its mesh range starts`);
      assert.equal(face.triangleCount, range.indexCount / 3);
      assert.ok(Number.isInteger(face.tangentGroup));
    }
    const polylineByOrd = new Map(meshEdgePolylines(component).map((edge) => [edge.ord, edge.polyline]));
    let segmentCursor = 0;
    for (const edge of edges) {
      const points = (polylineByOrd.get(edge.ordinal)?.length || 0) / 3;
      assert.equal(edge.segmentStart, segmentCursor, `${edge.id} segments follow the table's order`);
      assert.equal(edge.segmentCount, Math.max(0, points - 1));
      segmentCursor += edge.segmentCount;
    }
    assert.equal(bundle.buffers.edgeIds.length, segmentCursor);
    assert.equal(bundle.buffers.edgeIndices.length, 2 * segmentCursor);
    // The face runs cover the mesh once, naming the table's rows.
    const runs = bundle.buffers.faceRuns;
    assert.equal(runs.length, 5 * rangeByOrd.size);
    let covered = 0;
    for (let offset = 0; offset < runs.length; offset += 5) {
      covered += runs[offset + 3];
      assert.equal(faces[runs[offset + 4]].triangleStart, runs[offset + 2]);
    }
    assert.equal(covered, component.indices.length / 3);
    for (const relation of ["faceEdgeRows", "edgeFaceRows", "edgeVertexRows", "vertexEdgeRows"]) {
      assert.deepEqual(Array.from(bundle.buffers[relation]), table.relations[relation]);
    }
  });
}

test("the runtime composes refs from the table's local ids and carries its facts, at any level", () => {
  const { table, bundle } = load("sun_gear", 0);
  const runtime = buildSelectorRuntime(bundle, { partId: "o1.3", remapOccurrenceId: "o1.3", copyCadPath: "gears.step" });
  const faceRows = rowsOf(table, "faces", "faceColumns");
  const faces = runtime.references.filter((reference) => reference.selectorType === "face");
  assert.deepEqual(faces.map((reference) => reference.displaySelector), faceRows.map((row) => `o1.3.${row.localId}`));
  assert.equal(faces[0].copyText, `gears.step#o1.3.${faceRows[0].localId}`);
  assert.deepEqual(faces.map((reference) => reference.pickData.area), faceRows.map((row) => row.area), "exact areas, not the mesh's");
  assert.deepEqual(faces.map((reference) => reference.pickData.normal), faceRows.map((row) => row.normal), "a plane's normal, else none");
  assert.deepEqual(faces.map((reference) => reference.pickData.flags), faceRows.map((row) => row.flags));
  const edgeRows = rowsOf(table, "edges", "edgeColumns");
  const edges = runtime.references.filter((reference) => reference.selectorType === "edge");
  assert.deepEqual(edges.map((reference) => reference.displaySelector), edgeRows.map((row) => `o1.3.${row.localId}`));
  assert.deepEqual(edges.map((reference) => reference.pickData.chain), edgeRows.map((row) => row.chain));
  // Adjacency is the table's relation rows, composed into the same namespace.
  const first = edgeRows[0];
  assert.deepEqual(edges[0].pickData.adjacentSelectors,
    table.relations.edgeFaceRows.slice(first.faceStart, first.faceStart + first.faceCount).map((row) => `o1.3.${faceRows[row].localId}`));
});

test("two occurrences of one component keep one table's ids apart by occurrence", () => {
  const { bundle } = load("cam_follower_roller");
  const composed = composeSelectorRuntimes(["o1.1", "o1.2"].map((id) => buildSelectorRuntime(bundle, { partId: id, remapOccurrenceId: id })));
  const byOccurrence = new Map();
  for (const reference of composed.references.filter((item) => item.selectorType === "face")) {
    byOccurrence.set(reference.occurrenceId, (byOccurrence.get(reference.occurrenceId) || 0) + 1);
  }
  assert.deepEqual([...byOccurrence.entries()], [["o1.1", bundle.manifest.faces.length], ["o1.2", bundle.manifest.faces.length]]);
  assert.ok(composed.referenceByDisplaySelector.has("o1.2.f1"));
});

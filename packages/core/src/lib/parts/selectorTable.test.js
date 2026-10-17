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

function load(name) {
  const mesh = meshFixture(name);
  const { component } = decodeComponentTessellation(mesh.bytes, { part: mesh.part });
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
    assert.equal(new Set(faces.map((face) => face.name)).size, faces.length, "each face's name is its own");
    for (const face of faces) {
      const range = rangeByOrd.get(face.ordinal);
      // A face row leads with its name -- the feature that made it, here the fixture's own
      // function, and its number there -- not an id.
      assert.match(face.name, new RegExp(`^f:${name}\\.[a-z_0-9]+\\.\\d+(\\.\\d+)?$`), face.name);
      assert.equal(face.triangleStart, range.indexStart / 3, `${face.name} starts where its mesh range starts`);
      assert.equal(face.triangleCount, range.indexCount / 3);
      assert.ok(Number.isInteger(face.tangentGroup));
    }
    const polylineByOrd = new Map(meshEdgePolylines(component).map((edge) => [edge.ord, edge.polyline]));
    let segmentCursor = 0;
    for (const edge of edges) {
      assert.match(edge.name, new RegExp(`^e:${name}\\.[a-z_0-9]+\\.\\d+(\\.\\d+)?$`), edge.name);
      const points = (polylineByOrd.get(edge.ordinal)?.length || 0) / 3;
      assert.equal(edge.segmentStart, segmentCursor, `${edge.name} segments follow the table's order`);
      assert.equal(edge.segmentCount, Math.max(0, points - 1));
      segmentCursor += edge.segmentCount;
    }
    assert.equal(bundle.buffers.edgeIds.length, segmentCursor);
    assert.equal(bundle.buffers.edgeIndices.length, 2 * segmentCursor);
    for (const relation of ["faceEdgeRows", "edgeFaceRows", "edgeVertexRows", "vertexEdgeRows"]) {
      assert.deepEqual(Array.from(bundle.buffers[relation]), table.relations[relation]);
    }
  });
}

// Occurrence tokens as the tree mints them (`o:` + 12 hex); their values are the page's business
// only in that every ref begins with one.
const GEAR = "o:3f2a9c1d7e5b";
const ROLLERS = ["o:a1b2c3d4e5f6", "o:0f1e2d3c4b5a"];

test("the runtime composes refs from the table's names and carries its facts", () => {
  const { table, bundle } = load("sun_gear");
  const runtime = buildSelectorRuntime(bundle, { partId: GEAR, occurrenceId: GEAR, copyCadPath: "gears.step" });
  const faceRows = rowsOf(table, "faces", "faceColumns");
  const faces = runtime.references.filter((reference) => reference.selectorType === "face");
  assert.deepEqual(faces.map((reference) => reference.displaySelector), faceRows.map((row) => `${GEAR}/${row.name}`));
  assert.equal(faces[0].copyText, `gears.step#${GEAR}/${faceRows[0].name}`);
  assert.deepEqual(faces.map((reference) => reference.pickData.element), faceRows.map((row) => row.name));
  assert.ok(faces.every((reference) => reference.pickData.name === null), "an element's name is no name of its own");
  assert.deepEqual(faces.map((reference) => reference.pickData.ordinal), faceRows.map((row) => row.ordinal), "the ordinal joins the mesh");
  assert.ok(faces.every((reference) => !("area" in reference.pickData)), "no face carries an area: cadgen measures it when asked");
  assert.deepEqual(faces.map((reference) => reference.pickData.normal), faceRows.map((row) => row.normal), "a plane's normal, else none");
  const edgeRows = rowsOf(table, "edges", "edgeColumns");
  const edges = runtime.references.filter((reference) => reference.selectorType === "edge");
  assert.deepEqual(edges.map((reference) => reference.displaySelector), edgeRows.map((row) => `${GEAR}/${row.name}`));
  assert.deepEqual(edges.map((reference) => reference.pickData.chain), edgeRows.map((row) => row.chain));
  assert.deepEqual(edges.map((reference) => reference.pickData.length), edgeRows.map((row) => row.length), "exact lengths, not the mesh's");
  assert.deepEqual(edges.map((reference) => reference.pickData.flags), edgeRows.map((row) => row.flags));
  // Adjacency is the table's relation rows, composed under the same occurrence.
  const first = edgeRows[0];
  assert.deepEqual(edges[0].pickData.adjacentSelectors,
    table.relations.edgeFaceRows.slice(first.faceStart, first.faceStart + first.faceCount).map((row) => `${GEAR}/${faceRows[row].name}`));
  // A shape is a row (it groups faces), never a reference.
  assert.equal(runtime.shapes.length, table.shapes.length);
  assert.ok(runtime.references.every((reference) => reference.selectorType !== "shape"));
});

test("two occurrences of one component keep one table's names apart by occurrence", () => {
  const { table, bundle } = load("cam_follower_roller");
  const composed = composeSelectorRuntimes(ROLLERS.map((id) => buildSelectorRuntime(bundle, { partId: id, occurrenceId: id })));
  const byOccurrence = new Map();
  for (const reference of composed.references.filter((item) => item.selectorType === "face")) {
    byOccurrence.set(reference.occurrenceId, (byOccurrence.get(reference.occurrenceId) || 0) + 1);
  }
  assert.deepEqual([...byOccurrence.entries()], ROLLERS.map((id) => [id, bundle.manifest.faces.length]));
  const firstFace = rowsOf(table, "faces", "faceColumns")[0].name;
  for (const id of ROLLERS) {
    assert.ok(composed.referenceByDisplaySelector.has(`${id}/${firstFace}`), `${id} places the same face under its own token`);
  }
});

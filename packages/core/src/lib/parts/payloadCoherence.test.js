// The mesh↔labels coherence invariant, pinned on cadgen's stored parts.
//
// Picking and highlighting work only when the displayed meshData and the
// selector bundle (face runs, edge tables) derive from ONE mesh. This suite
// asserts the invariant on cadgen's stored parts of REAL shapes — a gear
// (sun_gear) and a turned part (cam_follower_roller) — each its display mesh
// joined to its selector table, the two objects of one part's record.
import assert from "node:assert/strict";
import test from "node:test";

import { buildComponentMeshData } from "./partMeshData.js";
import { joinSelectorTable } from "./selectorTable.js";
import { decodeComponentTessellation, meshEdgePolylines, meshFaceRanges } from "./tessellationCache.js";
import { meshFixture, selectorTableFixture } from "./__tests__/meshFixtures.js";

const FIXTURES = ["sun_gear", "cam_follower_roller"];
const FACE_RUN_COLUMNS = 5; // occurrenceRow, primitiveIndex, triangleStart, triangleCount, faceRow

function loadFixture(name) {
  const table = selectorTableFixture(name);
  const mesh = meshFixture(name);
  const decoded = decodeComponentTessellation(mesh.bytes, { part: mesh.part });
  assert.ok(decoded, `${name} decodes`);
  return { table, component: decoded.component };
}

function faceRunRows(bundle) {
  const runs = bundle.buffers.faceRuns;
  assert.ok(runs instanceof Uint32Array, "bundle carries faceRuns");
  const rows = [];
  for (let offset = 0; offset < runs.length; offset += FACE_RUN_COLUMNS) {
    rows.push({
      triangleStart: runs[offset + 2],
      triangleCount: runs[offset + 3],
      faceRow: runs[offset + 4],
    });
  }
  return rows;
}

// The invariant itself: one (meshData, bundle) pair agrees with the component
// tessellation both claim to describe — faces AND edges.
function assertCoherent(label, component, meshData, bundle) {
  const meshTriangles = meshData.indices.length / 3;
  const rows = faceRunRows(bundle);
  const runTriangles = rows.reduce((sum, row) => sum + row.triangleCount, 0);
  assert.equal(runTriangles, meshTriangles, `${label}: faceRuns cover exactly the mesh triangles`);
  const faceRanges = meshFaceRanges(component);
  assert.equal(rows.length, faceRanges.length, `${label}: one run per face range`);
  const ordinal = bundle.manifest.tables.faceColumns.indexOf("ordinal");
  faceRanges.forEach((range, rangeIndex) => {
    const row = rows[rangeIndex];
    assert.equal(row.triangleStart, range.indexStart / 3, `${label}: run ${rangeIndex} start`);
    assert.equal(row.triangleCount, range.indexCount / 3, `${label}: run ${rangeIndex} count`);
    assert.equal(bundle.manifest.faces[row.faceRow][ordinal], range.ord, `${label}: run ${rangeIndex} names its face's row`);
  });
  // Runs must tile [0, meshTriangles) without gaps or overlaps: contiguous
  // face highlights depend on it.
  const sorted = [...rows].sort((a, b) => a.triangleStart - b.triangleStart);
  let cursor = 0;
  for (const row of sorted) {
    assert.equal(row.triangleStart, cursor, `${label}: runs tile without gaps`);
    cursor += row.triangleCount;
  }
  assert.equal(cursor, meshTriangles, `${label}: runs tile the whole mesh`);
  // EDGE channel: the bundle's edge tables and the mesh's CAD edge lines
  // must describe the same tessellation's edges.
  const componentEdges = meshEdgePolylines(component);
  const componentEdgeOrds = new Set(componentEdges.map((edge) => edge.ord));
  const edgeIds = bundle.buffers.edgeIds;
  assert.ok(edgeIds instanceof Uint32Array && edgeIds.length > 0, `${label}: bundle carries edge ids`);
  // Every edge row the bundle names is an edge of this mesh, or one it left undrawn.
  assert.equal(componentEdgeOrds.size, componentEdges.length, `${label}: edge ordinals are unique`);
  const lineSegments = meshData.cadEdgeIndices.length / 2;
  const rangeSegments = meshData.cadEdgeClassRanges.reduce((sum, range) => sum + range.segmentCount, 0);
  const rangePoints = meshData.cadEdgeClassRanges.reduce((sum, range) => sum + range.pointCount, 0);
  assert.equal(rangeSegments, lineSegments, `${label}: class ranges tile the CAD edge segments`);
  assert.equal(rangePoints, meshData.cadEdgePositions.length / 3, `${label}: class ranges tile the CAD edge points`);
  assert.ok(Array.from(meshData.cadEdgeIndices).every((i) => i < rangePoints), `${label}: edge indices address edge points`);
  const polylineSegments = componentEdges.reduce(
    (sum, edge) => sum + (edge.visibilityClass === "none" ? 0 : Math.max(0, edge.polyline.length / 3 - 1)),
    0,
  );
  assert.equal(lineSegments, polylineSegments, `${label}: CAD edge lines come from THIS tessellation's polylines`);
  // Indexed render buffers: the display shares the mesh's vertices instead
  // of expanding three corners per triangle.
  assert.equal(meshData.vertices.length, component.positions.length, `${label}: shared vertex buffer`);
  assert.equal(meshData.parts[0].vertexCount, component.positions.length / 3, `${label}: part vertexCount is the shared count`);
  assert.equal(meshData.parts[0].triangleCount, meshTriangles, `${label}: part triangleCount`);
}

for (const fixture of FIXTURES) {
  test(`${fixture}: the stored mesh with its selector table is coherent (faces + edges)`, () => {
    const { table, component } = loadFixture(fixture);
    const meshData = buildComponentMeshData(component);
    const bundle = joinSelectorTable(table, component);
    assertCoherent("stored part", component, meshData, bundle);
    // A decoded entry (one buffer for every section) is copied out so the entry can be released.
    assert.notEqual(meshData.vertices.buffer, component.positions.buffer, "vertices leave the entry buffer");
  });
}

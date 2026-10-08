// The mesh↔labels coherence invariant, pinned across every load-path shape.
//
// Picking and highlighting work only when the displayed meshData and the
// selector bundle (face runs, edge tables) derive from ONE mesh. Two viewer
// regressions came from breaking that pairing (LOD swaps leaving level-0 runs
// on a level-2 mesh; nearly, cache-hit meshes vs fresh bundles). This suite
// asserts the invariant on cadgen's stored meshes of REAL surfs — a gear
// (sun_gear) and a turned part (cam_follower_roller) — for every shape a
// component payload can take:
//   the real SURF index (selectors) · the stored entry's own display index
//   (render-only and snapshot loads) · a coarser LOD level.
// It also asserts the MIXED pairing is DETECTABLE (a level-N mesh against
// level-0 runs violates the count invariant), so a future desync cannot pass
// this suite by accident.
import assert from "node:assert/strict";
import test from "node:test";

import { parseSurf } from "./container.js";
import { buildMeshDataFromSurf } from "./surfMeshData.js";
import { joinSelectorTable } from "./selectorTable.js";
import {
  decodeComponentTessellation, meshEdgePolylines, meshFaceRanges, surfIndexFromCacheEntry,
} from "./tessellationCache.js";
import { meshFixture, selectorTableFixture, surfFixture } from "./__tests__/meshFixtures.js";

const FIXTURES = ["sun_gear", "cam_follower_roller"];
const FACE_RUN_COLUMNS = 5; // occurrenceRow, primitiveIndex, triangleStart, triangleCount, faceRow

function loadFixture(name, level = 1) {
  const { index } = parseSurf(surfFixture(name).arrayBuffer());
  const table = selectorTableFixture(name);
  const mesh = meshFixture(name, level);
  const decoded = decodeComponentTessellation(mesh.bytes, {
    surfaceInput: mesh.surfaceInput, surfaceObject: mesh.surfaceObject, tessellation: mesh.tessellation,
  });
  assert.ok(decoded, `${name} L${level} decodes`);
  return { index, table, decoded, component: decoded.component };
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
  faceRanges.forEach((range, rangeIndex) => {
    const row = rows[rangeIndex];
    assert.equal(row.triangleStart, range.indexStart / 3, `${label}: run ${rangeIndex} start`);
    assert.equal(row.triangleCount, range.indexCount / 3, `${label}: run ${rangeIndex} count`);
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

function assertTypedArraysEqual(label, a, b) {
  assert.equal(a.constructor, b.constructor, `${label}: same array type`);
  assert.equal(a.length, b.length, `${label}: same length`);
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) {
      assert.fail(`${label}: differs at ${i} (${a[i]} !== ${b[i]})`);
    }
  }
}

for (const fixture of FIXTURES) {
  test(`${fixture}: the stored mesh with its selector table is coherent (faces + edges)`, () => {
    const { index, table, component } = loadFixture(fixture);
    const meshData = buildMeshDataFromSurf(index, component);
    const bundle = joinSelectorTable(table, component);
    assertCoherent("real index", component, meshData, bundle);
    // A decoded entry (one buffer for every section) is copied out so the entry can be released.
    assert.notEqual(meshData.vertices.buffer, component.positions.buffer, "vertices leave the entry buffer");
  });

  test(`${fixture}: the entry's own display index draws what the real index draws`, () => {
    const { index, decoded, component } = loadFixture(fixture);
    const surrogate = surfIndexFromCacheEntry(decoded);
    assert.ok(surrogate, "every stored mesh yields a display index");
    const meshSurrogate = buildMeshDataFromSurf(surrogate, component);
    const meshReal = buildMeshDataFromSurf(index, component);
    for (const key of ["vertices", "indices", "normals", "cadEdgePositions", "cadEdgeIndices"]) {
      assertTypedArraysEqual(`surrogate meshData.${key}`, meshSurrogate[key], meshReal[key]);
    }
    assert.deepEqual(meshSurrogate.cadEdgeClassRanges, meshReal.cadEdgeClassRanges, "surrogate class ranges");
    assert.equal(meshSurrogate.sourceColor, meshReal.sourceColor, "the part colour rides the entry");
  });

  test(`${fixture}: a mixed level pairing VIOLATES the invariant (detectability)`, () => {
    const { index, table, component: level1 } = loadFixture(fixture, 1);
    const { component: level0 } = loadFixture(fixture, 0);
    assert.notEqual(
      level1.indices.length,
      level0.indices.length,
      "levels mesh to different densities (otherwise this test is vacuous)",
    );
    const meshLevel1 = buildMeshDataFromSurf(index, level1);
    const bundleLevel0 = joinSelectorTable(table, level0);
    const runTriangles = faceRunRows(bundleLevel0).reduce((sum, row) => sum + row.triangleCount, 0);
    assert.notEqual(
      runTriangles,
      meshLevel1.indices.length / 3,
      "level-0 runs against a level-1 mesh fail the count invariant — the desync is detectable",
    );
    // And the properly paired level-1 payload passes.
    const bundleLevel1 = joinSelectorTable(table, level1);
    assertCoherent("level-1 paired", level1, meshLevel1, bundleLevel1);
  });
}

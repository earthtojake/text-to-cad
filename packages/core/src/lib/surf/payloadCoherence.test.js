// The mesh↔labels coherence invariant, pinned across every load-path shape.
//
// Picking and highlighting work only when the displayed meshData and the
// selector bundle (face runs, edge tables) derive from ONE tessellation
// result. Two viewer regressions came from breaking that pairing (LOD swaps
// leaving level-0 runs on a level-2 mesh; nearly, cache-hit meshes vs fresh
// bundles). This suite asserts the invariant on REAL surfs — a generated part
// (sun_gear) and a native-import part (cam_follower_roller, the file the
// second regression was reported on) — for every shape a component payload
// can take:
//   fresh tessellation · cache-entry decode (worker hit path) · the
//   snapshot host's surrogate-index path · a finer LOD level.
// It also asserts the MIXED pairing is DETECTABLE (a level-N mesh against
// level-0 runs violates the count invariant), so a future desync cannot pass
// this suite by accident.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { parseSurf } from "./container.js";
import { tessellateComponent } from "./tessellate.js";
import { buildMeshDataFromSurf } from "./surfMeshData.js";
import { buildSelectorBundleFromSurf } from "./surfSelectorBundle.js";
import {
  decodeComponentTessellation,
  edgeClassesFromSurfIndex,
  encodeComponentTessellation,
  surfIndexFromCacheEntry,
} from "./tessellationCache.js";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES = ["sun_gear", "cam_follower_roller"];
const FACE_RUN_COLUMNS = 5; // occurrenceRow, primitiveIndex, triangleStart, triangleCount, faceRow

function loadFixture(name) {
  const buffer = fs.readFileSync(path.join(HERE, "fixtures", `${name}.surf`));
  return parseSurf(buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength));
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
  assert.equal(rows.length, component.faceRanges.length, `${label}: one run per face range`);
  component.faceRanges.forEach((range, rangeIndex) => {
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
  // EDGE channel: the bundle's edge tables and the mesh's edge-class overlay
  // must describe the same tessellation's edges.
  const componentEdgeOrds = new Set(component.edges.map((edge) => edge.ord));
  const edgeIds = bundle.buffers.edgeIds;
  assert.ok(edgeIds instanceof Uint32Array && edgeIds.length > 0, `${label}: bundle carries edge ids`);
  // sideOrds on the tessellation reference only real edges (or 0 = none).
  const sideOrds = new Set(component.sideOrds);
  sideOrds.delete(0);
  for (const ord of sideOrds) {
    assert.ok(componentEdgeOrds.has(ord), `${label}: sideOrd ${ord} is a real edge of this tessellation`);
  }
  assert.equal(
    meshData.surfaceEdgeClass.length,
    meshData.indices.length * 3,
    `${label}: per-corner edge classes sized to THIS mesh`,
  );
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
  test(`${fixture}: fresh tessellation payload is coherent (faces + edges)`, () => {
    const { index, floats } = loadFixture(fixture);
    const component = tessellateComponent(index, floats, {});
    const meshData = buildMeshDataFromSurf(index, floats, { component });
    const bundle = buildSelectorBundleFromSurf(index, floats, { component });
    assertCoherent("fresh", component, meshData, bundle);
  });

  test(`${fixture}: cache-entry decode (worker hit path) reproduces the fresh payload exactly`, () => {
    const { index, floats } = loadFixture(fixture);
    const fresh = tessellateComponent(index, floats, {});
    const entry = encodeComponentTessellation(fresh, {
      partColor: Array.isArray(index.partColor) ? index.partColor : null,
      edgeClasses: edgeClassesFromSurfIndex(index),
    });
    const decoded = decodeComponentTessellation(entry);
    assert.ok(decoded, "entry decodes");
    // The worker hit path: cached component + the REAL surf index feed both
    // consumers, exactly like surfWorker.js does.
    const meshHit = buildMeshDataFromSurf(index, floats, { component: decoded.component });
    const bundleHit = buildSelectorBundleFromSurf(index, floats, { component: decoded.component });
    assertCoherent("cache-hit", decoded.component, meshHit, bundleHit);
    const meshFresh = buildMeshDataFromSurf(index, floats, { component: fresh });
    for (const key of ["vertices", "indices", "normals", "surfaceEdgeBarycentric", "surfaceEdgeClass"]) {
      assertTypedArraysEqual(`cache-hit meshData.${key}`, meshHit[key], meshFresh[key]);
    }
    const bundleFresh = buildSelectorBundleFromSurf(index, floats, { component: fresh });
    assertTypedArraysEqual("cache-hit faceRuns", bundleHit.buffers.faceRuns, bundleFresh.buffers.faceRuns);
    assertTypedArraysEqual("cache-hit edgeIds", bundleHit.buffers.edgeIds, bundleFresh.buffers.edgeIds);
  });

  test(`${fixture}: snapshot surrogate-index path matches the real-index mesh`, () => {
    const { index, floats } = loadFixture(fixture);
    const fresh = tessellateComponent(index, floats, {});
    const entry = encodeComponentTessellation(fresh, {
      partColor: Array.isArray(index.partColor) ? index.partColor : null,
      edgeClasses: edgeClassesFromSurfIndex(index),
    });
    const decoded = decodeComponentTessellation(entry);
    const surrogate = surfIndexFromCacheEntry(decoded);
    assert.ok(surrogate, "v3 entry yields a surrogate index");
    const meshSurrogate = buildMeshDataFromSurf(surrogate, null, { component: decoded.component });
    const meshReal = buildMeshDataFromSurf(index, floats, { component: fresh });
    for (const key of ["vertices", "indices", "surfaceEdgeClass"]) {
      assertTypedArraysEqual(`surrogate meshData.${key}`, meshSurrogate[key], meshReal[key]);
    }
  });

  test(`${fixture}: a mixed level pairing VIOLATES the invariant (detectability)`, () => {
    const { index, floats } = loadFixture(fixture);
    const level0 = tessellateComponent(index, floats, {});
    const level1 = tessellateComponent(index, floats, { chordTolerance: 5e-4 });
    assert.notEqual(
      level1.indices.length,
      level0.indices.length,
      "levels tessellate to different densities (otherwise this test is vacuous)",
    );
    const meshLevel1 = buildMeshDataFromSurf(index, floats, { component: level1 });
    const bundleLevel0 = buildSelectorBundleFromSurf(index, floats, { component: level0 });
    const runTriangles = faceRunRows(bundleLevel0).reduce((sum, row) => sum + row.triangleCount, 0);
    assert.notEqual(
      runTriangles,
      meshLevel1.indices.length / 3,
      "level-0 runs against a level-1 mesh fail the count invariant — the desync is detectable",
    );
    // And the properly paired level-1 payload passes.
    const bundleLevel1 = buildSelectorBundleFromSurf(index, floats, { component: level1 });
    assertCoherent("level-1 paired", level1, meshLevel1, bundleLevel1);
  });
}

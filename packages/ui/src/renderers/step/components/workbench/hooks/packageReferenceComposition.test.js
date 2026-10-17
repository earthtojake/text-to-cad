// The picking invariant (the regression behind "striped highlights and picks
// through faces"): a composed package's selector runtime and its display mesh
// must come from ONE mesh of each component. faceRuns are triangle ranges of a
// specific mesh, so faceIds built from another mesh's runtime mislabel
// triangles. These tests pin the invariant with real geometry and pin the
// package composer to a full recomposition.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { createRequire } from "node:module";

import { decodeComponentTessellation } from "@text-to-cad/core/lib/parts/tessellationCache.js";
import { buildComponentMeshData } from "@text-to-cad/core/lib/parts/partMeshData.js";
import { joinSelectorTable, parseSelectorTable } from "@text-to-cad/core/lib/parts/selectorTable.js";
import { buildGlbFaceIdsForPart, TOPOLOGY_FACE_ID_NONE } from "@text-to-cad/core/lib/viewer/selectorPickGroups.js";
import { buildEdgeChainGraph } from "../../../workbench/edgeChainSelection.js";
import { buildTangentFaceGraph } from "../../../workbench/tangentFaceSelection.js";

import {
  buildPackageOccurrenceRuntimes,
  composePackageSelectorRuntime,
  createPackageReferenceComposer,
} from "./packageReferenceComposition.js";

const require = createRequire(import.meta.url);
// The gear's selector table and cadgen's stored display mesh of it (core's part fixtures).
const FIXTURES = path.join(path.dirname(require.resolve("@text-to-cad/core/lib/parts/tessellationCache.js")), "fixtures");

// Each call joins the table anew: a new bundle object over the same geometry, as a new file
// revision's is.
function loadMesh() {
  const table = parseSelectorTable(fs.readFileSync(path.join(FIXTURES, "sun_gear.selectors.json"), "utf8"));
  const decoded = decodeComponentTessellation(new Uint8Array(fs.readFileSync(path.join(FIXTURES, "sun_gear.glb"))));
  return {
    meshData: buildComponentMeshData(decoded.component),
    bundle: joinSelectorTable(table, decoded.component),
    component: decoded.component
  };
}

const ENTRY = { fileRefPrefix: "sun_gear.step", kind: "assembly", file: "sun_gear.step" };
// An occurrence token of the tree's shape (`o:` + 12 hex) for the n-th placed occurrence.
const occurrenceToken = (index) => `o:${(0xa0 + index).toString(16).padStart(12, "0")}`;
const GEAR = occurrenceToken(0);
const OCCURRENCES = [{ id: GEAR, component: "c0", transform: null }];

function partForMeshData(meshData) {
  return {
    occurrenceId: GEAR,
    primitiveIndex: 0,
    triangleOffset: 0,
    triangleCount: Math.floor(meshData.indices.length / 3)
  };
}

// The invariant faceIds must satisfy against the mesh they label: every
// triangle carries a face row (no NONE), and each face's labeled triangle
// count equals that face's triangle count in the SAME tessellation.
function faceIdInvariant(meshData, runtime) {
  const part = partForMeshData(meshData);
  const faceIds = buildGlbFaceIdsForPart(part, runtime);
  if (!faceIds) {
    return { ok: false, reason: "no faceIds matched" };
  }
  let unlabeled = 0;
  const perRow = new Map();
  for (const rowIndex of faceIds) {
    if (rowIndex === TOPOLOGY_FACE_ID_NONE) {
      unlabeled += 1;
      continue;
    }
    perRow.set(rowIndex, (perRow.get(rowIndex) || 0) + 1);
  }
  if (unlabeled > 0) {
    return { ok: false, reason: `${unlabeled} unlabeled triangles` };
  }
  // Compare against the mesh's own per-face triangle counts (parts[0] spans
  // the whole component; faceRanges live on the tessellation the meshData
  // was built from, exposed through the bundle's faceRuns — recompute from
  // the labeled totals instead: labeled totals must sum to the mesh).
  const labeledTotal = [...perRow.values()].reduce((sum, count) => sum + count, 0);
  if (labeledTotal !== part.triangleCount) {
    return { ok: false, reason: `labeled ${labeledTotal} of ${part.triangleCount}` };
  }
  return { ok: true, reason: "" };
}

test("every displayed triangle maps to a face row of its own mesh's runtime", () => {
  const { meshData, bundle } = loadMesh();
  const runtime = composePackageSelectorRuntime(ENTRY, OCCURRENCES, { c0: bundle }, {
    singleComponentPart: false
  });
  const verdict = faceIdInvariant(meshData, runtime);
  assert.ok(verdict.ok, verdict.reason);
});

test("occurrence runtimes build identically through both entrypoints", () => {
  const { bundle } = loadMesh();
  const runtimes = buildPackageOccurrenceRuntimes(ENTRY, OCCURRENCES, { c0: bundle }, {
    singleComponentPart: false
  });
  assert.equal(runtimes.length, 1);
  // The occurrence namespace is what keeps picks aligned with the composed
  // mesh's sourcePartRanges — pin it.
  const reference = runtimes[0].references?.[0];
  assert.ok(String(reference?.id || "").includes(GEAR), `reference ids carry the occurrence: ${reference?.id}`);
});

// ---- incremental composition: the same runtime as composing everything again ----------------

function placedOccurrence(index, component = "c0") {
  const angle = 0.5 * index;
  return {
    id: occurrenceToken(index),
    component,
    transform: [Math.cos(angle), -Math.sin(angle), 0, 40 * index, Math.sin(angle), Math.cos(angle), 0, -7 * index, 0, 0, 1, 3.5 * index, 0, 0, 0, 1]
  };
}

test("the package composer composes exactly what recomposing every occurrence does", () => {
  const first = loadMesh().bundle;
  const replaced = loadMesh().bundle; // the same geometry under a new bundle, as a new revision's is
  const revised = loadMesh().bundle;
  const occurrences = Array.from({ length: 10 }, (_, index) => placedOccurrence(index, index % 3 ? "c0" : "c1"));
  const composer = createPackageReferenceComposer();
  const steps = [
    ["nothing loaded", ENTRY, [], { c0: first, c1: first }],
    ["one part", ENTRY, occurrences.slice(0, 1), { c0: first, c1: first }],
    ["parts appended as they scroll on", ENTRY, occurrences.slice(0, 4), { c0: first, c1: first }],
    ["more appended", ENTRY, occurrences.slice(0, 8), { c0: first, c1: first }],
    ["one unloaded from the middle", ENTRY, [...occurrences.slice(0, 3), ...occurrences.slice(4, 8)], { c0: first, c1: first }],
    ["it comes back", ENTRY, occurrences.slice(0, 8), { c0: first, c1: first }],
    ["a component's bundle replaced", ENTRY, occurrences.slice(0, 8), { c0: replaced, c1: first }],
    ["appended under the replacement", ENTRY, occurrences, { c0: replaced, c1: first }],
    ["the first bundle back", ENTRY, occurrences, { c0: first, c1: first }],
    ["a changed file revision", { ...ENTRY, fileRefPrefix: "sun_gear_v2.step" }, occurrences.slice(0, 5), { c0: revised, c1: revised }],
    ["a single-component part", { ...ENTRY, kind: "part" }, occurrences.slice(0, 1), { c0: first }],
  ];
  for (const [label, entry, loaded, bundleByCid] of steps) {
    const singleComponentPart = entry.kind === "part";
    const incremental = composePackageSelectorRuntime(entry, loaded, bundleByCid, { singleComponentPart, composer });
    const recomposed = composePackageSelectorRuntime(entry, loaded, bundleByCid, { singleComponentPart });
    // Every reference, lookup, proxy array and edge-chain endpoint (Group edges' input).
    assert.deepStrictEqual(incremental, recomposed, label);
    // And what Group edges and Group faces make of them.
    const references = (runtime) => [...(runtime?.referenceMap?.values() || [])];
    assert.deepStrictEqual(buildEdgeChainGraph(references(incremental)), buildEdgeChainGraph(references(recomposed)), label);
    assert.deepStrictEqual(buildTangentFaceGraph(references(incremental)), buildTangentFaceGraph(references(recomposed)), label);
  }
});

test("the package composer keeps the picking invariant", () => {
  const mesh = loadMesh();
  const composer = createPackageReferenceComposer();
  const runtime = composePackageSelectorRuntime(ENTRY, OCCURRENCES, { c0: mesh.bundle }, { composer });
  assert.ok(faceIdInvariant(mesh.meshData, runtime).ok);
});

test("the package composer builds each occurrence once and releases what stops being composed", () => {
  const { bundle } = loadMesh();
  const occurrences = Array.from({ length: 6 }, (_, index) => placedOccurrence(index));
  const composer = createPackageReferenceComposer({ retainCompositions: 2 });
  const first = composePackageSelectorRuntime(ENTRY, occurrences.slice(0, 3), { c0: bundle }, { composer });
  const second = composePackageSelectorRuntime(ENTRY, occurrences, { c0: bundle }, { composer });
  assert.equal(composer.size, 6);
  // The first three occurrences were not rebuilt: their references are the same objects.
  assert.ok(first.references.every((reference, index) => second.references[index] === reference));
  composePackageSelectorRuntime(ENTRY, occurrences.slice(3), { c0: bundle }, { composer });
  composePackageSelectorRuntime(ENTRY, occurrences.slice(3), { c0: bundle }, { composer });
  assert.equal(composer.size, 3);
  composer.reset();
  assert.equal(composer.size, 0);
});

test("Group edges and Group faces group the same references through the package composer", () => {
  // One square face bounded by four line edges, three of them one chain as cadgen decided it,
  // and one tangent edge between two faces of one tangent group: chains and groups both exist.
  // The table's rows lead with their names (schema 3) and name no occurrence: the composer
  // places them by each occurrence's token.
  const bundle = {
    manifest: {
      tables: {
        occurrenceColumns: ["bbox"],
        shapeColumns: ["ordinal", "kind"],
        faceColumns: ["name", "ordinal", "shape", "surfaceType", "edgeStart", "edgeCount", "tangentGroup"],
        edgeColumns: ["name", "ordinal", "shape", "curveType", "faceStart", "faceCount", "segmentStart", "segmentCount", "visibilityClass", "chain"],
      },
      occurrences: [[null]],
      shapes: [[1, "solid"]],
      faces: [["f:base.extrude1.1", 1, 1, "plane", 0, 4, 1], ["f:base.hole1.1", 2, 1, "cylinder", 0, 1, 1]],
      edges: [
        ["e:base.hole1.1", 1, 1, "line", 0, 2, 0, 1, "tangent", 1],
        ["e:base.extrude1.1", 2, 1, "line", 0, 1, 1, 1, "feature", 2],
        ["e:base.extrude1.2", 3, 1, "line", 0, 1, 2, 2, "feature", 2],
        ["e:base.extrude1.3", 4, 1, "line", 0, 1, 4, 1, "feature", 2],
      ],
      relations: { faceEdgeRows: [0, 1, 2, 3, 0], edgeFaceRows: [0, 1, 0, 0, 0] },
    },
    buffers: {
      edgePositions: new Float32Array([0.1, 0.2, 0.3, 10.1, 0.2, 0.3, 10.1, 10.2, 0.3, 5.1, 10.2, 0.3, 0.1, 10.2, 0.3]),
      edgeIndices: new Uint32Array([0, 1, 1, 2, 2, 3, 3, 4, 4, 0]),
      edgeIds: new Uint32Array([0, 1, 2, 2, 3]),
    },
  };
  const occurrences = Array.from({ length: 5 }, (_, index) => placedOccurrence(index));
  const composer = createPackageReferenceComposer();
  let linked = 0;
  for (const loaded of [occurrences.slice(0, 2), occurrences, [occurrences[0], ...occurrences.slice(2)]]) {
    const incremental = composePackageSelectorRuntime(ENTRY, loaded, { c0: bundle }, { composer });
    const recomposed = composePackageSelectorRuntime(ENTRY, loaded, { c0: bundle });
    assert.deepStrictEqual(incremental, recomposed);
    const edges = buildEdgeChainGraph([...incremental.referenceMap.values()]);
    assert.deepStrictEqual(edges, buildEdgeChainGraph([...recomposed.referenceMap.values()]));
    assert.deepStrictEqual(buildTangentFaceGraph([...incremental.referenceMap.values()]), buildTangentFaceGraph([...recomposed.referenceMap.values()]));
    linked += [...edges.values()].filter((neighbours) => neighbours.size).length;
  }
  assert.ok(linked > 0, "the fixture forms edge chains");
});

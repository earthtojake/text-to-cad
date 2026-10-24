import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildSelectorRuntime,
  buildTransformedSelectorRuntime,
  composeSelectorRuntimes
} from "./runtime.js";

// Names as cadgen gives them: an occurrence's token from its place in the tree, an element's name
// from its lineage (the feature that made it and its number there) or, where it has none, its
// geometric token (`f:` + 12 hex). The values here are arbitrary; only their shape is the grammar's.
const A = "o:3f2a9c1d7e5b";
const B = "o:a1b2c3d4e5f6";
const F1 = "f:plate.extrude1.1";
const F2 = "f:plate.extrude1.2";
const F7 = "f:plate.fillet1.3.2";
const E1 = "e:plate.extrude1.1";
const E4 = "e:9d2e8c1b5a70";

// The selector table's wire columns (cadgen's, schema 6) as joining it to its mesh extended
// them: a face gains its triangle range, an edge its segment range.
const OCCURRENCE_COLUMNS = ["transform", "bbox", "shapeStart", "shapeCount", "faceStart", "faceCount", "edgeStart", "edgeCount", "vertexStart", "vertexCount"];
const SHAPE_COLUMNS = ["ordinal", "kind", "bbox", "center", "faceStart", "faceCount", "edgeStart", "edgeCount"];
const FACE_COLUMNS = ["name", "ordinal", "shape", "surfaceType", "normal", "bbox", "edgeStart", "edgeCount", "params", "tangentGroup", "triangleStart", "triangleCount"];
const EDGE_COLUMNS = ["name", "ordinal", "shape", "curveType", "length", "center", "bbox", "faceStart", "faceCount", "vertexStart", "vertexCount", "relevance", "flags", "params", "adjacentFaceCount", "continuity", "dihedralDeg", "visibilityClass", "chain", "segmentStart", "segmentCount"];
const TABLES = { occurrenceColumns: OCCURRENCE_COLUMNS, shapeColumns: SHAPE_COLUMNS, faceColumns: FACE_COLUMNS, edgeColumns: EDGE_COLUMNS };

const box = (x0, x1, y1) => ({ min: [x0, 0, 0], max: [x1, y1, 0] });
const occurrenceRow = (bbox, shapes, faces, edges) => [null, bbox, 0, shapes, 0, faces, 0, edges, 0, 0];
const shapeRow = (ordinal, bbox, center, faces, edges) => [ordinal, "solid", bbox, center, 0, faces, 0, edges];
const faceRow = (name, ordinal, shape, { bbox = null, edges = 0, tangentGroup = 1, triangles = [0, 0] } = {}) =>
  [name, ordinal, shape, "plane", [0, 0, 1], bbox, 0, edges, {}, tangentGroup, ...triangles];
const edgeRow = (name, ordinal, shape, { center = [0, 0, 0], bbox = null, faces = 0, chain = null, visibilityClass = "feature", segments = [0, 0] } = {}) =>
  [name, ordinal, shape, "line", 1, center, bbox, 0, faces, 0, 0, 0, 0, {}, faces, "c0", 90, visibilityClass, chain, ...segments];

function fakeComponentRuntime(occurrenceId) {
  // A minimal per-component selector runtime: 2 faces, 1 edge, one occurrence, with the face
  // pick run (occurrenceRow, primitiveIndex, triangleStart, triangleCount, faceRow).
  const ref = (selector, selectorType, rowIndex, pickData) => ({
    id: selector, normalizedSelector: selector, displaySelector: selector, selectorType, rowIndex,
    ...(pickData ? { pickData } : {})
  });
  return {
    occurrences: [{ occurrenceId }],
    shapes: [],
    faces: [{ name: F1 }, { name: F2 }],
    edges: [{ name: E1 }],
    bbox: { min: [0, 0, 0], max: [1, 1, 1] },
    references: [
      ref(occurrenceId, "occurrence", 0),
      ref(`${occurrenceId}/${F1}`, "face", 0, { triangleStart: 0, triangleCount: 1 }),
      ref(`${occurrenceId}/${F2}`, "face", 1, { triangleStart: 0, triangleCount: 1 }),
      ref(`${occurrenceId}/${E1}`, "edge", 0, { segmentStart: 0, segmentCount: 1 })
    ],
    occurrenceIdByRowIndex: new Map([[0, occurrenceId]]),
    proxy: {
      facePositions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
      faceIndices: new Uint32Array([0, 1, 2]),
      faceIds: new Uint32Array([0]),
      faceRuns: new Uint32Array([0, 0, 0, 1, 0]),
      faceRunColumns: ["occurrenceRow", "primitiveIndex", "triangleStart", "triangleCount", "faceRow"],
      edgePositions: new Float32Array([0, 0, 0, 1, 0, 0]),
      edgeIndices: new Uint32Array([0, 1]),
      edgeIds: new Uint32Array([0])
    }
  };
}

test("composeSelectorRuntimes merges per-component runtimes with disjoint row/proxy offsets", () => {
  const merged = composeSelectorRuntimes([fakeComponentRuntime(A), fakeComponentRuntime(B)]);

  // Tables concatenate; each component occupies a disjoint range.
  assert.equal(merged.faces.length, 4);
  assert.equal(merged.edges.length, 2);
  assert.equal(merged.occurrences.length, 2);

  // The second component's face reference rowIndex is offset past the first's faces.
  assert.equal(merged.references.find((r) => r.normalizedSelector === `${B}/${F1}`).rowIndex, 2);
  // faceReferenceByRowIndex resolves both components by their offset rows.
  assert.equal(merged.faceReferenceByRowIndex.get(0).normalizedSelector, `${A}/${F1}`);
  assert.equal(merged.faceReferenceByRowIndex.get(2).normalizedSelector, `${B}/${F1}`);
  assert.equal(merged.occurrenceIdByRowIndex.get(0), A);
  assert.equal(merged.occurrenceIdByRowIndex.get(1), B);

  // The pick faceRuns concatenate, offsetting occurrenceRow and faceRow into the merged tables,
  // and the face proxy ids/indices offset to stay consistent with faceReferenceByRowIndex.
  assert.equal(merged.proxy.faceRuns.length, 10);
  assert.equal(merged.proxy.faceRuns[5 + 0], 1); // occurrenceRow of component 2
  assert.equal(merged.proxy.faceRuns[5 + 4], 2); // faceRow of component 2
  assert.equal(merged.proxy.faceIds[1], 2);
  assert.deepEqual([...merged.proxy.faceIndices], [0, 1, 2, 3, 4, 5]);

  // Each reference's pickData segment/triangle start shifts into the CONCATENATED edge/face
  // proxies so a non-first occurrence's highlight indexes its OWN geometry, not the first
  // component's (the bug: selecting the second occurrence's edge highlighted the first). The
  // first stays at 0; the second shifts past the first component's 1 triangle / 1 edge segment.
  const refBySel = (sel) => merged.references.find((r) => r.normalizedSelector === sel);
  assert.equal(refBySel(`${A}/${E1}`).pickData.segmentStart, 0);
  assert.equal(refBySel(`${B}/${E1}`).pickData.segmentStart, 1);
  assert.equal(refBySel(`${A}/${F1}`).pickData.triangleStart, 0);
  assert.equal(refBySel(`${B}/${F1}`).pickData.triangleStart, 1);
});

test("buildSelectorRuntime composes the placing occurrence with each row's own name", () => {
  // The names are cadgen's (the selector table's `name` column), from each element's lineage or
  // geometry; the ordinal is the mesh join only. A composed ref says what cadgen says, never
  // `f${rowIndex + 1}`, and a row without a name has no ref.
  const bundle = {
    manifest: {
      cadRef: "parts/source",
      tables: TABLES,
      occurrences: [occurrenceRow(null, 1, 3, 1)],
      shapes: [shapeRow(1, null, null, 3, 1)],
      faces: [
        faceRow(F1, 1, 1, { tangentGroup: 1 }),
        faceRow(F7, 7, 1, { tangentGroup: 3 }),
        faceRow("", 9, 1, { tangentGroup: 3 })
      ],
      edges: [edgeRow(E4, 4, 1, { chain: 2 })]
    },
    buffers: {}
  };

  const runtime = buildSelectorRuntime(bundle, { copyCadPath: "parts/root", partId: A, occurrenceId: A });
  const faces = runtime.references.filter((reference) => reference.selectorType === "face");

  assert.deepEqual(faces.map((reference) => reference.displaySelector), [`${A}/${F1}`, `${A}/${F7}`], "a row without a name has no ref");
  assert.deepEqual(faces.map((reference) => reference.pickData.tangentGroup), [1, 3]);
  assert.deepEqual(faces.map((reference) => reference.pickData.ordinal), [1, 7]);
  assert.equal(faces[0].id, `topology|${A}|face|${A}/${F1}`);
  const [edge] = runtime.references.filter((reference) => reference.selectorType === "edge");
  assert.equal(edge.displaySelector, `${A}/${E4}`);
  assert.equal(edge.pickData.chain, 2);
  assert.equal(edge.pickData.element, E4);
  // copyCadPath reaches the copy text, so a copied ref says which file it came from. The viewer
  // supplies the name its host gives the file (its path under the host's root).
  assert.equal(faces[1].copyText, `parts/root#${A}/${F7}`);
  assert.equal(faces[1].pickData.surfaceType, "plane");
  const [occurrence] = runtime.references.filter((reference) => reference.selectorType === "occurrence");
  assert.equal(occurrence.displaySelector, A);
  assert.equal(occurrence.occurrenceId, "", "an occurrence reference IS the occurrence");
});

test("a part placed by no occurrence composes the bare element name", () => {
  // A document with one leaf resolves a bare name (cadgen assembly_lookup does the same), so a
  // bundle built for no occurrence names its elements by name alone.
  const bundle = {
    manifest: {
      cadRef: "parts/alone",
      tables: TABLES,
      occurrences: [occurrenceRow(null, 1, 1, 1)],
      shapes: [shapeRow(1, null, null, 1, 1)],
      faces: [faceRow(F1, 1, 1)],
      edges: [edgeRow(E1, 1, 1)]
    },
    buffers: {}
  };
  const runtime = buildSelectorRuntime(bundle, { copyCadPath: "parts/alone" });
  assert.deepEqual(
    runtime.references.map((reference) => [reference.selectorType, reference.displaySelector]),
    [["face", F1], ["edge", E1]],
    "an occurrence nobody named is no reference; its elements are bare names"
  );
  assert.equal(runtime.references[0].copyText, `parts/alone#${F1}`);
});

test("a shape row is no reference", () => {
  // A shape (a solid of the part) groups faces and carries a volume, but a ref names an
  // occurrence, a face, an edge or a vertex: nothing copies or resolves a shape.
  const bundle = {
    manifest: {
      cadRef: "parts/labeled",
      tables: TABLES,
      occurrences: [occurrenceRow(null, 1, 0, 0)],
      shapes: [shapeRow(1, null, null, 0, 0)],
      faces: [],
      edges: []
    },
    buffers: {}
  };

  const runtime = buildSelectorRuntime(bundle, { copyCadPath: "parts/labeled", occurrenceId: A });
  assert.deepEqual(runtime.references.map((reference) => reference.selectorType), ["occurrence"]);
  assert.deepEqual(runtime.shapes.map((row) => [row.ordinal, row.kind, row.occurrenceId]), [[1, "solid", A]]);
});

test("buildSelectorRuntime exposes v1 GLB face runs from selector buffers", () => {
  const bundle = {
    manifest: {
      cadRef: "parts/source",
      faceProxy: {
        source: "model.glb",
        runsView: "faceRuns",
        runColumns: ["occurrenceRow", "primitiveIndex", "triangleStart", "triangleCount", "faceRow"]
      },
      tables: TABLES,
      occurrences: [occurrenceRow(null, 1, 1, 0)],
      shapes: [shapeRow(1, null, null, 1, 0)],
      faces: [faceRow(F1, 1, 1, { triangles: [2, 4] })],
      edges: []
    },
    buffers: {
      faceRuns: new Uint32Array([0, 1, 2, 4, 0])
    }
  };

  const runtime = buildSelectorRuntime(bundle, { occurrenceId: A });

  assert.deepEqual(Array.from(runtime.proxy.faceRuns), [0, 1, 2, 4, 0]);
  assert.deepEqual(runtime.proxy.faceRunColumns, ["occurrenceRow", "primitiveIndex", "triangleStart", "triangleCount", "faceRow"]);
  assert.equal(runtime.occurrenceIdByRowIndex.get(0), A);
});

function componentBundle(xOffset) {
  // One component's selector data, as a part's table actually carries it: the rows are the
  // PART's and name no occurrence; whatever the assembly calls this instance of it is the page's.
  const bbox = box(xOffset, xOffset + 1, 1);
  return {
    manifest: {
      cadRef: "parts/source",
      tables: TABLES,
      occurrences: [occurrenceRow(bbox, 1, 1, 1)],
      shapes: [shapeRow(1, bbox, [xOffset + 0.5, 0.5, 0], 1, 1)],
      faces: [faceRow(F1, 1, 1, { bbox, edges: 1, triangles: [0, 1] })],
      edges: [edgeRow(E1, 1, 1, { center: [xOffset + 0.5, 0, 0], bbox: box(xOffset, xOffset + 1, 0), faces: 1, segments: [0, 1] })],
      relations: { faceEdgeRows: [0], edgeFaceRows: [0] }
    },
    buffers: {
      facePositions: new Float32Array([xOffset, 0, 0, xOffset + 1, 0, 0, xOffset, 1, 0]),
      faceIndices: new Uint32Array([0, 1, 2]),
      faceIds: new Uint32Array([0]),
      edgePositions: new Float32Array([xOffset, 0, 0, xOffset + 1, 0, 0]),
      edgeIndices: new Uint32Array([0, 1]),
      edgeIds: new Uint32Array([0])
    }
  };
}

test("a composed assembly transforms the occurrence the CALLER named", () => {
  // composeSelectorRuntimes concatenates component TABLES verbatim, so every row must already say
  // which occurrence placed it: the runtime stamps the page's occurrence on each row when it is
  // built. Before it did, a caller's transform matched no row, applied to no geometry, and
  // hovered edges stayed at rest while faces -- rebuilt from the live display meshes -- moved.
  const runtime = composeSelectorRuntimes([
    buildSelectorRuntime(componentBundle(0), { occurrenceId: A }),
    buildSelectorRuntime(componentBundle(100), { occurrenceId: B })
  ]);
  assert.deepEqual(
    [...new Set(runtime.edges.map((row) => row.occurrenceId))],
    [A, B],
    "each row carries the occurrence that placed it"
  );

  const transformed = buildTransformedSelectorRuntime(runtime, new Map([
    [B, [1, 0, 0, 0, 0, 1, 0, 5, 0, 0, 1, 0, 0, 0, 0, 1]]
  ]));

  const edgeOf = (rt, id) => rt.references.find((reference) => reference.id === id);
  // The named occurrence moves, in its rows, its reference pickData, AND the pick proxy the
  // hover highlight slices its line positions out of.
  assert.deepEqual(edgeOf(transformed, `${B}/${E1}`).pickData.center, [100.5, 5, 0]);
  assert.deepEqual(transformed.edges[1].center, [100.5, 5, 0]);
  assert.deepEqual(Array.from(transformed.proxy.edgePositions.slice(6)), [100, 5, 0, 101, 5, 0]);
  assert.deepEqual(Array.from(transformed.proxy.facePositions.slice(9)), [100, 5, 0, 101, 5, 0, 100, 6, 0]);

  // ...and the occurrence nobody named stays exactly where it was.
  assert.deepEqual(edgeOf(transformed, `${A}/${E1}`).pickData.center, [0.5, 0, 0]);
  assert.deepEqual(Array.from(transformed.proxy.edgePositions.slice(0, 6)), [0, 0, 0, 1, 0, 0]);
});

test("buildTransformedSelectorRuntime applies part transforms to rows and proxy geometry", () => {
  const runtime = buildSelectorRuntime(componentBundle(0), { occurrenceId: A });
  const transformed = buildTransformedSelectorRuntime(runtime, new Map([
    [A, [
      1, 0, 0, 10,
      0, 1, 0, 20,
      0, 0, 1, 30,
      0, 0, 0, 1
    ]]
  ]));

  const placedBox = { min: [10, 20, 30], max: [11, 21, 30] };
  assert.deepEqual(transformed.faces[0].bbox, placedBox);
  assert.deepEqual(transformed.edges[0].center, [10.5, 20, 30]);
  assert.deepEqual(transformed.references.find((reference) => reference.selectorType === "face").pickData.bbox, placedBox);
  assert.deepEqual(Array.from(transformed.proxy.facePositions), [
    10, 20, 30,
    11, 20, 30,
    10, 21, 30
  ]);
  assert.deepEqual(Array.from(transformed.proxy.faceIndices), [0, 1, 2]);
  assert.deepEqual(Array.from(transformed.proxy.faceIds), [0]);
  assert.deepEqual(Array.from(transformed.proxy.edgePositions), [
    10, 20, 30,
    11, 20, 30
  ]);
  assert.deepEqual(Array.from(transformed.proxy.edgeIndices), [0, 1]);
  assert.deepEqual(Array.from(transformed.proxy.edgeIds), [0]);
});

test("edge tangency, adjacency and connected ids survive placing into separate assembly occurrences", () => {
  const bundle = { manifest: { tables: {
    occurrenceColumns: ["bbox"],
    faceColumns: ["name", "ordinal", "shape", "tangentGroup"],
    edgeColumns: ["name", "ordinal", "shape", "faceStart", "faceCount", "visibilityClass", "chain"],
  }, occurrences: [[null]], faces: [[F1, 1, 1, 1], [F2, 2, 1, 1]],
  edges: [[E1, 1, 1, 0, 2, "tangent", 4]], relations: { edgeFaceRows: [0, 1] } }, buffers: {} };
  const runtimes = [A, B].map((id) => buildSelectorRuntime(bundle, { partId: id, occurrenceId: id }));
  const composed = composeSelectorRuntimes(runtimes);
  const edges = composed.references.filter((ref) => ref.selectorType === "edge");
  assert.deepEqual(edges.map((ref) => ref.pickData.visibilityClass), ["tangent", "tangent"]);
  assert.deepEqual(edges.map((ref) => ref.pickData.adjacentSelectors), [[`${A}/${F1}`, `${A}/${F2}`], [`${B}/${F1}`, `${B}/${F2}`]]);
  // cadgen's connected sets ride through composition and posing unchanged: they are local to the
  // component, like the names.
  assert.deepEqual(edges.map((ref) => [ref.occurrenceId, ref.pickData.chain]), [[A, 4], [B, 4]]);
  const posed = buildTransformedSelectorRuntime(composed, { [B]: [1, 0, 0, 10, 0, 1, 0, 20, 0, 0, 1, 30, 0, 0, 0, 1] });
  assert.deepEqual(posed.references.filter((ref) => ref.selectorType === "face").map((ref) => ref.pickData.tangentGroup), [1, 1, 1, 1]);
  assert.deepEqual(posed.references.filter((ref) => ref.selectorType === "edge").map((ref) => ref.pickData.chain), [4, 4]);
});

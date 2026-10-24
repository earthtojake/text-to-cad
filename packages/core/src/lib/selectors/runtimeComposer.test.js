// The incremental composer is pure performance: every test here holds it to the path it
// replaces, value for value, on synthetic component bundles shaped like a selector table joined
// to its mesh.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildSelectorCompositionPart,
  buildSelectorRuntime,
  composeSelectorRuntimes,
  createSelectorRuntimeComposer,
} from "./runtime.js";

// ---- a seeded synthetic component bundle ----------------------------------------------------

function random(seed) {
  let state = seed >>> 0 || 1;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

// The selector table's columns (cadgen's, schema 3) as joining it to its mesh extended
// them with each face's triangle range and each edge's segment range. Element rows lead with
// their name; `shape` is the owning solid's ordinal; no row names an occurrence.
const OCCURRENCE_COLUMNS = ["transform", "bbox", "shapeStart", "shapeCount", "faceStart", "faceCount", "edgeStart", "edgeCount", "vertexStart", "vertexCount"];
const SHAPE_COLUMNS = ["ordinal", "kind", "bbox", "center", "faceStart", "faceCount", "edgeStart", "edgeCount"];
const FACE_COLUMNS = ["name", "ordinal", "shape", "surfaceType", "normal", "bbox", "edgeStart", "edgeCount", "params",
  "tangentGroup", "triangleStart", "triangleCount"];
const EDGE_COLUMNS = ["name", "ordinal", "shape", "curveType", "length", "center", "bbox", "faceStart", "faceCount", "vertexStart",
  "vertexCount", "relevance", "flags", "params", "adjacentFaceCount", "continuity", "dihedralDeg", "visibilityClass", "chain",
  "segmentStart", "segmentCount"];
const FACE_EDGE_COUNT = FACE_COLUMNS.indexOf("edgeCount");
const FACE_TRIANGLE_START = FACE_COLUMNS.indexOf("triangleStart");
const EDGE_FACE_COUNT = EDGE_COLUMNS.indexOf("faceCount");

// A name of the grammar's shape for the n-th element of a synthetic part: the n-th its one
// feature made.
const elementName = (kind, n) => `${kind}:part.extrude1.${n}`;

// `faces` faces over `shapes` solids; each face bounded by a loop of edges that share their
// end vertices with the next edge BY VALUE (sometimes through a duplicated vertex index), plus a
// closed circle, a branched edge and a degenerate segment. `detail` scales the edge polylines
// and the face proxy, as a denser mesh of the same topology would.
function makeBundle(seed, { faces: faceCount = 4, shapes: shapeCount = 2, detail = 1, faceProxy = true, stepHash = "h1" } = {}) {
  const rand = random(seed);
  const coord = () => Math.round((rand() * 200 - 100) * 1e4) / 1e4 + 0.1;
  const positions = [];
  const vertex = (point) => { positions.push(...point); return positions.length / 3 - 1; };
  const edgeIndices = [];
  const edgeIds = [];
  const edges = [];
  const edgeFaceRows = [];
  const faceEdgeRows = [];
  const faces = [];
  const shapes = [];
  const pushEdge = (shape, points, { curveType = "line", params = {}, indices = null } = {}) => {
    const row = edges.length;
    const segmentStart = edgeIds.length;
    const vertexIndices = indices || points.map(vertex);
    for (let i = 0; i + 1 < vertexIndices.length; i += 1) {
      edgeIndices.push(vertexIndices[i], vertexIndices[i + 1]);
      edgeIds.push(row);
    }
    edges.push([elementName("e", row + 1), row + 1, shape, curveType, 1 + rand(), [0, 0, 0],
      { min: [-1, -1, -1], max: [1, 1, 1] }, 0, 2, 0, 0, 0, 0, params, 2, "c0",
      rand() * 180, rand() < 0.5 ? "feature" : "tangent", row + 1, segmentStart, edgeIds.length - segmentStart]);
    return row;
  };
  for (let s = 0; s < shapeCount; s += 1) {
    shapes.push([s + 1, "solid", { min: [-100, -100, -100], max: [100, 100, 100] },
      [coord(), coord(), coord()], 0, 0, 0, 0]);
  }
  for (let f = 0; f < faceCount; f += 1) {
    const shape = (f % shapeCount) + 1;
    // A loop of 3 edges: corners a -> b -> c -> a, each edge a polyline of `detail` segments.
    const corners = [[coord(), coord(), coord()], [coord(), coord(), coord()], [coord(), coord(), coord()]];
    const loop = [];
    for (let k = 0; k < 3; k += 1) {
      const from = corners[k];
      const to = corners[(k + 1) % 3];
      const points = [];
      for (let i = 0; i <= detail; i += 1) {
        const t = i / detail;
        points.push(from.map((value, axis) => value + (to[axis] - value) * t + (i && i < detail ? rand() * 0.01 : 0)));
      }
      loop.push(pushEdge(shape, points));
    }
    if (f % 3 === 0) {
      // A closed circle: its ends meet.
      const center = [coord(), coord(), coord()];
      const ring = Array.from({ length: 4 + detail }, (_, i) => {
        const angle = (2 * Math.PI * i) / (4 + detail);
        return [center[0] + Math.cos(angle), center[1] + Math.sin(angle), center[2]];
      });
      const ringIndices = ring.map(vertex);
      loop.push(pushEdge(shape, null, { curveType: "circle", params: { center, axis: [0, 0, 1], radius: 1 }, indices: [...ringIndices, ringIndices[0]] }));
    }
    if (f % 3 === 1) {
      // An open arc (circle curve type): its end directions are the circle's tangents.
      const center = [coord(), coord(), coord()];
      const arc = Array.from({ length: 3 + detail }, (_, i) => {
        const angle = (Math.PI * i) / (2 + detail);
        return [center[0] + 2 * Math.cos(angle), center[1], center[2] + 2 * Math.sin(angle)];
      });
      loop.push(pushEdge(shape, arc, { curveType: "circle", params: { center, axis: [0, 1, 0], radius: 2 } }));
      // A branched proxy (a vertex used three times).
      const hub = vertex([coord(), coord(), coord()]);
      loop.push(pushEdge(shape, null, { indices: [hub, vertex([coord(), coord(), coord()]), hub, vertex([coord(), coord(), coord()]), hub] }));
    }
    if (f % 3 === 2) {
      // A degenerate segment inside an otherwise open edge, and a duplicated end vertex index.
      const a = [coord(), coord(), coord()];
      const b = [coord(), coord(), coord()];
      loop.push(pushEdge(shape, null, { indices: [vertex(a), vertex(a), vertex(b)] }));
      // Vertices one coordinate apart are different vertices.
      loop.push(pushEdge(shape, [b, [b[0], b[1], b[2] + 1.5], [b[0] + 0.5, b[1], b[2] + 1.5], a]));
    }
    faces.push([elementName("f", f + 1), f + 1, shape, f % 2 ? "plane" : "cylinder",
      [0, 0, 1], { min: [-100, -100, -100], max: [100, 100, 100] }, 0, loop.length,
      f % 2 ? { origin: [coord(), coord(), coord()], normal: [0, 0, 1] } : { axis: [0, 1, 0], center: [coord(), coord(), coord()], radius: 3 },
      f + 1, 0, 0]);
    faceEdgeRows.push(...loop);
  }
  // Each edge borders its own face and the next one.
  const edgeFaces = edges.map(() => []);
  let cursor = 0;
  faces.forEach((face, faceRow) => {
    for (let i = 0; i < face[FACE_EDGE_COUNT]; i += 1) edgeFaces[faceEdgeRows[cursor + i]].push(faceRow, (faceRow + 1) % faces.length);
    cursor += face[FACE_EDGE_COUNT];
  });
  edges.forEach((edge, row) => { edge[EDGE_FACE_COUNT] = edgeFaces[row].length; edgeFaceRows.push(...edgeFaces[row]); });

  // The face proxy and its runs: `detail` triangles per face.
  const facePositions = [];
  const faceIndices = [];
  const faceIds = [];
  const faceRuns = [];
  faces.forEach((face, faceRow) => {
    const triangleStart = faceIds.length;
    for (let t = 0; t < detail; t += 1) {
      const base = facePositions.length / 3;
      facePositions.push(coord(), coord(), coord(), coord(), coord(), coord(), coord(), coord(), coord());
      faceIndices.push(base, base + 1, base + 2);
      faceIds.push(faceRow);
    }
    face[FACE_TRIANGLE_START] = triangleStart;
    face[FACE_TRIANGLE_START + 1] = detail;
    faceRuns.push(0, 0, triangleStart, detail, faceRow);
  });
  const shapeFaces = shapes.map(() => 0);
  faces.forEach((face) => { shapeFaces[face[2] - 1] += 1; });
  return {
    manifest: {
      schemaVersion: 2,
      profile: "selector",
      capabilities: { surfaceEdgeRendering: true },
      stepHash,
      bbox: { min: [-100, -100, -100], max: [100, 100, 100] },
      tables: {
        occurrenceColumns: OCCURRENCE_COLUMNS,
        shapeColumns: SHAPE_COLUMNS,
        faceColumns: FACE_COLUMNS,
        edgeColumns: EDGE_COLUMNS,
      },
      occurrences: [[null, { min: [-100, -100, -100], max: [100, 100, 100] }, 0, shapes.length, 0, faces.length, 0, edges.length, 0, 0]],
      shapes,
      faces,
      edges,
      faceProxy: { source: "part", runsView: "faceRuns", runColumns: ["occurrenceRow", "primitiveIndex", "triangleStart", "triangleCount", "faceRow"] },
      edgeProxy: { positionsView: "edgePositions", indicesView: "edgeIndices", edgeIdsView: "edgeIds" },
      relations: { faceEdgeRowsView: "faceEdgeRows", edgeFaceRowsView: "edgeFaceRows" },
    },
    buffers: {
      ...(faceProxy ? {
        facePositions: new Float32Array(facePositions),
        faceIndices: new Uint32Array(faceIndices),
        faceIds: new Uint32Array(faceIds),
      } : {}),
      faceRuns: new Uint32Array(faceRuns),
      edgePositions: new Float32Array(positions),
      edgeIndices: new Uint32Array(edgeIndices),
      edgeIds: new Uint32Array(edgeIds),
      faceEdgeRows: new Uint32Array(faceEdgeRows),
      edgeFaceRows: new Uint32Array(edgeFaceRows),
    },
  };
}

// A rigid placement with a rotation, so placed coordinates round through Float32.
function placement(index) {
  const angle = 0.37 * (index + 1);
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return [c, -s, 0, 10.1 * index, s, c, 0, -3.3 * index, 0, 0, 1, 0.7 * index, 0, 0, 0, 1];
}

// ---- the incremental composer against composing whole runtimes -----------------------------

// The occurrence the page places the n-th part by: a token of the tree's shape (`o:` + 12 hex).
function occurrenceOptions(index, { copyCadPath = "cars/hypercar.step", single = false } = {}) {
  const id = `o:${(0xa0 + index).toString(16).padStart(12, "0")}`;
  return { copyCadPath, partId: single ? "" : id, transform: placement(index), occurrenceId: id };
}

function composeFresh(items) {
  return composeSelectorRuntimes(items.map(({ bundle, options }) => buildSelectorRuntime(bundle, options)));
}

function assertSameComposition(actual, expected, label) {
  assert.deepStrictEqual(actual, expected, label);
}

test("the incremental composer composes exactly what composing whole runtimes does", () => {
  const bundles = [makeBundle(11, { faces: 5 }), makeBundle(12, { faces: 3, shapes: 1, faceProxy: false }), makeBundle(13, { faces: 6, detail: 2 })];
  const revised = makeBundle(21, { faces: 4, stepHash: "h2" });
  const composer = createSelectorRuntimeComposer();
  const parts = new Map();
  const partFor = ({ bundle, options }, key) => {
    if (!parts.has(key)) parts.set(key, buildSelectorCompositionPart(bundle, options));
    return parts.get(key);
  };
  const item = (index, bundle = bundles[index % bundles.length], extra = {}) => ({ index, bundle, options: occurrenceOptions(index, extra) });
  const steps = [
    ["nothing", []],
    ["one part", [item(0)]],
    ["appended parts", [item(0), item(1), item(2)]],
    ["a longer append", [item(0), item(1), item(2), item(3), item(4), item(5)]],
    ["the same parts again", [item(0), item(1), item(2), item(3), item(4), item(5)]],
    ["a part inserted in the middle", [item(0), item(1), item(6), item(2), item(3), item(4), item(5)]],
    ["a part removed", [item(0), item(6), item(2), item(3), item(4), item(5)]],
    ["the first part removed", [item(6), item(2), item(3), item(4), item(5)]],
    ["appended after a removal", [item(6), item(2), item(3), item(4), item(5), item(7), item(8)]],
    ["down to one part", [item(4)]],
    ["a changed revision", [item(0, revised, { copyCadPath: "cars/hypercar_v2.step" }), item(1, revised, { copyCadPath: "cars/hypercar_v2.step" })]],
    ["a single-component part", [item(0, bundles[0], { single: true }), item(1, bundles[0], { single: true })]],
  ];
  for (const [label, items] of steps) {
    const incremental = composer.compose(items.map((entry) => partFor(entry, `${entry.index}:${bundles.indexOf(entry.bundle)}:${entry.bundle === revised ? "revised" : ""}:${entry.options.partId}:${entry.options.copyCadPath}`)));
    assertSameComposition(incremental, composeFresh(items), label);
  }
});

test("the incremental composer reuses placed references and extends the previous result", () => {
  const bundle = makeBundle(31, { faces: 4 });
  const composer = createSelectorRuntimeComposer();
  const parts = [0, 1, 2, 3].map((index) => buildSelectorCompositionPart(bundle, occurrenceOptions(index)));
  const first = composer.compose(parts.slice(0, 2));
  const second = composer.compose(parts);
  // The first two parts sit where they sat: the very same reference objects.
  const kept = first.references.length;
  assert.ok(second.references.slice(0, kept).every((reference, index) => reference === first.references[index]));
  // A composition never mutates one before it.
  assert.equal(first.references.length, kept);
  assert.equal(first.referenceMap.size, kept);
  assert.deepStrictEqual(second, composeFresh(parts.map((part) => ({ bundle, options: part.options }))));
  // Moving a part moves its references (new objects), never the ones the last result holds.
  const moved = composer.compose([parts[1], parts[0], parts[2], parts[3]]);
  assert.notEqual(moved.references[0], second.references[0]);
  assert.deepStrictEqual(second, composeFresh(parts.map((part) => ({ bundle, options: part.options }))));
});

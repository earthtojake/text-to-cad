// The incremental composer and the lazy edge-chain endpoints are pure performance: every
// test here holds them to the path they replace, value for value, on synthetic component
// bundles shaped like the ones `buildSelectorBundleFromSurf` produces.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildSelectorCompositionPart,
  buildSelectorRuntime,
  buildTransformedSelectorRuntime,
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

const EDGE_COLUMNS = ["id", "occurrenceId", "shapeId", "ordinal", "curveType", "length", "center", "bbox", "faceStart",
  "faceCount", "relevance", "flags", "params", "segmentStart", "segmentCount", "adjacentFaceCount", "continuity",
  "dihedralDeg", "visibilityClass", "surfaceHalfEdgeStart", "surfaceHalfEdgeCount"];

// `faces` faces over `shapes` solids; each face bounded by a loop of edges that share their
// end vertices with the next edge BY VALUE (sometimes through a duplicated vertex index), plus a
// closed circle, a branched edge and a degenerate segment. `detail` scales the edge polylines
// and the face proxy, as a finer LOD level of the same topology would.
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
  const pushEdge = (shapeId, points, { curveType = "line", params = {}, indices = null } = {}) => {
    const row = edges.length;
    const segmentStart = edgeIds.length;
    const vertexIndices = indices || points.map(vertex);
    for (let i = 0; i + 1 < vertexIndices.length; i += 1) {
      edgeIndices.push(vertexIndices[i], vertexIndices[i + 1]);
      edgeIds.push(row);
    }
    edges.push([`o1.e${row + 1}`, "o1", shapeId, row + 1, curveType, 1 + rand(), [0, 0, 0],
      { min: [-1, -1, -1], max: [1, 1, 1] }, 0, 2, 0, 0, params, segmentStart, edgeIds.length - segmentStart, 2, "c0",
      rand() * 180, rand() < 0.5 ? "feature" : "tangent", 0, 0]);
    return row;
  };
  for (let s = 0; s < shapeCount; s += 1) {
    shapes.push([`o1.s${s + 1}`, "o1", s + 1, "solid", null, null, { min: [-100, -100, -100], max: [100, 100, 100] },
      [coord(), coord(), coord()], 1000 * rand(), 100 * rand(), 0, 0, 0, 0]);
  }
  for (let f = 0; f < faceCount; f += 1) {
    const shapeId = `o1.s${(f % shapeCount) + 1}`;
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
      loop.push(pushEdge(shapeId, points));
    }
    if (f % 3 === 0) {
      // A closed circle: its ends meet, so it has no chain endpoints.
      const center = [coord(), coord(), coord()];
      const ring = Array.from({ length: 4 + detail }, (_, i) => {
        const angle = (2 * Math.PI * i) / (4 + detail);
        return [center[0] + Math.cos(angle), center[1] + Math.sin(angle), center[2]];
      });
      const ringIndices = ring.map(vertex);
      loop.push(pushEdge(shapeId, null, { curveType: "circle", params: { center, axis: [0, 0, 1], radius: 1 }, indices: [...ringIndices, ringIndices[0]] }));
    }
    if (f % 3 === 1) {
      // An open arc (circle curve type): its end directions are the circle's tangents.
      const center = [coord(), coord(), coord()];
      const arc = Array.from({ length: 3 + detail }, (_, i) => {
        const angle = (Math.PI * i) / (2 + detail);
        return [center[0] + 2 * Math.cos(angle), center[1], center[2] + 2 * Math.sin(angle)];
      });
      loop.push(pushEdge(shapeId, arc, { curveType: "circle", params: { center, axis: [0, 1, 0], radius: 2 } }));
      // A branched proxy (a vertex used three times): no chain endpoints.
      const hub = vertex([coord(), coord(), coord()]);
      loop.push(pushEdge(shapeId, null, { indices: [hub, vertex([coord(), coord(), coord()]), hub, vertex([coord(), coord(), coord()]), hub] }));
    }
    if (f % 3 === 2) {
      // A degenerate segment inside an otherwise open edge, and a duplicated end vertex index.
      const a = [coord(), coord(), coord()];
      const b = [coord(), coord(), coord()];
      loop.push(pushEdge(shapeId, null, { indices: [vertex(a), vertex(a), vertex(b)] }));
      // Vertices one coordinate apart are different vertices.
      loop.push(pushEdge(shapeId, [b, [b[0], b[1], b[2] + 1.5], [b[0] + 0.5, b[1], b[2] + 1.5], a]));
    }
    faces.push([`o1.f${f + 1}`, "o1", shapeId, f + 1, f % 2 ? "plane" : "cylinder", 10 * rand(), [coord(), coord(), coord()],
      [0, 0, 1], { min: [-100, -100, -100], max: [100, 100, 100] }, 0, loop.length, 0, 0,
      f % 2 ? { origin: [coord(), coord(), coord()], normal: [0, 0, 1] } : { axis: [0, 1, 0], center: [coord(), coord(), coord()], radius: 3 },
      0, 0]);
    faceEdgeRows.push(...loop);
  }
  // Each edge borders its own face and the next one.
  const edgeFaces = edges.map(() => []);
  let cursor = 0;
  faces.forEach((face, faceRow) => {
    for (let i = 0; i < face[10]; i += 1) edgeFaces[faceEdgeRows[cursor + i]].push(faceRow, (faceRow + 1) % faces.length);
    cursor += face[10];
  });
  edges.forEach((edge, row) => { edge[9] = edgeFaces[row].length; edgeFaceRows.push(...edgeFaces[row]); });

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
    face[14] = triangleStart;
    face[15] = detail;
    faceRuns.push(0, 0, triangleStart, detail, faceRow);
  });
  const shapeFaces = shapes.map(() => 0);
  faces.forEach((face) => { shapeFaces[Number(face[2].slice(4)) - 1] += 1; });
  return {
    manifest: {
      schemaVersion: 2,
      profile: "selector",
      capabilities: { surfaceEdgeRendering: true },
      stepHash,
      bbox: { min: [-100, -100, -100], max: [100, 100, 100] },
      tables: {
        occurrenceColumns: ["id", "path", "name", "sourceName", "parentId", "transform", "bbox", "shapeStart", "shapeCount", "faceStart", "faceCount", "edgeStart", "edgeCount"],
        shapeColumns: ["id", "occurrenceId", "ordinal", "kind", "name", "sourceName", "bbox", "center", "area", "volume", "faceStart", "faceCount", "edgeStart", "edgeCount"],
        faceColumns: ["id", "occurrenceId", "shapeId", "ordinal", "surfaceType", "area", "center", "normal", "bbox", "edgeStart", "edgeCount", "relevance", "flags", "params", "triangleStart", "triangleCount"],
        edgeColumns: EDGE_COLUMNS,
      },
      occurrences: [["o1", "1", null, null, null, null, { min: [-100, -100, -100], max: [100, 100, 100] }, 0, shapes.length, 0, faces.length, 0, edges.length]],
      shapes,
      faces,
      edges,
      faceProxy: { source: "surf", runsView: "faceRuns", runColumns: ["occurrenceRow", "primitiveIndex", "triangleStart", "triangleCount", "faceRow"] },
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

// ---- the eager edge-chain endpoints this replaced, verbatim -------------------------------

function eagerEdgeChainEndpoints(reference, proxy) {
  const { segmentStart: start, segmentCount: count, curveType, params } = reference.pickData;
  const points = proxy.edgePositions, indices = proxy.edgeIndices;
  if (!Number.isInteger(start) || !Number.isInteger(count) || count < 1 || (start + count) * 2 > indices.length) return [];
  const vertices = new Map();
  for (let i = start * 2; i < (start + count) * 2; i += 2) {
    const pair = [indices[i], indices[i + 1]].map(index => Array.from(points.slice(index * 3, index * 3 + 3)));
    if (pair.some(point => point.length !== 3 || !point.every(Number.isFinite))) return [];
    if (JSON.stringify(pair[0]) === JSON.stringify(pair[1])) continue;
    for (let j = 0; j < 2; j++) {
      const key = JSON.stringify(pair[j]);
      const vertex = vertices.get(key) || { point: pair[j], neighbor: pair[1-j], count: 0 };
      vertex.count++; vertices.set(key, vertex);
    }
  }
  if ([...vertices.values()].some(vertex => vertex.count > 2)) return [];
  const ends = [...vertices.values()].filter(vertex => vertex.count === 1);
  if (ends.length !== 2) return [];
  return ends.map(({ point, neighbor }) => {
    let direction = neighbor.map((value, i) => value - point[i]);
    if (curveType === 'circle' && params?.center?.length === 3 && params?.axis?.length === 3) {
      const radial = point.map((value, i) => value - params.center[i]);
      const a = params.axis;
      const tangent = [a[1]*radial[2]-a[2]*radial[1], a[2]*radial[0]-a[0]*radial[2], a[0]*radial[1]-a[1]*radial[0]];
      const sign = tangent.reduce((sum, value, i) => sum + value * direction[i], 0) < 0 ? -1 : 1;
      direction = tangent.map(value => value * sign);
    }
    const length = Math.hypot(...direction);
    return { point, direction: length ? direction.map(value => value / length) : [0, 0, 0] };
  });
}

test("lazy chain endpoints equal the eager ones, placed or not", () => {
  let open = 0;
  for (let seed = 1; seed <= 6; seed += 1) {
    const bundle = makeBundle(seed, { faces: 7, detail: seed });
    for (const transform of [null, placement(seed)]) {
      const runtime = buildSelectorRuntime(bundle, { transform, partId: "o1.2", remapOccurrenceId: "o1.2" });
      for (const reference of runtime.references.filter((item) => item.selectorType === "edge")) {
        const expected = eagerEdgeChainEndpoints(reference, runtime.proxy);
        assert.deepStrictEqual(reference.pickData.chainEndpoints, expected, `${reference.id} under ${transform ? "a placement" : "no placement"}`);
        if (expected.length) open += 1;
      }
    }
  }
  // The fixture exercises both answers.
  assert.ok(open > 20);
});

test("copying, composing and posing references never computes their chain endpoints", () => {
  const bundle = makeBundle(3, { faces: 4 });
  // Edge rows that point at vertices past the end of the positions: reading an endpoint throws.
  const poisoned = { ...bundle, buffers: { ...bundle.buffers, edgePositions: undefined } };
  const runtimes = [0, 1].map((index) => buildSelectorRuntime(poisoned, { transform: placement(index), partId: `o1.${index + 1}`, remapOccurrenceId: `o1.${index + 1}` }));
  const composed = composeSelectorRuntimes(runtimes);
  const composer = createSelectorRuntimeComposer();
  const incremental = composer.compose([0, 1].map((index) => buildSelectorCompositionPart(poisoned, { transform: placement(index), partId: `o1.${index + 1}`, remapOccurrenceId: `o1.${index + 1}` })));
  const posed = buildTransformedSelectorRuntime(composed, { "o1.1": placement(4) });
  for (const runtime of [composed, incremental, posed]) {
    const edge = runtime.references.find((reference) => reference.selectorType === "edge");
    assert.equal(typeof Object.getOwnPropertyDescriptor(edge.pickData, "chainEndpoints").get, "function");
    assert.throws(() => edge.pickData.chainEndpoints, TypeError);
  }
});

test("a posed runtime's chain endpoints are the posed eager endpoints", () => {
  const bundle = makeBundle(5, { faces: 6, detail: 2 });
  const composed = composeSelectorRuntimes([0, 1, 2].map((index) => buildSelectorRuntime(bundle, {
    transform: placement(index), partId: `o1.${index + 1}`, remapOccurrenceId: `o1.${index + 1}`,
  })));
  const pose = { "o1.2": placement(7) };
  const posed = buildTransformedSelectorRuntime(composed, pose);
  // The same pose over endpoints read first (data, not accessor) — the path taken before.
  const readFirst = { ...composed, references: composed.references.map((reference) => (
    reference.selectorType === "edge" ? { ...reference, pickData: { ...reference.pickData } } : reference
  )) };
  assert.deepStrictEqual(posed.references, buildTransformedSelectorRuntime(readFirst, pose).references);
});

// ---- the incremental composer against composing whole runtimes -----------------------------

function occurrenceOptions(index, { copyCadPath = "cars/hypercar.step", single = false } = {}) {
  const id = `o1.${Math.floor(index / 3) + 1}.${(index % 3) + 1}`;
  return { copyCadPath, partId: single ? "" : id, transform: placement(index), remapOccurrenceId: id };
}

function composeFresh(items) {
  return composeSelectorRuntimes(items.map(({ bundle, options }) => buildSelectorRuntime(bundle, options)));
}

function assertSameComposition(actual, expected, label) {
  // Reading every reference's chain endpoints on both sides compares Group edges' input too.
  assert.deepStrictEqual(actual, expected, label);
}

test("the incremental composer composes exactly what composing whole runtimes does", () => {
  const bundles = [makeBundle(11, { faces: 5 }), makeBundle(12, { faces: 3, shapes: 1, faceProxy: false }), makeBundle(13, { faces: 6, detail: 2 })];
  const fine = makeBundle(13, { faces: 6, detail: 5 });
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
    ["a component swapped to a finer level", [item(6), item(2, fine), item(3), item(4), item(5, fine)]],
    ["swapped back", [item(6), item(2), item(3), item(4), item(5)]],
    ["appended after a swap", [item(6), item(2), item(3), item(4), item(5), item(7), item(8)]],
    ["down to one part", [item(4)]],
    ["a changed revision", [item(0, revised, { copyCadPath: "cars/hypercar_v2.step" }), item(1, revised, { copyCadPath: "cars/hypercar_v2.step" })]],
    ["a single-component part", [item(0, bundles[0], { single: true }), item(1, bundles[0], { single: true })]],
  ];
  for (const [label, items] of steps) {
    const incremental = composer.compose(items.map((entry) => partFor(entry, `${entry.index}:${bundles.indexOf(entry.bundle)}:${entry.bundle === fine ? "fine" : entry.bundle === revised ? "revised" : ""}:${entry.options.partId}:${entry.options.copyCadPath}`)));
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

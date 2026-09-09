import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildTopologyDisplayEdgePositions,
  buildTopologyDisplayEdgePolylines,
  hasTopologyDisplayEdgeClassification,
  hasTopologyDisplayEdgeProxy,
  shouldUseTopologyDisplayEdges,
  stitchTopologyDisplayEdgePolylines
} from "./topologyDisplayEdges.js";

function runtimeWithEdges(edges, options = {}) {
  return {
    surfaceEdgeRendering: options.surfaceEdgeRendering,
    edges,
    proxy: {
      edgePositions: new Float32Array([
        0, 0, 0,
        1, 0, 0,
        2, 0, 0,
        3, 0, 0,
        4, 0, 0,
        5, 0, 0
      ]),
      edgeIndices: new Uint32Array([0, 1, 2, 3, 4, 5]),
      edgeIds: new Uint32Array([0, 1, 2])
    }
  };
}

test("topology display edges expose proxy availability", () => {
  assert.equal(hasTopologyDisplayEdgeProxy(runtimeWithEdges([])), true);
  assert.equal(hasTopologyDisplayEdgeProxy({
    proxy: {
      edgePositions: new Float32Array(0),
      edgeIndices: new Uint32Array(0)
    }
  }), false);
});

test("classified topology display edges expose v2 availability", () => {
  assert.equal(hasTopologyDisplayEdgeClassification(runtimeWithEdges([])), true);
  assert.equal(hasTopologyDisplayEdgeClassification(runtimeWithEdges([{ relevance: 1 }])), true);
  assert.equal(shouldUseTopologyDisplayEdges(runtimeWithEdges([{ relevance: 1 }])), true);
  assert.equal(shouldUseTopologyDisplayEdges(runtimeWithEdges([{ relevance: 1 }], { surfaceEdgeRendering: true })), false);
});

test("topology display edges use every valid proxy segment", () => {
  const positions = buildTopologyDisplayEdgePositions(runtimeWithEdges([
    { flags: 0, visibilityClass: "feature" },
    { flags: 4, visibilityClass: "seam" },
    { flags: 8, visibilityClass: "tangent" }
  ]));

  assert.deepEqual(Array.from(positions), [
    0, 0, 0, 1, 0, 0,
    2, 0, 0, 3, 0, 0,
    4, 0, 0, 5, 0, 0
  ]);
});

test("topology display edges can filter by visibility class", () => {
  const positions = buildTopologyDisplayEdgePositions(runtimeWithEdges([
    { flags: 0, visibilityClass: "feature" },
    { flags: 4, visibilityClass: "seam" },
    { flags: 8, visibilityClass: "tangent" }
  ]), { visibilityClasses: ["feature"] });

  assert.deepEqual(Array.from(positions), [
    0, 0, 0, 1, 0, 0
  ]);
});

test("topology display edges can filter by focused occurrence ids", () => {
  const runtime = runtimeWithEdges([
    { occurrenceId: "part-a", segmentStart: 0, segmentCount: 1 },
    { occurrenceId: "part-b", segmentStart: 1, segmentCount: 1 },
    { occurrenceId: "part-a.child", segmentStart: 2, segmentCount: 1 }
  ]);

  assert.deepEqual(Array.from(buildTopologyDisplayEdgePositions(runtime, { includePartIds: ["part-a"] })), [
    0, 0, 0, 1, 0, 0,
    4, 0, 0, 5, 0, 0
  ]);
  assert.deepEqual(Array.from(buildTopologyDisplayEdgePositions(runtime, { excludePartIds: ["part-a"] })), [
    2, 0, 0, 3, 0, 0
  ]);
});

test("topology display edge polylines can filter by visibility class and focused ids", () => {
  const runtime = runtimeWithEdges([
    { occurrenceId: "part-a", visibilityClass: "feature", segmentStart: 0, segmentCount: 1 },
    { occurrenceId: "part-b", visibilityClass: "tangent", segmentStart: 1, segmentCount: 1 },
    { occurrenceId: "part-a.child", visibilityClass: "tangent", segmentStart: 2, segmentCount: 1 }
  ]);

  const polylines = buildTopologyDisplayEdgePolylines(runtime, {
    includePartIds: ["part-a"],
    visibilityClasses: ["tangent"]
  });

  assert.equal(polylines.length, 1);
  assert.deepEqual(Array.from(polylines[0]), [
    4, 0, 0,
    5, 0, 0
  ]);
});

test("topology display edges preserve continuous CAD edge polylines", () => {
  const polylines = buildTopologyDisplayEdgePolylines({
    edges: [
      {
        flags: 0,
        visibilityClass: "feature",
        segmentStart: 0,
        segmentCount: 2
      }
    ],
    proxy: {
      edgePositions: new Float32Array([
        0, 0, 0,
        1, 0, 0,
        2, 0, 0
      ]),
      edgeIndices: new Uint32Array([0, 1, 1, 2]),
      edgeIds: new Uint32Array([0, 0])
    }
  });

  assert.equal(polylines.length, 1);
  assert.deepEqual(Array.from(polylines[0]), [
    0, 0, 0,
    1, 0, 0,
    2, 0, 0
  ]);
});

test("topology display edges stitch adjacent CAD edge fragments", () => {
  const polylines = buildTopologyDisplayEdgePolylines({
    edges: [
      {
        flags: 0,
        visibilityClass: "tangent",
        segmentStart: 0,
        segmentCount: 1
      },
      {
        flags: 0,
        visibilityClass: "tangent",
        segmentStart: 1,
        segmentCount: 1
      }
    ],
    proxy: {
      edgePositions: new Float32Array([
        0, 0, 0,
        1, 0, 0,
        2, 0, 0
      ]),
      edgeIndices: new Uint32Array([0, 1, 1, 2])
    }
  });

  assert.equal(polylines.length, 1);
  assert.deepEqual(Array.from(polylines[0]), [
    0, 0, 0,
    1, 0, 0,
    2, 0, 0
  ]);
});

test("topology polyline stitching handles reversed fragments", () => {
  const polylines = stitchTopologyDisplayEdgePolylines([
    new Float32Array([
      0, 0, 0,
      1, 0, 0
    ]),
    new Float32Array([
      2, 0, 0,
      1, 0, 0
    ])
  ]);

  assert.equal(polylines.length, 1);
  assert.deepEqual(Array.from(polylines[0]), [
    0, 0, 0,
    1, 0, 0,
    2, 0, 0
  ]);
});

test("all topology display edges include every valid proxy segment", () => {
  const positions = buildTopologyDisplayEdgePositions(runtimeWithEdges([
    { flags: 0, relevance: 10 },
    { flags: 4, relevance: 0 },
    { flags: 8, relevance: 0 }
  ]));

  assert.deepEqual(Array.from(positions), [
    0, 0, 0, 1, 0, 0,
    2, 0, 0, 3, 0, 0,
    4, 0, 0, 5, 0, 0
  ]);
});

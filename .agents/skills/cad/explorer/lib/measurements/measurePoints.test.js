import assert from "node:assert/strict";
import { test } from "node:test";

import { buildMeasurePointReferences } from "./measurePoints.js";

test("creates a client-side measure point for a circular edge center", () => {
  const points = buildMeasurePointReferences([{
    id: "edge-circle",
    selectorType: "edge",
    displaySelector: "models/part.step#edge[4]",
    normalizedSelector: "models/part.step#edge[4]",
    pickData: {
      curveType: "circle",
      center: [10, 20, 30],
      params: { radius: 5 }
    }
  }]);

  assert.equal(points.length, 1);
  assert.equal(points[0].selectorType, "vertex");
  assert.equal(points[0].summary, "Circle center");
  assert.deepEqual(points[0].pickData.center, [10, 20, 30]);
  assert.equal(points[0].pickData.measurePointKind, "circle-center");
});

test("accepts typed-array circle centers from selector metadata", () => {
  const points = buildMeasurePointReferences([{
    id: "edge-circle",
    selectorType: "edge",
    displaySelector: "models/part.step#edge[4]",
    normalizedSelector: "models/part.step#edge[4]",
    pickData: {
      curveType: "circle",
      center: new Float32Array([1, 2, 3]),
      params: { radius: 5 }
    }
  }]);

  assert.equal(points.length, 1);
  assert.deepEqual(points[0].pickData.center, [1, 2, 3]);
});

test("creates client-side measure points for edge endpoints from the selector proxy", () => {
  const selectorRuntime = {
    proxy: {
      edgePositions: new Float32Array([
        0, 0, 0,
        3, 4, 0
      ]),
      edgeIndices: new Uint32Array([0, 1]),
      edgeIds: new Uint32Array([7])
    }
  };
  const points = buildMeasurePointReferences([{
    id: "edge-line",
    selectorType: "edge",
    displaySelector: "models/part.step#edge[7]",
    normalizedSelector: "models/part.step#edge[7]",
    pickData: {
      curveType: "line",
      rowIndex: 7,
      params: {}
    }
  }], selectorRuntime);

  assert.equal(points.length, 2);
  assert.deepEqual(points.map((point) => point.pickData.center), [[0, 0, 0], [3, 4, 0]]);
  assert.deepEqual(points.map((point) => point.pickData.measurePointKind), ["edge-endpoint", "edge-endpoint"]);
});

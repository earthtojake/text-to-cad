import assert from "node:assert/strict";
import { test } from "node:test";

import {
  measurementForReferences,
  measurementsForReferences
} from "./measureTopology.js";

test("measures exact edge length from topology metadata", () => {
  const result = measurementForReferences([{
    id: "edge-1",
    selectorType: "edge",
    pickData: {
      curveType: "line",
      length: 12.5,
      center: [1, 2, 3],
      params: {}
    }
  }]);

  assert.equal(result.title, "Edge length");
  assert.equal(result.value, 12.5);
  assert.equal(result.detail, "Midpoint 1, 2, 3");
});

test("measures radius from circular edge metadata", () => {
  const results = measurementsForReferences([{
    id: "edge-arc",
    selectorType: "edge",
    pickData: {
      curveType: "circle",
      length: 18.85,
      center: [0, 0, 0],
      params: { radius: 3 }
    }
  }]);

  assert.equal(results[0].title, "Radius");
  assert.equal(results[0].value, 3);
  assert.equal(results[0].detail, "Diameter 6 mm | Center 0, 0, 0");
  assert.equal(results[1].title, "Edge length");
});

test("measures radius from cylindrical face metadata", () => {
  const result = measurementForReferences([{
    id: "face-1",
    selectorType: "face",
    pickData: {
      surfaceType: "cylinder",
      params: { radius: 3 }
    }
  }]);

  assert.equal(result.title, "Radius");
  assert.equal(result.value, 3);
  assert.equal(result.detail, "Diameter 6 mm");
});

test("measures surface area from face metadata", () => {
  const result = measurementForReferences([{
    id: "face-2",
    selectorType: "face",
    pickData: {
      surfaceType: "plane",
      area: 42.125,
      params: {}
    }
  }]);

  assert.equal(result.title, "Surface area");
  assert.equal(result.value, 42.125);
  assert.equal(result.unit, "mm2");
});

test("measures the acute angle between two line edges", () => {
  const result = measurementForReferences([
    {
      id: "e1",
      selectorType: "edge",
      pickData: {
        curveType: "line",
        params: { direction: [1, 0, 0] }
      }
    },
    {
      id: "e2",
      selectorType: "edge",
      pickData: {
        curveType: "line",
        params: { direction: [0, 1, 0] }
      }
    }
  ]);

  assert.equal(result.title, "Edge angle");
  assert.equal(result.unit, "deg");
  assert.equal(result.value, 90);
});

test("measures line edge angle from proxy endpoints when vertices are absent", () => {
  const selectorRuntime = {
    proxy: {
      edgePositions: new Float32Array([
        0, 0, 0,
        4, 0, 0,
        0, 0, 0,
        0, 3, 0
      ]),
      edgeIndices: new Uint32Array([0, 1, 2, 3]),
      edgeIds: new Uint32Array([0, 1])
    }
  };
  const result = measurementForReferences([
    {
      id: "e1",
      selectorType: "edge",
      pickData: { curveType: "line", rowIndex: 0, segmentStart: 0, segmentCount: 1, params: {} }
    },
    {
      id: "e2",
      selectorType: "edge",
      pickData: { curveType: "line", rowIndex: 1, segmentStart: 1, segmentCount: 1, params: {} }
    }
  ], selectorRuntime);

  assert.equal(result.title, "Edge angle");
  assert.equal(result.value, 90);
});

test("reports midpoint distance for two selected edges without vertex selectors", () => {
  const results = measurementsForReferences([
    {
      id: "e1",
      selectorType: "edge",
      pickData: { curveType: "line", center: [0, 0, 0], params: { direction: [1, 0, 0] } }
    },
    {
      id: "e2",
      selectorType: "edge",
      pickData: { curveType: "line", center: [3, 4, 12], params: { direction: [1, 0, 0] } }
    }
  ]);

  const distance = results.find((result) => result.kind === "point-distance");
  assert.equal(distance.title, "Midpoint distance");
  assert.equal(distance.value, 13);
});

test("measures distance between client-side measure points", () => {
  const result = measurementForReferences([
    {
      id: "p1",
      selectorType: "vertex",
      pickData: { kind: "measure-point", center: [0, 0, 0] }
    },
    {
      id: "p2",
      selectorType: "vertex",
      pickData: { kind: "measure-point", center: [6, 8, 0] }
    }
  ]);

  assert.equal(result.title, "Point distance");
  assert.equal(result.value, 10);
  assert.equal(result.detail, "0, 0, 0 to 6, 8, 0");
});

test("measures the acute angle between two planar faces", () => {
  const result = measurementForReferences([
    {
      id: "f1",
      selectorType: "face",
      pickData: {
        surfaceType: "plane",
        normal: [1, 0, 0]
      }
    },
    {
      id: "f2",
      selectorType: "face",
      pickData: {
        surfaceType: "plane",
        normal: [0, 0, 1]
      }
    }
  ]);

  assert.equal(result.title, "Face angle");
  assert.equal(result.unit, "deg");
  assert.equal(result.value, 90);
});

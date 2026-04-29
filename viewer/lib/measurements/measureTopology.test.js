import assert from "node:assert/strict";
import { test } from "node:test";

import { measurementForReferences } from "./measureTopology.js";

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

test("measures point-to-point distance between two vertices", () => {
  const result = measurementForReferences([
    {
      id: "v1",
      selectorType: "vertex",
      pickData: { center: [0, 0, 0] }
    },
    {
      id: "v2",
      selectorType: "vertex",
      pickData: { center: [3, 4, 12] }
    }
  ]);

  assert.equal(result.title, "Point distance");
  assert.equal(result.value, 13);
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
  assert.equal(result.unit, "mm^2");
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

  assert.equal(result.title, "Angle");
  assert.equal(result.unit, "deg");
  assert.equal(result.value, 90);
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

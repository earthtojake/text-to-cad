import assert from "node:assert/strict";
import test from "node:test";

import { DRAWING_TOOL } from "./drawingTools.js";
import {
  buildCirclePixelPolygon,
  buildGuessedFillPolygon,
  buildPolygonFromFilledMask,
  buildRectanglePixelCorners,
  findNearestOpenSeed,
  floodFillInterior,
  getDrawingBoundaryPixelPoints,
  maxDrawingStrokeOrdinal,
  normalizePolygonPoints,
  pairNearbyBoundaryEndpoints,
  traceMaskLoops
} from "./drawingCanvas.js";

function rectangleBoundaryMask(width, height, left, top, right, bottom) {
  const mask = new Uint8Array(width * height);
  for (let x = left; x <= right; x += 1) {
    mask[top * width + x] = 1;
    mask[bottom * width + x] = 1;
  }
  for (let y = top; y <= bottom; y += 1) {
    mask[y * width + left] = 1;
    mask[y * width + right] = 1;
  }
  return mask;
}

test("drawing canvas helpers preserve overlay id and shape geometry behavior", () => {
  assert.equal(maxDrawingStrokeOrdinal([
    { id: "stroke-7" },
    { id: "ignored" },
    { id: "stroke-12" }
  ]), 12);

  assert.deepEqual(buildRectanglePixelCorners([10, 20], [30, 40]), [
    [10, 20],
    [30, 20],
    [30, 40],
    [10, 40]
  ]);
  assert.deepEqual(getDrawingBoundaryPixelPoints({
    tool: DRAWING_TOOL.RECTANGLE,
    points: [{ x: 0.1, y: 0.2 }, { x: 0.3, y: 0.4 }]
  }, 100, 100), [
    [10, 20],
    [30, 20],
    [30, 40],
    [10, 40],
    [10, 20]
  ]);

  const circle = buildCirclePixelPolygon([10, 10], [20, 10], 4);
  assert.equal(circle.length, 13);
  assert.deepEqual(circle[0], [20, 10]);
});

test("boundary endpoint pairing preserves nearest non-conflicting connectors", () => {
  const pairs = pairNearbyBoundaryEndpoints([
    { strokeId: "a", point: [0, 0], allowSelfConnect: false },
    { strokeId: "a", point: [1, 0], allowSelfConnect: false },
    { strokeId: "b", point: [1.2, 0], allowSelfConnect: false },
    { strokeId: "c", point: [10, 0], allowSelfConnect: false }
  ], 0.5);

  assert.deepEqual(pairs, [
    [[1, 0], [1.2, 0]]
  ]);
  assert.deepEqual(pairNearbyBoundaryEndpoints([
    { strokeId: "freehand", point: [0, 0], allowSelfConnect: true },
    { strokeId: "freehand", point: [0.25, 0], allowSelfConnect: true }
  ], 0.5), [
    [[0, 0], [0.25, 0]]
  ]);
});

test("fill mask helpers recover a bounded interior polygon", () => {
  const width = 10;
  const height = 10;
  const boundaryMask = rectangleBoundaryMask(width, height, 2, 2, 7, 7);

  assert.deepEqual(findNearestOpenSeed(boundaryMask, width, height, 2, 2), [2, 1]);

  const filled = floodFillInterior(boundaryMask, width, height, [4, 4]);
  assert.equal(filled.area, 16);
  assert.equal(filled.touchesEdge, false);
  assert.deepEqual(filled.seed, [4, 4]);

  const loops = traceMaskLoops(filled.mask, width, height);
  assert.equal(loops.length, 1);
  assert.ok(loops[0].length >= 4);

  const polygon = buildPolygonFromFilledMask(filled.mask, width, height, filled.seed);
  assert.ok(polygon.length >= 3);
  for (const point of polygon) {
    assert.ok(point.x >= 0 && point.x <= 1);
    assert.ok(point.y >= 0 && point.y <= 1);
  }
});

test("guessed fill polygon uses radial boundary hits when exact fill is unavailable", () => {
  const width = 40;
  const height = 40;
  const boundaryMask = rectangleBoundaryMask(width, height, 10, 10, 29, 29);
  const polygon = buildGuessedFillPolygon(boundaryMask, width, height, [20, 20]);

  assert.ok(polygon.length >= 12);
  for (const point of polygon) {
    assert.ok(point.x >= 0 && point.x <= 1);
    assert.ok(point.y >= 0 && point.y <= 1);
  }
  assert.deepEqual(normalizePolygonPoints([[0, 0], [20, 40]], width, height), [
    { x: 0, y: 0 },
    { x: 0.5, y: 1 }
  ]);
});

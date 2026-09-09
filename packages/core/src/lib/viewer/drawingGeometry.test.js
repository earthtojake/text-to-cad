import assert from "node:assert/strict";
import test from "node:test";

import { DRAWING_TOOL } from "./drawingTools.js";
import {
  buildDrawingPoint,
  distancePointToSegment2d,
  distanceToStrokeInPixels,
  drawingPointToPixels,
  drawingToolNeedsTwoPoints,
  getDrawingStrokePoints,
  getFillStrokePoints,
  isClosedDrawingStroke,
  isFillBoundaryStroke,
  isFillStroke,
  isSurfaceLineStroke,
  pointInPolygon2d,
  strokeLengthInPixels
} from "./drawingGeometry.js";

test("drawing point conversion clamps pointer positions to canvas bounds", () => {
  const canvas = {
    getBoundingClientRect: () => ({
      left: 10,
      top: 20,
      width: 200,
      height: 100
    })
  };

  assert.deepEqual(buildDrawingPoint({ clientX: 110, clientY: 70 }, canvas), { x: 0.5, y: 0.5 });
  assert.deepEqual(buildDrawingPoint({ clientX: -10, clientY: 200 }, canvas), { x: 0, y: 1 });
  assert.deepEqual(drawingPointToPixels({ x: 0.25, y: 0.75 }, 400, 200), [100, 150]);
});

test("drawing stroke classification mirrors overlay behavior", () => {
  assert.equal(isFillStroke({ tool: DRAWING_TOOL.FILL }), true);
  assert.equal(isSurfaceLineStroke({ tool: DRAWING_TOOL.SURFACE_LINE, surfaceLine: { referenceId: "face" } }), true);
  assert.equal(isSurfaceLineStroke({ tool: DRAWING_TOOL.SURFACE_LINE }), false);
  assert.equal(isClosedDrawingStroke({ tool: DRAWING_TOOL.RECTANGLE }), true);
  assert.equal(isClosedDrawingStroke({ tool: DRAWING_TOOL.CIRCLE }), true);
  assert.equal(isFillBoundaryStroke({ tool: DRAWING_TOOL.LINE }), true);
  assert.equal(isFillBoundaryStroke({ tool: DRAWING_TOOL.FILL }), false);
  assert.equal(isFillBoundaryStroke({ tool: DRAWING_TOOL.SURFACE_LINE }), false);
  assert.equal(drawingToolNeedsTwoPoints(DRAWING_TOOL.DOUBLE_ARROW), true);
  assert.equal(drawingToolNeedsTwoPoints(DRAWING_TOOL.FILL), false);
});

test("stroke helpers filter invalid points and compute screen length", () => {
  const stroke = {
    points: [
      { x: 0, y: 0 },
      { x: 0.3, y: 0.4 },
      { x: Number.NaN, y: 1 }
    ],
    fillPoints: [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
      { x: Infinity, y: 1 }
    ]
  };

  assert.deepEqual(getDrawingStrokePoints(stroke), [{ x: 0, y: 0 }, { x: 0.3, y: 0.4 }]);
  assert.deepEqual(getFillStrokePoints(stroke), [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }]);
  assert.equal(strokeLengthInPixels({
    points: [
      { x: 0, y: 0 },
      { x: 0.3, y: 0.4 }
    ]
  }, 100, 100), 50);
});

test("distance helpers cover line, rectangle, circle, and fill strokes", () => {
  assert.equal(distancePointToSegment2d([5, 5], [0, 0], [10, 0]), 5);
  assert.equal(pointInPolygon2d([5, 5], [[0, 0], [10, 0], [10, 10], [0, 10]]), true);
  assert.equal(pointInPolygon2d([12, 5], [[0, 0], [10, 0], [10, 10], [0, 10]]), false);

  assert.equal(distanceToStrokeInPixels(
    { x: 0.5, y: 0.5 },
    { tool: DRAWING_TOOL.LINE, points: [{ x: 0, y: 0.5 }, { x: 1, y: 0.5 }] },
    100,
    100
  ), 0);
  assert.equal(distanceToStrokeInPixels(
    { x: 0.5, y: 0.5 },
    { tool: DRAWING_TOOL.RECTANGLE, points: [{ x: 0.25, y: 0.25 }, { x: 0.75, y: 0.75 }] },
    100,
    100
  ), 25);
  assert.equal(distanceToStrokeInPixels(
    { x: 0.5, y: 0.8 },
    { tool: DRAWING_TOOL.CIRCLE, points: [{ x: 0.5, y: 0.5 }, { x: 0.8, y: 0.5 }] },
    100,
    100
  ), 0);
  assert.equal(distanceToStrokeInPixels(
    { x: 0.5, y: 0.5 },
    {
      tool: DRAWING_TOOL.FILL,
      fillPoints: [{ x: 0.25, y: 0.25 }, { x: 0.75, y: 0.25 }, { x: 0.75, y: 0.75 }, { x: 0.25, y: 0.75 }]
    },
    100,
    100
  ), 0);
});

import assert from "node:assert/strict";
import test from "node:test";
import {
  boxFromDrag,
  boxSamplePoints,
  segmentInBox,
  segmentTouchesBox,
  triangleTouchesBox
} from "./boxSelect.js";

const window_ = boxFromDrag({ x: 10, y: 10 }, { x: 110, y: 60 });

test("a drag draws the same box whichever way it goes", () => {
  for (const box of [window_, boxFromDrag({ x: 110, y: 60 }, { x: 10, y: 10 }), boxFromDrag({ x: 10, y: 60 }, { x: 110, y: 10 })]) {
    assert.deepEqual(box, { left: 10, top: 10, right: 110, bottom: 60, width: 100, height: 50 });
  }
});

test("a segment touches the box with an end inside it or by crossing it, never by passing beside it", () => {
  assert.equal(segmentTouchesBox(window_, 50, 30, 500, 500), true);
  assert.equal(segmentTouchesBox(window_, 0, 30, 200, 30), true);
  assert.equal(segmentTouchesBox(window_, 0, 0, 200, 0), false);
  assert.equal(segmentTouchesBox(window_, 0, 15, 5, 0), false);
  assert.equal(segmentTouchesBox(window_, 0, 70, 120, 0), true);
});

test("the part of a segment in the box is the span between where it enters and leaves", () => {
  assert.deepEqual(segmentInBox(window_, 0, 30, 200, 30), [0.05, 0.55]);
  assert.deepEqual(segmentInBox(window_, 20, 20, 30, 30), [0, 1]);
  assert.equal(segmentInBox(window_, 0, 0, 200, 0), null);
});

test("a triangle touches the box by a side, or by covering it whole", () => {
  assert.equal(triangleTouchesBox(window_, -1000, -1000, 1000, -1000, 0, 1000), true);
  assert.equal(triangleTouchesBox(window_, 200, 200, 300, 200, 250, 300), false);
  assert.equal(triangleTouchesBox(window_, 50, 30, 300, 200, 250, 300), true);
});

test("the sample grid covers the box evenly, stays inside it, and is bounded", () => {
  const points = boxSamplePoints(window_, { max: 50, minSpacing: 1 });
  assert.ok(points.length <= 50 && points.length >= 40);
  assert.ok(points.every(({ x, y }) => x > 10 && x < 110 && y > 10 && y < 60));
  // No closer than the minimum spacing, and a box smaller than that still casts at its centre.
  assert.equal(boxSamplePoints({ left: 0, top: 0, right: 30, bottom: 30 }, { max: 10000, minSpacing: 3 }).length, 100);
  assert.deepEqual(boxSamplePoints({ left: 0, top: 0, right: 2, bottom: 2 }), [{ x: 1, y: 1 }]);
});

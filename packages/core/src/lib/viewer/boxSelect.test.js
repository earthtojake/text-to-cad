import assert from "node:assert/strict";
import test from "node:test";
import {
  boundsTouchBox,
  boxFromBounds,
  boxFromDrag,
  boxSamplePoints,
  circleTouchesBox,
  trianglePoints,
  pointInPolygon,
  polygonTouchesBox,
  polylineTouchesBox,
  segmentInBox,
  segmentTouchesBox,
  triangleTouchesBox
} from "./boxSelect.js";

const drawn = boxFromDrag({ x: 10, y: 10 }, { x: 110, y: 60 });

test("a drag draws the same box whichever way it goes", () => {
  for (const box of [drawn, boxFromDrag({ x: 110, y: 60 }, { x: 10, y: 10 }), boxFromDrag({ x: 10, y: 60 }, { x: 110, y: 10 })]) {
    assert.deepEqual(box, { left: 10, top: 10, right: 110, bottom: 60, width: 100, height: 50 });
  }
});

test("a segment touches the box with an end inside it or by crossing it, never by passing beside it", () => {
  assert.equal(segmentTouchesBox(drawn, 50, 30, 500, 500), true);
  assert.equal(segmentTouchesBox(drawn, 0, 30, 200, 30), true);
  assert.equal(segmentTouchesBox(drawn, 0, 0, 200, 0), false);
  assert.equal(segmentTouchesBox(drawn, 0, 15, 5, 0), false);
  assert.equal(segmentTouchesBox(drawn, 0, 70, 120, 0), true);
});

test("the part of a segment in the box is the span between where it enters and leaves", () => {
  assert.deepEqual(segmentInBox(drawn, 0, 30, 200, 30), [0.05, 0.55]);
  assert.deepEqual(segmentInBox(drawn, 20, 20, 30, 30), [0, 1]);
  assert.equal(segmentInBox(drawn, 0, 0, 200, 0), null);
});

test("a triangle touches the box by a side, or by covering it whole", () => {
  assert.equal(triangleTouchesBox(drawn, -1000, -1000, 1000, -1000, 0, 1000), true);
  assert.equal(triangleTouchesBox(drawn, 200, 200, 300, 200, 250, 300), false);
  assert.equal(triangleTouchesBox(drawn, 50, 30, 300, 200, 250, 300), true);
});

test("a region's points lie in its triangles and in the box, and find a sliver thinner than the lattice", () => {
  const box = { left: 100, top: 100, right: 200, bottom: 160 };
  const inTriangle = (x, y, [ax, ay, bx, by, cx, cy]) => {
    const d1 = (bx - ax) * (y - ay) - (by - ay) * (x - ax), d2 = (cx - bx) * (y - by) - (cy - by) * (x - bx), d3 = (ax - cx) * (y - cy) - (ay - cy) * (x - cx);
    return !((d1 < 0 || d2 < 0 || d3 < 0) && (d1 > 0 || d2 > 0 || d3 > 0));
  };
  // A big triangle across the box: points in it and in the box.
  const big = [50, 50, 400, 120, 120, 400];
  const inside = trianglePoints(box, big);
  assert.ok(inside.length > 100 && inside.every(({ x, y }) => inTriangle(x, y, big) && x >= 100 && x <= 200 && y >= 100 && y <= 160));
  // However large, about `max` of them.
  assert.ok(trianglePoints({ left: 0, top: 0, right: 1e4, bottom: 1e4 }, [0, 0, 1e4, 0, 0, 1e4], { max: 100 }).length <= 110);
  // A corner poking 0.5 px into the box's top, between the lattice's points: still a point in it.
  const tip = [140, 60, 160, 60, 150, 100.5];
  const poked = trianglePoints(box, tip);
  assert.ok(poked.length >= 1 && poked.every(({ x, y }) => y >= 100 && y <= 100.5 && inTriangle(x, y, tip)));
  // Wholly outside: nothing.
  assert.deepEqual(trianglePoints(box, [10, 10, 20, 10, 10, 20]), []);
});

test("the sample grid covers the box evenly, stays inside it, and is bounded", () => {
  const points = boxSamplePoints(drawn, { max: 50, minSpacing: 1 });
  assert.ok(points.length <= 50 && points.length >= 40);
  assert.ok(points.every(({ x, y }) => x > 10 && x < 110 && y > 10 && y < 60));
  // No closer than the minimum spacing, and a box smaller than that still casts at its centre.
  assert.equal(boxSamplePoints({ left: 0, top: 0, right: 30, bottom: 30 }, { max: 10000, minSpacing: 3 }).length, 100);
  assert.deepEqual(boxSamplePoints({ left: 0, top: 0, right: 2, bottom: 2 }), [{ x: 1, y: 1 }]);
});

test("a line of ink touches the box by a segment, its closing one when closed, or by its drawn width", () => {
  const vee = [{ x: 0, y: 0 }, { x: 60, y: 120 }, { x: 120, y: 0 }];
  assert.equal(polylineTouchesBox(drawn, vee), true);
  // A hook round the box, which its closing segment crosses only when it is closed.
  const hook = [{ x: 0, y: 30 }, { x: 0, y: 0 }, { x: 200, y: 0 }, { x: 200, y: 30 }];
  assert.equal(polylineTouchesBox(drawn, hook), false);
  assert.equal(polylineTouchesBox(drawn, hook, { closed: true }), true);
  // A stroke 6px wide passing 2px above the box reaches it; a hairline there does not.
  const above = [{ x: 0, y: 8 }, { x: 200, y: 8 }];
  assert.equal(polylineTouchesBox(drawn, above), false);
  assert.equal(polylineTouchesBox(drawn, above, { radius: 3 }), true);
  assert.equal(polylineTouchesBox(drawn, [{ x: 50, y: 30 }]), true);
  assert.equal(polylineTouchesBox(drawn, []), false);
});

test("a filled outline touches the box by its outline, or by covering it whole", () => {
  const around = [{ x: -100, y: -100 }, { x: 300, y: -100 }, { x: 300, y: 300 }, { x: -100, y: 300 }];
  assert.equal(polylineTouchesBox(drawn, around, { closed: true }), false);
  assert.equal(polygonTouchesBox(drawn, around), true);
  assert.equal(polygonTouchesBox(drawn, [{ x: 200, y: 200 }, { x: 300, y: 200 }, { x: 250, y: 300 }]), false);
  assert.equal(pointInPolygon(0, 0, around), true);
  assert.equal(pointInPolygon(400, 0, around), false);
});

test("a flat picture's own frame: bounds, a disc, and [x, y] points are judged by the same rule", () => {
  const box = boxFromBounds([10, 10, 20, 20]);
  assert.deepEqual([box.left, box.top, box.right, box.bottom, box.width], [10, 10, 20, 20, 10]);
  assert.equal(boundsTouchBox(box, [20, 0, 30, 10]), true);
  assert.equal(boundsTouchBox(box, [21, 0, 30, 30]), false);
  assert.equal(boundsTouchBox(box, null), false);
  // A via near the corner: its rim reaches in, its centre does not.
  assert.equal(circleTouchesBox(box, 22, 22, 3), true);
  assert.equal(circleTouchesBox(box, 23, 23, 3), false);
  assert.equal(circleTouchesBox(box, 15, 15, 0.1), true);
  assert.equal(polylineTouchesBox(box, [[0, 15], [30, 15]]), true);
  assert.equal(polygonTouchesBox(box, [[0, 0], [40, 0], [40, 40], [0, 40]]), true);
  assert.equal(pointInPolygon(5, 5, [[0, 0], [10, 0], [10, 10]]), true);
});


import assert from "node:assert/strict";
import test from "node:test";

import {
  DRAWING_ZOOM_IN_LIMIT,
  DRAWING_ZOOM_OUT_LIMIT,
  clampScale,
  fitTransform,
  modelToScreen,
  panTransform,
  sameTransform,
  screenToModel,
  zoomLimits,
  zoomTransform
} from "./transform.js";

test("fit centres the box and leaves the margin on the tight axis", () => {
  const transform = fitTransform([0, 0, 100, 50], 400, 300, { margin: 20 });
  // 360 / 100 = 3.6 across, 260 / 50 = 5.2 up: width is the binding constraint.
  assert.equal(transform.scale, 3.6);
  const [cx, cy] = modelToScreen(transform, 50, 25);
  assert.equal(cx, 200);
  assert.equal(cy, 150);
  const [leftX] = modelToScreen(transform, 0, 0);
  assert.equal(leftX, 20);
});

test("fit flips y: the top of the drawing is the top of the pane", () => {
  const transform = fitTransform([0, 0, 10, 10], 200, 200, { margin: 0 });
  const [, topScreenY] = modelToScreen(transform, 5, 10);
  const [, bottomScreenY] = modelToScreen(transform, 5, 0);
  assert.ok(topScreenY < bottomScreenY, `expected model y=10 above y=0, got ${topScreenY} and ${bottomScreenY}`);
  assert.equal(topScreenY, 0);
  assert.equal(bottomScreenY, 200);
});

test("a drawing with no extent on one axis fits by the other", () => {
  const transform = fitTransform([0, 5, 100, 5], 400, 300, { margin: 0 });
  assert.equal(transform.scale, 4);
  assert.deepEqual(modelToScreen(transform, 50, 5), [200, 150]);
});

test("a single point cannot set a scale, so it sits in the middle at 1:1", () => {
  const transform = fitTransform([7, 7, 7, 7], 400, 300, { margin: 0 });
  assert.equal(transform.scale, 1);
  assert.deepEqual(modelToScreen(transform, 7, 7), [200, 150]);
});

test("the margin never eats more than half the pane", () => {
  const transform = fitTransform([0, 0, 10, 10], 20, 20, { margin: 16 });
  assert.ok(transform.scale > 0, `expected a positive scale, got ${transform.scale}`);
  assert.equal(transform.scale, 1); // 20 * 0.5 usable / 10 model units
});

test("fitting an empty drawing is refused by name", () => {
  assert.throws(() => fitTransform(null, 400, 300), /empty drawing \(bounds: null\)/);
  assert.throws(() => fitTransform([0, 0, 1], 400, 300), /minX, minY, maxX, maxY/);
  assert.throws(() => fitTransform([0, 0, 1, Number.NaN], 400, 300), /finite numbers/);
});

test("fitting into a pane with no size is refused by name", () => {
  assert.throws(() => fitTransform([0, 0, 1, 1], 0, 300), /positive size/);
  assert.throws(() => fitTransform([0, 0, 1, 1], 400, -1), /positive size/);
});

test("screenToModel inverts modelToScreen", () => {
  const transform = fitTransform([-30, 12, 70, 90], 640, 480);
  for (const [x, y] of [[-30, 12], [0, 0], [70, 90], [11.25, -4.5]]) {
    const [sx, sy] = modelToScreen(transform, x, y);
    const [mx, my] = screenToModel(transform, sx, sy);
    assert.ok(Math.abs(mx - x) < 1e-9 && Math.abs(my - y) < 1e-9, `round trip lost (${x}, ${y})`);
  }
});

test("pan moves the picture by the screen delta and leaves the scale alone", () => {
  const before = fitTransform([0, 0, 10, 10], 200, 200, { margin: 0 });
  const after = panTransform(before, 17, -4);
  assert.equal(after.scale, before.scale);
  const [x0, y0] = modelToScreen(before, 3, 3);
  const [x1, y1] = modelToScreen(after, 3, 3);
  assert.equal(x1 - x0, 17);
  assert.equal(y1 - y0, -4);
});

test("zoom keeps the anchor point fixed", () => {
  const before = fitTransform([0, 0, 100, 100], 400, 400, { margin: 0 });
  const anchor = { x: 310, y: 90 };
  const [modelX, modelY] = screenToModel(before, anchor.x, anchor.y);
  const after = zoomTransform(before, anchor, 2.5, zoomLimits(before.scale));
  assert.equal(after.scale, before.scale * 2.5);
  const [sx, sy] = modelToScreen(after, modelX, modelY);
  assert.ok(Math.abs(sx - anchor.x) < 1e-9, `anchor x moved to ${sx}`);
  assert.ok(Math.abs(sy - anchor.y) < 1e-9, `anchor y moved to ${sy}`);
});

test("zoom is clamped to a range relative to the fitted scale", () => {
  const fitted = fitTransform([0, 0, 100, 100], 400, 400, { margin: 0 });
  const limits = zoomLimits(fitted.scale);
  const anchor = { x: 200, y: 200 };
  let deep = fitted;
  for (let step = 0; step < 40; step += 1) {
    deep = zoomTransform(deep, anchor, 2, limits);
  }
  assert.equal(deep.scale, fitted.scale * DRAWING_ZOOM_IN_LIMIT);
  let far = fitted;
  for (let step = 0; step < 40; step += 1) {
    far = zoomTransform(far, anchor, 0.5, limits);
  }
  assert.equal(far.scale, fitted.scale / DRAWING_ZOOM_OUT_LIMIT);
  // Clamping shortens the step; it must not slide the picture.
  assert.ok(Math.abs(modelToScreen(deep, 50, 50)[0] - anchor.x) < 1e-6);
});

test("a clamped zoom still anchors exactly at the limit", () => {
  const fitted = { scale: 2, offsetX: 10, offsetY: 20 };
  const limits = { minScale: 1, maxScale: 3 };
  const anchor = { x: 120, y: 44 };
  const [modelX, modelY] = screenToModel(fitted, anchor.x, anchor.y);
  const after = zoomTransform(fitted, anchor, 10, limits);
  assert.equal(after.scale, 3);
  const [sx, sy] = modelToScreen(after, modelX, modelY);
  assert.ok(Math.abs(sx - anchor.x) < 1e-9 && Math.abs(sy - anchor.y) < 1e-9);
});

test("bad zoom inputs are refused by name", () => {
  assert.throws(() => zoomTransform({ scale: 1, offsetX: 0, offsetY: 0 }, { x: 0, y: 0 }, 0, zoomLimits(1)), /positive factor/);
  assert.throws(() => zoomLimits(0), /positive fitted scale/);
  assert.throws(() => clampScale(1, { minScale: 4, maxScale: 2 }), /minScale <= maxScale/);
});

test("sameTransform tells a resize's drift from a pan", () => {
  const base = { scale: 3.6, offsetX: 20, offsetY: 280 };
  assert.ok(sameTransform(base, { ...base }));
  assert.ok(sameTransform(base, { scale: 3.6 + 1e-12, offsetX: 20, offsetY: 280 }));
  assert.ok(!sameTransform(base, { ...base, offsetX: 21 }));
  assert.ok(!sameTransform(base, null));
  assert.ok(sameTransform(null, null));
});

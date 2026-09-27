import assert from "node:assert/strict";
import test from "node:test";

import { readFileView, writeFileView } from "../kit/shell/fileView.js";
import { drawingTransformCamera, readDrawingTransform } from "./drawingTransform.js";

const TRANSFORM = { scale: 10.8, offsetX: 60, offsetY: 664 };

test("a moved view round-trips as the file view's camera", () => {
  const camera = drawingTransformCamera(TRANSFORM, true);
  assert.deepEqual(camera, TRANSFORM);
  const stored = JSON.parse(JSON.stringify(writeFileView({ camera })));
  assert.deepEqual(readDrawingTransform(readFileView(stored).camera), TRANSFORM);
});

test("an untouched view stores nothing, so it reopens fitted to whatever pane it lands in", () => {
  assert.equal(drawingTransformCamera(TRANSFORM, false), null);
  assert.equal(drawingTransformCamera(null, true), null);
  assert.equal(readDrawingTransform(null), null);
  assert.equal(readDrawingTransform(undefined), null);
});

test("a scene camera, or a broken transform, is nothing stored, never a half-restored view", () => {
  assert.equal(readDrawingTransform({ position: [0, 0, 1], target: [0, 0, 0], up: [0, 1, 0], zoom: 1 }), null);
  for (const transform of [{}, [1, 2, 3], { scale: 0, offsetX: 1, offsetY: 2 },
    { scale: -3, offsetX: 1, offsetY: 2 }, { scale: 1, offsetX: Number.NaN, offsetY: 2 },
    { scale: 1, offsetX: 1 }, "dxf-view"]) {
    assert.equal(readDrawingTransform(transform), null, JSON.stringify(transform));
  }
});

test("the stored transform carries nothing but the three numbers", () => {
  const camera = drawingTransformCamera({ ...TRANSFORM, bounds: [0, 0, 1, 1], file: "plate.dxf" }, true);
  assert.deepEqual(Object.keys(camera), ["scale", "offsetX", "offsetY"]);
});

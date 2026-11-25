import assert from "node:assert/strict";
import test from "node:test";

import { readFileView, writeFileView } from "../shell/fileView.js";
import { flatViewRecord, readFlatView } from "./flatView.js";

const TRANSFORM = { scale: 10.8, offsetX: 60, offsetY: 664 };
const PANE = { width: 1224, height: 800 };

test("a moved view round-trips as the file view's camera, with the pane it was framed in", () => {
  const camera = flatViewRecord(TRANSFORM, PANE);
  assert.deepEqual(camera, { ...TRANSFORM, ...PANE });
  const stored = JSON.parse(JSON.stringify(writeFileView({ camera })));
  assert.deepEqual(readFlatView(readFileView(stored).camera), { ...TRANSFORM, ...PANE });
});

test("an untouched view stores nothing, so it reopens fitted to whatever pane it lands in", () => {
  assert.equal(readFlatView(null), null);
  assert.equal(readFlatView(undefined), null);
  const stored = JSON.parse(JSON.stringify(writeFileView({ camera: readFlatView(null) })));
  assert.equal(readFileView(stored).camera, null);
});

test("a record an earlier build stored, the transform alone, comes back as it is", () => {
  assert.deepEqual(readFlatView(TRANSFORM), TRANSFORM);
  // A pane that is not one (no size, or half of one) is no pane: the transform alone.
  for (const pane of [{ width: 0, height: 800 }, { width: 1224 }, { width: -1, height: 2 }, { width: "1224", height: 800 }]) {
    assert.deepEqual(readFlatView({ ...TRANSFORM, ...pane }), TRANSFORM, JSON.stringify(pane));
    assert.deepEqual(flatViewRecord(TRANSFORM, pane), TRANSFORM, JSON.stringify(pane));
  }
});

test("a scene camera, or a broken transform, is nothing stored, never a half-restored view", () => {
  assert.equal(readFlatView({ position: [0, 0, 1], target: [0, 0, 0], up: [0, 1, 0], zoom: 1 }), null);
  for (const transform of [{}, [1, 2, 3], { scale: 0, offsetX: 1, offsetY: 2 },
    { scale: -3, offsetX: 1, offsetY: 2 }, { scale: 1, offsetX: Number.NaN, offsetY: 2 },
    { scale: 1, offsetX: 1 }, "dxf-view"]) {
    assert.equal(readFlatView(transform), null, JSON.stringify(transform));
  }
});

test("the stored view carries the transform and its pane, nothing else", () => {
  const camera = flatViewRecord({ ...TRANSFORM, bounds: [0, 0, 1, 1], file: "plate.dxf" }, { ...PANE, pixelRatio: 2 });
  assert.deepEqual(Object.keys(camera), ["scale", "offsetX", "offsetY", "width", "height"]);
  assert.deepEqual(Object.keys(readFlatView({ ...camera, sheet: "/" })), ["scale", "offsetX", "offsetY", "width", "height"]);
});

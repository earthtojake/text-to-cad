import assert from "node:assert/strict";
import test from "node:test";

import { measureLabelText, measurementMark } from "./measureDimension.js";
import { measurementFromPicks } from "./measurement.js";
import { meshMeasurePick } from "./meshMeasure.js";
import { GLB_SCENE_UNITS, threeMfSceneUnits } from "./sceneUnits.js";

const hit = { id: "n3", point: [40, 30, 0] };

test("a pick on a mesh is the point on its surface under the pointer, never a triangle's corner or side", () => {
  const mm = threeMfSceneUnits("millimeter");
  assert.deepEqual(meshMeasurePick(hit, mm), { point: [40, 30, 0], snapKind: "surface", referenceId: "n3:s", units: mm, approximate: true });
  assert.equal(meshMeasurePick({ id: "n3", point: [1, 1] }, mm), null, "no point, no pick");
  assert.equal(meshMeasurePick(null, mm), null);
});

test("a mesh's length is in its file's unit and says it is approximate, wherever it is read", () => {
  // A GLB's scene is in millimetres; its file is in metres.
  const a = meshMeasurePick({ ...hit, point: [0, 0, 0] }, GLB_SCENE_UNITS);
  const b = meshMeasurePick({ ...hit, point: [100, 0, 0] }, GLB_SCENE_UNITS);
  const measurement = measurementFromPicks(a, b);
  assert.deepEqual([measurement.euclidean, measurement.unit, measurement.approximate, measurement.perpendicular], [0.1, "m", true, null]);
  assert.equal(measureLabelText(measurement), "≈ 0.1000 m");
  assert.equal(measurementMark({ pickA: a, pickB: b, measurement, colorIndex: 0 }).label, "≈ 0.1000 m", "the label its mark carries");
  assert.equal(measureLabelText(measurementFromPicks({ point: [0, 0, 0] }, { point: [3, 4, 0] })), "5.00 mm", "a STEP's stays exact");
});

test("a 3MF's declared unit is one of the 3MF unit names", () => {
  assert.throws(() => threeMfSceneUnits("furlong"), /micron, millimeter, centimeter, inch, foot, meter/);
});

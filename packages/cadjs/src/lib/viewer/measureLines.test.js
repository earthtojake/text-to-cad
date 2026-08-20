import assert from "node:assert/strict";
import test from "node:test";

import { dimensionEndpoints, measureDimensionSegments } from "./measureLines.js";

test("dimensionEndpoints returns the raw pick points for a point-to-point measurement", () => {
  const endpoints = dimensionEndpoints({ point: [0, 0, 0] }, { point: [3, 4, 0] }, null);
  assert.deepEqual(endpoints.start, [0, 0, 0]);
  assert.deepEqual(endpoints.end, [3, 4, 0]);
  assert.equal(dimensionEndpoints({ point: [0, 0, 0] }, {}, null), null);
});

test("measureDimensionSegments uses the face normal for perpendicular labels", () => {
  const reference = { pickData: { normal: [0, 0, 1] } };
  const dimension = measureDimensionSegments(
    { point: [0, 0, 0], reference },
    { point: [4, 3, 5], reference },
    { perpendicular: 5 }
  );
  assert.deepEqual(dimension.start, [0, 0, 0]);
  assert.deepEqual(dimension.end, [0, 0, 5]);
  assert.equal(dimension.segments.length, 5);
});

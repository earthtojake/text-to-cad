import assert from "node:assert/strict";
import test from "node:test";
import {
  CAD_DEFAULT_VERTICAL_FOV_DEGREES,
  explicitViewerFocalLength,
  perspectiveDistanceScale
} from "./cameraLens.js";

test("a missing Render lens returns the perspective camera to CAD's native field of view", () => {
  assert.equal(CAD_DEFAULT_VERTICAL_FOV_DEGREES, 48);
  assert.equal(explicitViewerFocalLength(null), null);
  assert.equal(explicitViewerFocalLength(undefined), null);
  assert.equal(explicitViewerFocalLength("50"), null);
  assert.equal(explicitViewerFocalLength(0), null);
  assert.equal(explicitViewerFocalLength(50), 50);
});

test("lens changes preserve projected subject scale by changing camera distance", () => {
  assert.equal(perspectiveDistanceScale(48, 48), 1);
  assert.ok(perspectiveDistanceScale(48, 30) > 1);
  assert.ok(perspectiveDistanceScale(30, 48) < 1);
  assert.equal(perspectiveDistanceScale(0, 30), 1);
});

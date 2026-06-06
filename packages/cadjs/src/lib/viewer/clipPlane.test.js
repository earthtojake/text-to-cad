import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildStepClipPatch,
  clipAxisBounds,
  clipAxisPosition,
  normalizeStepClipSettings,
  pointVisibleByClipPlane,
  stepClipSettingsEqual
} from "./clipPlane.js";

const bounds = {
  min: [-10, 2, 100],
  max: [30, 12, 200]
};

test("normalizes STEP clip settings with safe defaults", () => {
  assert.deepEqual(normalizeStepClipSettings(), {
    enabled: false,
    axis: "x",
    offset: 0,
    offsets: { x: 0, y: 0, z: 0 },
    invert: false
  });

  assert.deepEqual(normalizeStepClipSettings({
    enabled: true,
    axis: "Y",
    offset: 2,
    invert: true
  }), {
    enabled: true,
    axis: "y",
    offset: 1,
    offsets: { x: 0, y: 1, z: 0 },
    invert: true
  });
  assert.deepEqual(normalizeStepClipSettings({
    axis: "z",
    offset: 0.25
  }), {
    enabled: true,
    axis: "z",
    offset: 0.25,
    offsets: { x: 0, y: 0, z: 0.25 },
    invert: false
  });
  assert.deepEqual(normalizeStepClipSettings({
    enabled: true,
    axis: "z",
    offset: 0
  }), {
    enabled: false,
    axis: "z",
    offset: 0,
    offsets: { x: 0, y: 0, z: 0 },
    invert: false
  });
  assert.deepEqual(normalizeStepClipSettings({ axis: "bad", offset: -1 }), {
    enabled: false,
    axis: "x",
    offset: 0,
    offsets: { x: 0, y: 0, z: 0 },
    invert: false
  });
});

test("resolves clip axis bounds and normalized position", () => {
  assert.deepEqual(clipAxisBounds(bounds, "x"), { min: -10, max: 30 });
  assert.deepEqual(clipAxisBounds({ min: [5], max: [-5] }, "x"), { min: -5, max: 5 });
  assert.equal(clipAxisPosition(bounds, { axis: "z", offset: 0.25 }), 125);
});

test("clip plane point visibility matches the side rendered by Three.js clipping", () => {
  const clipPlane = {
    distanceToPoint(point) {
      return point.distance;
    }
  };

  assert.equal(pointVisibleByClipPlane(clipPlane, { distance: 2 }), true);
  assert.equal(pointVisibleByClipPlane(clipPlane, { distance: 0 }), true);
  assert.equal(pointVisibleByClipPlane(clipPlane, { distance: -1e-6 }), true);
  assert.equal(pointVisibleByClipPlane(clipPlane, { distance: -0.01 }), false);
  assert.equal(pointVisibleByClipPlane(null, { distance: -0.01 }), true);
});

test("builds normalized clip patches", () => {
  assert.deepEqual(buildStepClipPatch({ axis: "x", offset: 0.5 }, { enabled: true, axis: "z" }), {
    enabled: false,
    axis: "z",
    offset: 0,
    offsets: { x: 0.5, y: 0, z: 0 },
    invert: false
  });
  const withZOffset = buildStepClipPatch(null, { axis: "z", offset: 0.25 });
  assert.deepEqual(withZOffset, {
    enabled: true,
    axis: "z",
    offset: 0.25,
    offsets: { x: 0, y: 0, z: 0.25 },
    invert: false
  });
  assert.deepEqual(buildStepClipPatch(withZOffset, { axis: "x" }), {
    enabled: false,
    axis: "x",
    offset: 0,
    offsets: { x: 0, y: 0, z: 0.25 },
    invert: false
  });
});

test("compares clip settings after normalization", () => {
  assert.equal(stepClipSettingsEqual({ enabled: true, axis: "X", offset: 0.5 }, { enabled: true, axis: "x", offset: 0.5000001 }), true);
  assert.equal(stepClipSettingsEqual({ enabled: true, offset: 0.5 }, { enabled: false, offset: 0.5 }), false);
});

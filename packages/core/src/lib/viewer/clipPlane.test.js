import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildStepClipPatch,
  clipAmount,
  clipAtForAmount,
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

test("a supplied clip cuts unless it says enabled: false; none at all is no clip", () => {
  assert.deepEqual(normalizeStepClipSettings(), { enabled: false, axis: "x", invert: false });
  assert.deepEqual(normalizeStepClipSettings({}), { enabled: true, axis: "x", invert: false });
  assert.deepEqual(normalizeStepClipSettings({ axis: "Y", at: -4.5, invert: true }),
    { enabled: true, axis: "y", invert: true, at: -4.5 });
  assert.deepEqual(normalizeStepClipSettings({ enabled: false, at: 3 }),
    { enabled: false, axis: "x", invert: false, at: 3 }, "off keeps where the plane stands");
  assert.deepEqual(normalizeStepClipSettings({ axis: "bad", at: "3" }), { enabled: true, axis: "x", invert: false },
    "validation refuses what the normalizer drops");
  const at = normalizeStepClipSettings({ axis: "z", at: 0 });
  assert.deepEqual(normalizeStepClipSettings(at), at, "normalization is idempotent");
});

test("the plane stands at `at`, else the middle of the bounds", () => {
  assert.deepEqual(clipAxisBounds(bounds, "x"), { min: -10, max: 30 });
  assert.deepEqual(clipAxisBounds({ min: [5], max: [-5] }, "x"), { min: -5, max: 5 });
  assert.equal(clipAxisPosition(bounds, { axis: "z" }), 150);
  assert.equal(clipAxisPosition(bounds, { axis: "y", at: -4.5 }), -4.5, "the bounds do not move it");
  assert.equal(clipAxisPosition(null, { axis: "y", at: 7 }), 7);
});

test("the slider's amount is the share cut away, both ways and on both sides", () => {
  // Keeping the lower side cuts from the top; inverted, from the bottom.
  assert.equal(clipAmount({ axis: "x", at: 20 }, bounds), 0.25);
  assert.equal(clipAmount({ axis: "x", at: 20, invert: true }, bounds), 0.75);
  assert.equal(clipAtForAmount({ axis: "x" }, bounds, 0.25), 20);
  assert.equal(clipAtForAmount({ axis: "x", invert: true }, bounds, 0.75), 20);
  for (const invert of [false, true]) {
    for (const amount of [0, 0.123, 0.5, 1]) {
      const at = clipAtForAmount({ axis: "z", invert }, bounds, amount);
      assert.ok(Math.abs(clipAmount({ axis: "z", at, invert }, bounds) - amount) < 1e-12);
    }
  }
  assert.equal(clipAmount({ axis: "z" }, bounds), 0.5, "no `at` is the middle");
  assert.equal(clipAmount({ enabled: false, axis: "z", at: 120 }, bounds), 0, "off cuts nothing");
  assert.equal(clipAmount({ axis: "z", at: 250 }, bounds), 0, "above the top cuts nothing");
  assert.equal(clipAmount({ axis: "z", at: 50 }, bounds), 1, "below the bottom cuts everything");
  assert.equal(clipAmount({ axis: "z", at: 50, invert: true }, bounds), 0);
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

test("a patch merges into the clip, and a new axis without a coordinate drops the old one", () => {
  const cut = { enabled: true, axis: "y", invert: false, at: 4 };
  assert.deepEqual(buildStepClipPatch(cut, { at: 6 }), { ...cut, at: 6 });
  assert.deepEqual(buildStepClipPatch(cut, { enabled: false, at: 12 }), { ...cut, enabled: false, at: 12 });
  assert.deepEqual(buildStepClipPatch(cut, { invert: true }), { ...cut, invert: true }, "flipping never moves the plane");
  assert.deepEqual(buildStepClipPatch(cut, { axis: "z" }), { enabled: true, axis: "z", invert: false });
  assert.deepEqual(buildStepClipPatch(cut, { axis: "z", at: 150 }), { enabled: true, axis: "z", invert: false, at: 150 });
  assert.deepEqual(buildStepClipPatch(cut, { axis: "y" }), cut, "the same axis keeps it");
  const off = { enabled: false, axis: "x", invert: false };
  assert.deepEqual(buildStepClipPatch(null, { axis: "z" }), { ...off, axis: "z" }, "an axis alone is no cut");
  assert.deepEqual(buildStepClipPatch(off, { axis: "y", invert: true }), { ...off, axis: "y", invert: true });
  assert.deepEqual(buildStepClipPatch(off, { at: 3 }), { ...off, enabled: true, at: 3 },
    "placing the plane is a cut, whatever the clip was");
  assert.deepEqual(buildStepClipPatch(null, { axis: "y", at: 5 }), { enabled: true, axis: "y", invert: false, at: 5 });
});

test("compares clip settings after normalization", () => {
  assert.equal(stepClipSettingsEqual({ axis: "X", at: 2 }, { enabled: true, axis: "x", at: 2, invert: false }), true);
  assert.equal(stepClipSettingsEqual({ axis: "y", at: -4.5 }, { axis: "y", at: 4.5 }), false);
  assert.equal(stepClipSettingsEqual({ axis: "y" }, { axis: "y", at: 0 }), false);
  assert.equal(stepClipSettingsEqual({ at: 1 }, { enabled: false, at: 1 }), false);
});

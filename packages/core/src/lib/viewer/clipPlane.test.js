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
    offsets: { y: 2 },
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
    offsets: { z: 0.25 }
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
    offsets: { z: 0 }
  }), {
    enabled: true,
    axis: "z",
    offset: 0,
    offsets: { x: 0, y: 0, z: 0 },
    invert: false
  });
  assert.deepEqual(normalizeStepClipSettings({ axis: "bad", offsets: { x: -1 } }), {
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
  assert.equal(clipAxisPosition(bounds, { axis: "z", offsets: { z: 0.25 } }), 125);
});

test("scalar offset is the selected-axis fallback, including zero and inversion", () => {
  const scalar = normalizeStepClipSettings({ axis: "z", offset: 0.25, offsets: { x: 0.6 }, invert: true });
  assert.deepEqual(scalar, {
    enabled: true, axis: "z", offset: 0.25,
    offsets: { x: 0.6, y: 0, z: 0.25 }, invert: true
  });
  assert.equal(clipAxisPosition(bounds, scalar), 125);
  assert.deepEqual(normalizeStepClipSettings(scalar), scalar, "normalization remains idempotent");
  const explicitZero = normalizeStepClipSettings({ enabled: true, axis: "y", offset: 0, invert: true });
  assert.equal(explicitZero.enabled, true);
  assert.equal(explicitZero.invert, true);
  assert.equal(clipAxisPosition(bounds, explicitZero), 2);
  assert.equal(normalizeStepClipSettings({ axis: "z", offset: 0.75, offsets: { z: 0 } }).offset, 0,
    "a present per-axis zero wins over the scalar fallback");
  assert.equal(normalizeStepClipSettings({ offset: 0.5 }).offsets.x, 0.5, "omitted axis defaults to X");
});

test("scalar clip patches update their selected axis without erasing other axes", () => {
  const current = { axis: "x", offsets: { x: 0.5, z: 0.3 } };
  const patched = buildStepClipPatch(current, { axis: "z", offset: 0.7, invert: true });
  assert.deepEqual(patched, {
    enabled: true, axis: "z", offset: 0.7,
    offsets: { x: 0.5, y: 0, z: 0.7 }, invert: true
  });
  const cleared = buildStepClipPatch(patched, { offset: 0 });
  assert.equal(cleared.offset, 0);
  assert.equal(cleared.enabled, false);
  assert.equal(cleared.offsets.x, 0.5);
  assert.equal(buildStepClipPatch(current, { offset: 0.7, offsets: { x: 0 } }).offset, 0);
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
  assert.deepEqual(
    buildStepClipPatch({ axis: "x", offsets: { x: 0.5 } }, { enabled: true, axis: "z" }),
    {
      enabled: true,
      axis: "z",
      offset: 0,
      offsets: { x: 0.5, y: 0, z: 0 },
      invert: false
    }
  );
  const withZOffset = buildStepClipPatch(null, { axis: "z", offsets: { z: 0.25 } });
  assert.deepEqual(withZOffset, {
    enabled: true,
    axis: "z",
    offset: 0.25,
    offsets: { x: 0, y: 0, z: 0.25 },
    invert: false
  });
  assert.deepEqual(buildStepClipPatch(withZOffset, { axis: "x" }), {
    enabled: true,
    axis: "x",
    offset: 0,
    offsets: { x: 0, y: 0, z: 0.25 },
    invert: false
  });
});

test("compares clip settings after normalization", () => {
  assert.equal(
    stepClipSettingsEqual(
      { enabled: true, axis: "X", offsets: { x: 0.5 } },
      { enabled: true, axis: "x", offsets: { x: 0.5000001 } }
    ),
    true
  );
  assert.equal(
    stepClipSettingsEqual(
      { enabled: true, offsets: { x: 0.5 } },
      { enabled: false, offsets: { x: 0.5 } }
    ),
    false
  );
});

test('explicitly enabling Clip starts at the center unless coordinates were supplied', () => {
  assert.equal(normalizeStepClipSettings({ enabled: true }).offset, 0.5);
  assert.deepEqual(normalizeStepClipSettings({ enabled: true, axis: 'z' }).offsets, { x: 0, y: 0, z: 0.5 });
  assert.equal(normalizeStepClipSettings({ enabled: true, offset: 0 }).offset, 0);
  assert.equal(normalizeStepClipSettings({ enabled: false }).offset, 0);
});

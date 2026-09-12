import assert from "node:assert/strict";
import test from "node:test";

import {
  advanceUrdfJointValues,
  easeUrdfJointAnimation,
  interpolateUrdfJointValues,
  jointValueMapsClose,
  URDF_JOINT_ANIMATION_DURATION_MS,
  URDF_JOINT_ANIMATION_FOLLOW_MS
} from "./jointAnimation.js";

function roundedMap(values) {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [key, Math.round(value * 1000) / 1000])
  );
}

test("easeUrdfJointAnimation clamps progress to the animation range", () => {
  assert.equal(easeUrdfJointAnimation(-1), 0);
  assert.equal(easeUrdfJointAnimation(1.5), 1);
  assert.equal(easeUrdfJointAnimation(0), 0);
  assert.equal(easeUrdfJointAnimation(1), 1);
  assert.equal(easeUrdfJointAnimation(0.5), 0.5);
  assert.ok(easeUrdfJointAnimation(0.25) < 0.25);
  assert.ok(easeUrdfJointAnimation(0.75) > 0.75);
});

test("URDF joint animations use a deliberate smooth duration", () => {
  assert.equal(URDF_JOINT_ANIMATION_DURATION_MS, 840);
  assert.equal(URDF_JOINT_ANIMATION_FOLLOW_MS, 240);
});

test("interpolateUrdfJointValues eases each target joint value", () => {
  const halfway = interpolateUrdfJointValues(
    { shoulder: 0, elbow: 10 },
    { shoulder: 90, elbow: -10 },
    0.5
  );

  assert.equal(halfway.done, false);
  assert.deepEqual(roundedMap(halfway.values), {
    elbow: 0,
    shoulder: 45
  });
});

test("interpolateUrdfJointValues uses the shortest wrapped path for continuous joints", () => {
  const halfway = interpolateUrdfJointValues(
    { shoulder: -170 },
    { shoulder: 170 },
    0.5,
    undefined,
    new Set(["shoulder"])
  );

  assert.equal(halfway.done, false);
  assert.deepEqual(roundedMap(halfway.values), {
    shoulder: -180
  });
});

test("interpolateUrdfJointValues snaps to target values at completion", () => {
  const result = interpolateUrdfJointValues(
    { shoulder: 89.9995, elbow: 10 },
    { shoulder: 90 },
    1
  );

  assert.equal(result.done, true);
  assert.deepEqual(result.values, { shoulder: 90 });
});

test("advanceUrdfJointValues follows moving targets without overshooting", () => {
  const first = advanceUrdfJointValues({ shoulder: 0 }, { shoulder: 90 }, 16);
  const redirected = advanceUrdfJointValues(first.values, { shoulder: 30 }, 16);

  assert.equal(first.done, false);
  assert.ok(first.values.shoulder > 0);
  assert.ok(first.values.shoulder < 90);
  assert.equal(redirected.done, false);
  assert.ok(redirected.values.shoulder > first.values.shoulder);
  assert.ok(redirected.values.shoulder < 30);
});

test("advanceUrdfJointValues snaps close values to the target", () => {
  const result = advanceUrdfJointValues({ shoulder: 89.9995 }, { shoulder: 90 }, 16);

  assert.equal(result.done, true);
  assert.deepEqual(result.values, { shoulder: 90 });
});

test("advanceUrdfJointValues rotates continuous joints along the shortest path", () => {
  const result = advanceUrdfJointValues(
    { shoulder: -170 },
    { shoulder: 170 },
    16,
    undefined,
    undefined,
    new Set(["shoulder"])
  );

  assert.equal(result.done, false);
  assert.ok(result.values.shoulder < -170);
  assert.ok(result.values.shoulder > -190);
});

test("jointValueMapsClose compares normalized finite joint values", () => {
  assert.equal(jointValueMapsClose({ shoulder: "90" }, { shoulder: 90.0005 }), true);
  assert.equal(jointValueMapsClose({ shoulder: 90, elbow: 0 }, { shoulder: 90 }), false);
  assert.equal(jointValueMapsClose({ shoulder: 90 }, { shoulder: 91 }), false);
});

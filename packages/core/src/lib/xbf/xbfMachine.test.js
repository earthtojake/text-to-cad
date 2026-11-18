// A machine's twin: each axis's joint by its name and kind, and a reading's pose.
import assert from "node:assert/strict";
import test from "node:test";

import { xbfMachineJoints, xbfMachinePose } from "./xbfMachine.js";

const pair = (label, type, limits = [[0, 300]]) => ({ label, type, limits, units: [type === "revolute" ? "deg" : "mm"] });
const gantry = {
  links: [], pairs: [pair("x", "prismatic", [[0, 800]]), pair("Y_axis", "prismatic"), pair("axis-z", "prismatic", [[-100, 0]]),
    pair("a", "revolute", [[null, null]]), pair("spindle", "revolute")]
};

test("each axis is the joint named for it, of its kind", () => {
  const { joints, refused } = xbfMachineJoints(gantry);
  assert.deepEqual(Object.keys(joints), ["X", "Y", "Z", "A"]);
  assert.deepEqual(joints.X, { pair: "x", min: 0, max: 800 });
  assert.deepEqual(joints.A, { pair: "a", min: null, max: null });
  assert.deepEqual(refused, []);
});

test("a joint of the wrong kind, or two for one axis, is refused and never chosen", () => {
  const { joints, refused } = xbfMachineJoints({ links: [], pairs: [pair("x", "revolute"), pair("y", "prismatic"), pair("Y_AXIS", "prismatic")] });
  assert.deepEqual(joints, {});
  assert.match(refused[0].reason, /x is a revolute joint; axis X needs a prismatic one/);
  assert.match(refused[1].reason, /y and Y_AXIS both name axis Y/);
});

test("a reading poses its axes, one past its joint's travel at the limit, and says what it could not", () => {
  const mapping = xbfMachineJoints(gantry);
  const { values, unmatched, idle, past } = xbfMachinePose(mapping, { spindle: [10] },
    { axes: { X: 812.5, Y: 40, Z: -20, B: 90 } });
  assert.deepEqual(values, { spindle: [10], x: [800], Y_axis: [40], "axis-z": [-20] });
  assert.deepEqual(unmatched, ["B"]);
  assert.deepEqual(idle, ["A"]);
  assert.deepEqual(past, ["X"]);
});

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  cloneJointValueMap,
  findBestMatchingJointValueState,
  jointValueMapsClose,
  jointValueSubsetClose
} from "./robotMotion.js";

test("control value helpers normalize maps and compare subsets", () => {
  assert.deepEqual(cloneJointValueMap({ " shoulder ": "12.5", empty: Number.NaN, " ": 4 }), {
    shoulder: 12.5,
    empty: 0
  });
  assert.equal(jointValueMapsClose({ a: 1, b: 2.0004 }, { b: 2, a: 1 }), true);
  assert.equal(jointValueMapsClose({ a: 1 }, { a: 1, b: 0 }), false);
  assert.equal(jointValueSubsetClose({ shoulder: 90.0004, slide: 0.12, extra: 10 }, { shoulder: 90, slide: 0.12 }), true);
  assert.equal(jointValueSubsetClose({ shoulder: 91 }, { shoulder: 90 }), false);
  assert.equal(jointValueSubsetClose({ shoulder: 90 }, {}), false);
});

test("best group-state match ignores partial presets when other controls changed", () => {
  const states = [
    { id: "gripper/open", values: { gripper: 0 } },
    { id: "arm/home", values: { shoulder: 45, elbow: -30 } },
    { id: "gripper/closed", values: { gripper: 20 } }
  ];
  const defaults = { shoulder: 45, elbow: -30, gripper: 0 };

  assert.equal(findBestMatchingJointValueState(states, defaults, defaults)?.id, "arm/home");
  assert.equal(findBestMatchingJointValueState(states, { ...defaults, gripper: 12 }, defaults), null);
  assert.equal(findBestMatchingJointValueState(states, { ...defaults, gripper: 20 }, defaults)?.id, "gripper/closed");
  assert.equal(findBestMatchingJointValueState(states, { shoulder: 20, elbow: -30, gripper: 0 }, defaults), null);
});

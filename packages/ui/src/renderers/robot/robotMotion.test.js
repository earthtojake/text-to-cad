import assert from "node:assert/strict";
import { test } from "node:test";

import {
  cloneJointValueMap,
  findBestMatchingJointValueState,
  jointValueSubsetClose
} from "./robotMotion.js";

test("robot joint value helpers normalize maps and compare subsets", () => {
  assert.deepEqual(cloneJointValueMap({ " shoulder ": "12.5", empty: Number.NaN, " ": 4 }), {
    shoulder: 12.5,
    empty: 0
  });

  assert.equal(jointValueSubsetClose({ shoulder: 90.0004, slide: 0.12, extra: 10 }, { shoulder: 90, slide: 0.12 }), true);
  assert.equal(jointValueSubsetClose({ shoulder: 91 }, { shoulder: 90 }), false);
  assert.equal(jointValueSubsetClose({ shoulder: 90 }, {}), false);
});

test("best group-state match ignores partial presets when other joints changed", () => {
  const states = [
    { id: "gripper/open", jointValuesByName: { gripper: 0 } },
    { id: "arm/home", jointValuesByName: { shoulder: 45, elbow: -30 } },
    { id: "gripper/closed", jointValuesByName: { gripper: 20 } }
  ];
  const defaults = { shoulder: 45, elbow: -30, gripper: 0 };

  assert.equal(findBestMatchingJointValueState(states, defaults, defaults)?.id, "arm/home");
  assert.equal(findBestMatchingJointValueState(states, { ...defaults, gripper: 12 }, defaults), null);
  assert.equal(findBestMatchingJointValueState(states, { ...defaults, gripper: 20 }, defaults)?.id, "gripper/closed");
  assert.equal(findBestMatchingJointValueState(states, { shoulder: 20, elbow: -30, gripper: 0 }, defaults), null);
});

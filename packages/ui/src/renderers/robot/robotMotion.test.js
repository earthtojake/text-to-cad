import assert from "node:assert/strict";
import { test } from "node:test";

import {
  cloneJointValueMap,
  findBestMatchingJointValueState,
  jointValueSubsetClose,
  srdfHomeGroupStateJointValuesToDisplay,
  srdfGroupStateJointValuesToDisplay
} from "./robotMotion.js";

test("robot joint value helpers normalize maps and SRDF native values", () => {
  assert.deepEqual(cloneJointValueMap({ " shoulder ": "12.5", empty: Number.NaN, " ": 4 }), {
    shoulder: 12.5,
    empty: 0
  });

  const urdfData = {
    joints: [
      { name: "shoulder", type: "revolute" },
      { name: "slide", type: "prismatic" }
    ]
  };
  assert.deepEqual(srdfGroupStateJointValuesToDisplay(urdfData, {
    shoulder: Math.PI / 2,
    slide: 0.12,
    unknown: 99
  }), {
    shoulder: 90,
    slide: 0.12
  });

  assert.deepEqual(srdfHomeGroupStateJointValuesToDisplay({
    ...urdfData,
    srdf: {
      groupStates: [
        { name: "open", jointValuesByName: { slide: 0.1 } },
        { name: "home", jointValuesByName: { shoulder: Math.PI / 4 } },
        { name: "home", jointValuesByName: { slide: 0.2 } }
      ]
    }
  }), {
    shoulder: 45,
    slide: 0.2
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

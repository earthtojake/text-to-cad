import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildUrdfJointAnglesCopyText,
  cloneJointValueMap,
  findBestMatchingJointValueState,
  interpolateTrajectoryJointValues,
  jointValueSubsetClose,
  normalizePoint3,
  roundedUrdfJointValue,
  srdfHomeGroupStateJointValuesToDisplay,
  srdfGroupStateJointValuesToDisplay
} from "./robotMotionControls.js";

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

test("trajectory interpolation keeps fallback values and interpolates only target joints", () => {
  const trajectory = {
    points: [
      { timeFromStartSec: 0, positionsByNameDeg: { shoulder: 0 } },
      { timeFromStartSec: 2, positionsByNameDeg: { shoulder: 20, elbow: 30 } },
      { timeFromStartSec: 4, positionsByNameDeg: { shoulder: 40, elbow: 10 } }
    ]
  };

  assert.deepEqual(interpolateTrajectoryJointValues(null, 1, { wrist: 5 }), { wrist: 5 });
  assert.deepEqual(interpolateTrajectoryJointValues(trajectory, -1, { wrist: 5 }), { wrist: 5, shoulder: 0 });
  assert.deepEqual(interpolateTrajectoryJointValues(trajectory, 1, { wrist: 5, elbow: 2 }), {
    wrist: 5,
    elbow: 30,
    shoulder: 10
  });
  assert.deepEqual(interpolateTrajectoryJointValues(trajectory, 5, { wrist: 5 }), {
    wrist: 5,
    shoulder: 40,
    elbow: 10
  });
});

test("URDF pose and copy helpers preserve formatting and numeric rounding", () => {
  assert.deepEqual(normalizePoint3(["1", 2, 3]), [1, 2, 3]);
  assert.equal(normalizePoint3([1, Number.NaN, 3]), null);
  assert.equal(roundedUrdfJointValue(-0.0001), 0);
  assert.equal(roundedUrdfJointValue(1.23456), 1.235);

  assert.equal(buildUrdfJointAnglesCopyText([
    { name: "shoulder", defaultValueDeg: 10 },
    { name: "elbow", defaultValueDeg: 0 },
    { name: "" }
  ], {
    shoulder: 12.3456
  }), `{
  "shoulder": 12.346,
  "elbow": 0
}`);
});

import assert from "node:assert/strict";
import test from "node:test";

import {
  jointValuesByNameToNative,
  measureUrdfMotionResult,
  normalizeMotionTargetPosition,
  robotOpeningPose,
  srdfGroupStateJointValuesToDisplay,
  srdfHomeGroupStateJointValuesToDisplay,
  validateUrdfMotionTrajectory,
  validateUrdfMotionJointValues
} from "./motion.js";

function translationTransform(x, y, z) {
  return [
    1, 0, 0, x,
    0, 1, 0, y,
    0, 0, 1, z,
    0, 0, 0, 1
  ];
}

const SAMPLE_URDF = {
  rootLink: "base_link",
  rootWorldTransform: translationTransform(0, 0, 0),
  links: [
    { name: "base_link", visuals: [] },
    { name: "tool_link", visuals: [] },
    { name: "mimic_link", visuals: [] }
  ],
  joints: [
    {
      name: "base_to_tool",
      type: "revolute",
      parentLink: "base_link",
      childLink: "tool_link",
      originTransform: translationTransform(0.2, 0, 0),
      axis: [0, 0, 1],
      defaultValueDeg: 0,
      minValueDeg: -45,
      maxValueDeg: 45
    },
    {
      name: "mimic_joint",
      type: "revolute",
      parentLink: "tool_link",
      childLink: "mimic_link",
      originTransform: translationTransform(0, 0, 0),
      axis: [0, 0, 1],
      defaultValueDeg: 0,
      minValueDeg: -45,
      maxValueDeg: 45,
      mimic: { joint: "base_to_tool", multiplier: 1, offset: 0 }
    }
  ]
};

test("normalizeMotionTargetPosition returns a stable finite xyz tuple", () => {
  assert.deepEqual(normalizeMotionTargetPosition(["1", 2, Number.NaN], [0, 0, 3]), [1, 2, 3]);
});

test("validateUrdfMotionJointValues accepts movable non-mimic joints", () => {
  assert.deepEqual(validateUrdfMotionJointValues(SAMPLE_URDF, { base_to_tool: 12.5 }), {
    base_to_tool: 12.5
  });
  assert.deepEqual(validateUrdfMotionJointValues(SAMPLE_URDF, { base_to_tool: Math.PI / 4 }, { native: true }), {
    base_to_tool: 45
  });
  assert.deepEqual(jointValuesByNameToNative(SAMPLE_URDF, { base_to_tool: 90 }), {
    base_to_tool: Math.PI / 2
  });
});

test("validateUrdfMotionJointValues rejects mimic and out-of-limit joints", () => {
  assert.throws(
    () => validateUrdfMotionJointValues(SAMPLE_URDF, { mimic_joint: 5 }),
    /cannot set mimic joint/
  );
  assert.throws(
    () => validateUrdfMotionJointValues(SAMPLE_URDF, { base_to_tool: 90 }),
    /must stay within joint limits/
  );
});

test("measureUrdfMotionResult reports FK residual for the end effector", () => {
  const measurement = measureUrdfMotionResult(
    SAMPLE_URDF,
    { base_to_tool: 0 },
    { link: "tool_link", frame: "base_link" },
    [0.2, 0.001, 0]
  );

  assert.deepEqual(measurement.actualPosition, [0.2, 0, 0]);
  assert.equal(Math.round(measurement.positionError * 1000) / 1000, 0.001);
});

test("validateUrdfMotionTrajectory accepts sorted finite waypoint positions", () => {
  assert.deepEqual(validateUrdfMotionTrajectory(SAMPLE_URDF, {
    jointNames: ["base_to_tool"],
    points: [
      { timeFromStartSec: 0, positionsDeg: [0] },
      { timeFromStartSec: 0.25, positionsDeg: [12.5] }
    ]
  }), {
    jointNames: ["base_to_tool"],
    points: [
      { timeFromStartSec: 0, positions: null, positionsDeg: [0], positionsByName: null, positionsByNameDeg: { base_to_tool: 0 } },
      { timeFromStartSec: 0.25, positions: null, positionsDeg: [12.5], positionsByName: null, positionsByNameDeg: { base_to_tool: 12.5 } }
    ]
  });
});

test("validateUrdfMotionTrajectory accepts native waypoint positions", () => {
  const trajectory = validateUrdfMotionTrajectory(SAMPLE_URDF, {
    jointNames: ["base_to_tool"],
    points: [
      { timeFromStartSec: 0, positions: [0] },
      { timeFromStartSec: 0.25, positions: [Math.PI / 4] }
    ]
  });

  assert.equal(trajectory.points[1].positionsByName.base_to_tool, Math.PI / 4);
  assert.equal(trajectory.points[1].positionsByNameDeg.base_to_tool, 45);
});

test("validateUrdfMotionTrajectory rejects out-of-limit waypoint positions", () => {
  assert.throws(
    () => validateUrdfMotionTrajectory(SAMPLE_URDF, {
      jointNames: ["base_to_tool"],
      points: [
        { timeFromStartSec: 0, positionsDeg: [0] },
        { timeFromStartSec: 0.25, positionsDeg: [90] }
      ]
    }),
    /must stay within joint limits/
  );
});

test("SRDF group states read as poses: radians to degrees, metres kept, unknown joints dropped", () => {
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
});

test("a robot opens at its joints' defaults with the SRDF's home state over them", () => {
  const description = {
    joints: [
      { name: "shoulder", type: "revolute", defaultValueDeg: 10 },
      { name: "elbow", type: "revolute", defaultValueDeg: 0 },
      { name: "follower", type: "revolute", mimic: { joint: "elbow" } },
      { name: "weld", type: "fixed" }
    ]
  };
  assert.deepEqual(robotOpeningPose(description), { shoulder: 10, elbow: 0 }, "no SRDF: every driven joint at its default");
  assert.deepEqual(robotOpeningPose({ ...description, srdf: { groupStates: [
    { name: "raised", jointValuesByName: { shoulder: 1 } },
    { name: "home", jointValuesByName: { elbow: -Math.PI / 4 } }
  ] } }), { shoulder: 10, elbow: -45 }, "home moves only the joints it names; another state is not the opening pose");
});

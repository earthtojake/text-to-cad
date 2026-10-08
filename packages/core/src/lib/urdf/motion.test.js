import assert from "node:assert/strict";
import test from "node:test";

import {
  robotOpeningPose,
  srdfGroupStateJointValuesToDisplay,
  srdfHomeGroupStateJointValuesToDisplay
} from "./motion.js";

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

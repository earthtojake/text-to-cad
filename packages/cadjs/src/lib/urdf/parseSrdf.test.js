import assert from "node:assert/strict";
import test from "node:test";

import { motionFromSrdf, parseSrdf } from "./parseSrdf.js";


class FakeElement {
  constructor(tagName, attributes = {}, children = [], namespaceURI = null) {
    this.nodeType = 1;
    this.tagName = tagName;
    this.localName = String(tagName || "").split(":").pop();
    this.namespaceURI = namespaceURI;
    this._attributes = { ...attributes };
    this.childNodes = children;
  }

  getAttribute(name) {
    return Object.hasOwn(this._attributes, name) ? this._attributes[name] : null;
  }
}

class FakeDocument {
  constructor(documentElement) {
    this.documentElement = documentElement;
  }

  querySelector(selector) {
    return selector === "parsererror" ? null : null;
  }
}

function withFakeDomParser(document, callback) {
  const previous = globalThis.DOMParser;
  globalThis.DOMParser = class FakeDomParser {
    parseFromString() {
      return document;
    }
  };
  try {
    return callback();
  } finally {
    globalThis.DOMParser = previous;
  }
}

function sampleUrdfData() {
  return {
    robotName: "sample_robot",
    rootLink: "base_link",
    links: [
      { name: "base_link" },
      { name: "arm_link" },
      { name: "wrist_link" },
      { name: "tool_link" }
    ],
    joints: [
      { name: "base_to_arm", type: "revolute", parentLink: "base_link", childLink: "arm_link", minValueDeg: -90, maxValueDeg: 90 },
      { name: "arm_to_wrist", type: "revolute", parentLink: "arm_link", childLink: "wrist_link", minValueDeg: -90, maxValueDeg: 90 },
      { name: "wrist_to_tool", type: "fixed", parentLink: "wrist_link", childLink: "tool_link" }
    ]
  };
}

test("parseSrdf reads MoveIt2 semantics directly from SRDF XML", () => {
  const robot = new FakeElement("robot", { name: "sample_robot" }, [
    new FakeElement("group", { name: "manipulator" }, [
      new FakeElement("chain", { base_link: "base_link", tip_link: "wrist_link" })
    ]),
    new FakeElement("group", { name: "gripper_group" }, [
      new FakeElement("link", { name: "tool_link" })
    ]),
    new FakeElement("end_effector", {
      name: "gripper",
      parent_link: "wrist_link",
      group: "gripper_group",
      parent_group: "manipulator"
    }),
    new FakeElement("group_state", { name: "home", group: "manipulator" }, [
      new FakeElement("joint", { name: "base_to_arm", value: "0" }),
      new FakeElement("joint", { name: "arm_to_wrist", value: "0.25" })
    ]),
    new FakeElement("disable_collisions", {
      link1: "base_link",
      link2: "arm_link",
      reason: "Adjacent"
    })
  ]);

  const srdfData = withFakeDomParser(new FakeDocument(robot), () => parseSrdf("<robot />", {
    sourceUrl: "/workspace/sample_robot.srdf",
    urdfData: sampleUrdfData()
  }));

  assert.equal(srdfData.kind, "texttocad-srdf");
  assert.equal(srdfData.srdf, "/workspace/sample_robot.srdf");
  assert.equal(srdfData.planningGroups[0].name, "manipulator");
  assert.equal(srdfData.planningGroups[0].chains[0].tipLink, "wrist_link");
  assert.equal(srdfData.endEffectors[0].link, "tool_link");
  assert.equal(srdfData.groupStates[0].jointValuesByName.arm_to_wrist, 0.25);
  assert.equal(srdfData.groupStates[0].jointValuesByNameRad.arm_to_wrist, 0.25);
  assert.equal(srdfData.disabledCollisionPairs[0].reason, "Adjacent");
  assert.equal(srdfData.disabledCollisionPairs[0].source, "adjacent");
});

test("motionFromSrdf converts direct SRDF data into MoveIt2 CAD Viewer controls", () => {
  const srdfData = {
    planningGroups: [{ name: "manipulator" }],
    endEffectors: [{ name: "gripper" }],
    groupStates: [{ name: "home", group: "manipulator", jointValuesByName: { base_to_arm: 0.5 } }],
    disabledCollisionPairs: []
  };

  const motion = motionFromSrdf(srdfData);

  assert.equal(motion.transport, "moveit2Server");
  assert.equal(motion.srdf, srdfData);
  assert.deepEqual(motion.endEffectors, srdfData.endEffectors);
  assert.deepEqual(motion.groupStates, srdfData.groupStates);
});

test("parseSrdf rejects robot names that do not match the paired URDF", () => {
  const robot = new FakeElement("robot", { name: "other_robot" }, [
    new FakeElement("group", { name: "manipulator" }, [
      new FakeElement("joint", { name: "base_to_arm" })
    ])
  ]);

  assert.throws(
    () => withFakeDomParser(new FakeDocument(robot), () => parseSrdf("<robot />", {
      sourceUrl: "/workspace/sample_robot.srdf",
      urdfData: sampleUrdfData()
    })),
    /must match the paired URDF robot name/
  );
});

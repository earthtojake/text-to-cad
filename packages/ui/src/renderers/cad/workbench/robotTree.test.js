import assert from "node:assert/strict";
import test from "node:test";

import { buildRobotTree, robotJointSummary, robotLinkFacts, robotTreeAncestorIds } from "./robotTree.js";

const joint = (name, type, parentLink, childLink, extra = {}) => ({ name, type, parentLink, childLink, ...extra });
const arm = () => ({
  rootLink: "base_link",
  links: [
    { name: "wrist_link", visuals: [] },
    { name: "base_link", inertial: { mass: 2.5 }, collisions: [{ type: "box", filename: "" }],
      visuals: [{ id: "base_link:v1", filename: "meshes/base.stl", label: "base.stl", meshUrl: "/meshes/base.stl" }] },
    { name: "arm_link", visuals: [] },
    { name: "camera_link", visuals: [] },
  ],
  joints: [
    joint("wrist_roll", "continuous", "arm_link", "wrist_link", { axis: [1, 0, 0] }),
    joint("shoulder", "revolute", "base_link", "arm_link", {
      axis: [0, 0, 1], origin: { xyz: [0, 0, 0.2], rpy: [0, 0, 0] },
      limit: { lower: -1.5, upper: 1.5, effort: 12, velocity: 3 },
    }),
    joint("camera_mount", "fixed", "base_link", "camera_link", { axis: [1, 0, 0] }),
  ],
});
const shape = nodes => nodes.map(node => node.children.length ? [node.label, shape(node.children)] : node.label);
const labels = tree => [...tree.nodesById.values()].map(node => node.label).sort();

test("links nest under their parent link through the connecting joint", () => {
  const tree = buildRobotTree(arm());
  assert.deepEqual(shape(tree.roots), [["base_link", [["arm_link", ["wrist_link"]], "camera_link"]]]);
  const armNode = tree.nodesById.get("link:arm_link");
  assert.equal(armNode.joint.name, "shoulder");
  assert.equal(armNode.detail, "shoulder · revolute");
  assert.deepEqual(armNode.searchAliases, ["shoulder"]);
  assert.equal(tree.roots[0].joint, null);
  assert.equal(tree.roots[0].detail, "");
  assert.deepEqual(robotTreeAncestorIds(tree, "link:wrist_link"), ["link:base_link", "link:arm_link"]);
  assert.deepEqual(robotTreeAncestorIds(tree, "link:base_link"), []);
  assert.equal(robotJointSummary({ name: "slide", type: "prismatic" }), "slide · prismatic");
});

test("named mesh objects are leaves under their link, after its child links", () => {
  const tree = buildRobotTree(arm(), {
    components: [
      { id: "base_link:v1/object/0", name: "housing", linkName: "base_link" },
      { id: "base_link:v1/object/1", name: "lid", linkName: "base_link" },
      { id: "ghost:v1/object/0", name: "lost", linkName: "ghost_link" },
    ],
    parts: [
      { id: "base_link:v1/object/0", linkName: "base_link" }, { id: "base_link:v1/object/1", linkName: "base_link" },
      { id: "arm_link:v1", linkName: "arm_link" },
    ],
  });
  assert.deepEqual(shape(tree.roots), [["base_link", [["arm_link", ["wrist_link"]], "camera_link", "housing", "lid"]]]);
  const base = tree.nodesById.get("link:base_link");
  assert.deepEqual(base.partIds, ["base_link:v1/object/0", "base_link:v1/object/1"]);
  assert.deepEqual(base.componentIds, ["base_link:v1/object/0", "base_link:v1/object/1"]);
  assert.deepEqual(tree.nodesById.get("link:arm_link").partIds, ["arm_link:v1"]);
  assert.deepEqual(tree.nodesById.get("link:wrist_link").partIds, []);
  const lid = tree.nodesById.get("component:base_link:v1/object/1");
  assert.equal(lid.kind, "component");
  assert.deepEqual(robotTreeAncestorIds(tree, lid.id), ["link:base_link"]);
  // A component whose link the description does not have has nowhere to sit.
  assert.equal(tree.nodesById.has("component:ghost:v1/object/0"), false);
});

test("orphans, undeclared links and second parents keep every link exactly once", () => {
  const tree = buildRobotTree({
    rootLink: "b",
    links: [{ name: "a" }, { name: "b" }, { name: "c" }, { name: "island" }],
    joints: [
      joint("b_to_c", "fixed", "b", "c"),
      joint("a_to_c", "fixed", "a", "c"),           // a second parent for c: ignored
      joint("to_nowhere", "fixed", "", "island"),   // no parent: island stays a root
      joint("c_to_tool", "fixed", "c", "tool"),     // tool is never declared
      joint("self", "fixed", "a", "a"),
    ],
  });
  // The declared root leads; the other roots keep the description's order.
  assert.deepEqual(shape(tree.roots), [["b", [["c", ["tool"]]]], "a", "island"]);
  assert.equal(tree.nodesById.get("link:c").joint.name, "b_to_c");
  assert.deepEqual(labels(tree), ["a", "b", "c", "island", "tool"]);
});

test("a cycle neither hangs nor drops its links", () => {
  const tree = buildRobotTree({
    links: [{ name: "root" }, { name: "x" }, { name: "y" }, { name: "z" }],
    joints: [
      joint("x_to_y", "revolute", "x", "y"), joint("y_to_z", "revolute", "y", "z"), joint("z_to_x", "revolute", "z", "x"),
    ],
  });
  assert.deepEqual(shape(tree.roots), ["root", ["x", [["y", ["z"]]]]]);
  // The cut link still says which joint it arrived by.
  assert.equal(tree.nodesById.get("link:x").joint.name, "z_to_x");
  assert.deepEqual(robotTreeAncestorIds(tree, "link:z"), ["link:x", "link:y"]);
  assert.deepEqual(shape(buildRobotTree(null).roots), []);
  assert.deepEqual(shape(buildRobotTree({ links: [{ name: "" }, null] }).roots), []);
});

test("a long serial chain does not depend on the call stack", () => {
  const count = 20000;
  const tree = buildRobotTree({
    links: Array.from({ length: count }, (_, index) => ({ name: `l${index}` })),
    joints: Array.from({ length: count - 1 }, (_, index) => joint(`j${index}`, "fixed", `l${index}`, `l${index + 1}`)),
  });
  assert.equal(tree.roots.length, 1);
  assert.equal(tree.nodesById.size, count);
  assert.equal(robotTreeAncestorIds(tree, `link:l${count - 1}`).length, count - 1);
});

test("link facts report what the description says and nothing it does not", () => {
  const description = { ...arm(), srdf: { endEffectors: [{ name: "gripper", parentLink: "wrist_link", link: "wrist_link" }] } };
  const groupNamesByLink = new Map([["arm_link", ["manipulator"]]]);
  const facts = robotLinkFacts(description, "arm_link", { groupNamesByLink });
  assert.deepEqual(facts.parentJoint, {
    name: "shoulder", type: "revolute", parentLink: "base_link", axis: [0, 0, 1],
    limit: { lower: -1.5, upper: 1.5, effort: 12, velocity: 3 }, origin: { xyz: [0, 0, 0.2], rpy: [0, 0, 0] }, mimic: null,
  });
  assert.deepEqual(facts.childJoints, [{ name: "wrist_roll", type: "continuous", childLink: "wrist_link" }]);
  assert.deepEqual(facts.groups, ["manipulator"]);
  assert.equal(facts.mass, null);
  assert.equal(facts.collisions, null);

  const base = robotLinkFacts(description, "base_link");
  assert.equal(base.isRoot, true);
  assert.equal(base.parentJoint, null);
  assert.equal(base.mass, 2.5);
  // A model that records only the file and the kind says only that; nothing is invented.
  const bare = { name: "", filename: "", scale: null, size: null, radius: null, length: null, origin: null, color: "", materialName: "" };
  assert.deepEqual(base.visuals, [{ ...bare, type: "mesh", filename: "meshes/base.stl" }]);
  assert.deepEqual(base.collisions, [{ ...bare, type: "box", filename: "" }]);
  assert.equal(base.centerOfMass, null);
  assert.equal(base.inertia, null);

  // What the description writes is carried as written: a visual under `description`, a collision as itself.
  const origin = { xyz: [0, 0, 0.1], rpy: [0, 0, 0] };
  const inertia = { ixx: 1, ixy: 0, ixz: 0, iyy: 2, iyz: 0, izz: 3 };
  const said = robotLinkFacts({ joints: [], links: [{ name: "l", inertial: { mass: 1, origin, inertia },
    visuals: [{ color: "#112233", description: { name: "shell", type: "mesh", filename: "m.stl", scale: [2, 2, 2], origin, materialName: "grey" } }],
    collisions: [{ name: "", type: "cylinder", filename: "", radius: 0.05, length: 0.2, origin }] }] }, "l");
  assert.deepEqual(said.visuals, [{ ...bare, name: "shell", type: "mesh", filename: "m.stl", scale: [2, 2, 2], origin, color: "#112233", materialName: "grey" }]);
  assert.deepEqual(said.collisions, [{ ...bare, type: "cylinder", radius: 0.05, length: 0.2, origin }]);
  assert.deepEqual([said.mass, said.centerOfMass, said.inertia], [1, origin, inertia]);
  assert.deepEqual(base.childJoints.map(child => child.name), ["shoulder", "camera_mount"]);

  // A fixed joint's axis is the parser's placeholder, not a fact.
  assert.equal(robotLinkFacts(description, "camera_link").parentJoint.axis, null);
  assert.deepEqual(robotLinkFacts(description, "wrist_link").endEffectors, ["gripper"]);
});

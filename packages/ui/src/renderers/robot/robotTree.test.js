import assert from "node:assert/strict";
import test from "node:test";

import { fixturePayload } from "./__tests__/robotFixtures.js";
import { buildRobotTree, robotJointSummary, robotLinkFacts, robotTreeAncestorIds } from "./robotTree.js";

// Payload-shaped robots (`cadgen.robot_payload`: `links`, `joints` with `parent`/`child`, `root`),
// hand-built where a shape cadgen would refuse (a cycle, a second parent) is the point.
const joint = (name, type, parent, child, extra = {}) => ({ name, type, parent, child, axis: null, origin: null, limit: null, mimic: null, ...extra });
const arm = () => ({
  root: "base_link",
  links: [
    { name: "wrist_link", visuals: [], collisions: [] },
    { name: "base_link", inertial: { mass: 2.5 }, collisions: [{ type: "box", filename: "", size: [0.1, 0.2, 0.3] }],
      visuals: [{ type: "mesh", filename: "meshes/base.stl", path: "/robots/meshes/base.stl" }] },
    { name: "arm_link", visuals: [] },
    { name: "camera_link", visuals: [] },
  ],
  joints: [
    joint("wrist_roll", "continuous", "arm_link", "wrist_link", { axis: [1, 0, 0] }),
    joint("shoulder", "revolute", "base_link", "arm_link", {
      axis: [0, 0, 1], origin: { xyz: [0, 0, 0.2], rpy: [0, 0, 0] },
      limit: { lower: -1.5, upper: 1.5, effort: 12, velocity: 3 },
    }),
    joint("camera_mount", "fixed", "base_link", "camera_link"),
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
      { id: "base_link:v1/object/0", name: "housing", link: "base_link" },
      { id: "base_link:v1/object/1", name: "lid", link: "base_link" },
      { id: "ghost:v1/object/0", name: "lost", link: "ghost_link" },
    ],
    parts: [
      { id: "base_link:v1/object/0", link: "base_link" }, { id: "base_link:v1/object/1", link: "base_link" },
      { id: "arm_link:v1", link: "arm_link" },
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
  // A component whose link the payload does not have has nowhere to sit.
  assert.equal(tree.nodesById.has("component:ghost:v1/object/0"), false);
});

test("orphans, undeclared links and second parents keep every link exactly once", () => {
  const tree = buildRobotTree({
    root: "b",
    links: [{ name: "a" }, { name: "b" }, { name: "c" }, { name: "island" }],
    joints: [
      joint("b_to_c", "fixed", "b", "c"),
      joint("a_to_c", "fixed", "a", "c"),           // a second parent for c: ignored
      joint("to_nowhere", "fixed", "", "island"),   // no parent: island stays a root
      joint("c_to_tool", "fixed", "c", "tool"),     // tool is never declared
      joint("self", "fixed", "a", "a"),
    ],
  });
  // The declared root leads; the other roots keep the payload's order.
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

test("link facts report what the payload says and nothing it does not", () => {
  const robot = { ...arm(), srdf: { endEffectors: [{ name: "gripper", parentLink: "wrist_link", link: "wrist_link" }], groupsByLink: { arm_link: ["manipulator"] } } };
  const facts = robotLinkFacts(robot, "arm_link");
  assert.deepEqual(facts.parentJoint, {
    name: "shoulder", type: "revolute", parentLink: "base_link", axis: [0, 0, 1],
    limit: { lower: -1.5, upper: 1.5, effort: 12, velocity: 3 }, origin: { xyz: [0, 0, 0.2], rpy: [0, 0, 0] }, mimic: null, fourBar: null,
  });
  assert.deepEqual(facts.childJoints, [{ name: "wrist_roll", type: "continuous", childLink: "wrist_link" }]);
  assert.deepEqual(facts.groups, ["manipulator"]);
  assert.equal(facts.mass, null);
  assert.equal(facts.collisions, null);

  const base = robotLinkFacts(robot, "base_link");
  assert.equal(base.isRoot, true);
  assert.equal(base.parentJoint, null);
  assert.equal(base.mass, 2.5);
  // A payload that records only the file and the kind says only that; nothing is invented.
  const bare = { name: "", filename: "", path: "", scale: null, size: null, radius: null, length: null, origin: null, color: "", materialName: "" };
  assert.deepEqual(base.visuals, [{ ...bare, type: "mesh", filename: "meshes/base.stl", path: "/robots/meshes/base.stl" }]);
  assert.deepEqual(base.collisions, [{ ...bare, type: "box", filename: "", size: [0.1, 0.2, 0.3] }]);
  assert.equal(base.centerOfMass, null);
  assert.equal(base.inertia, null);

  // What the description wrote is carried as cadgen read it.
  const origin = { xyz: [0, 0, 0.1], rpy: [0, 0, 0] };
  const inertia = { ixx: 1, ixy: 0, ixz: 0, iyy: 2, iyz: 0, izz: 3 };
  const said = robotLinkFacts({ joints: [], links: [{ name: "l", inertial: { mass: 1, origin, inertia },
    visuals: [{ name: "shell", type: "mesh", filename: "m.stl", path: "/r/m.stl", scale: [2, 2, 2], origin, color: "#112233", materialName: "grey" }],
    collisions: [{ name: "", type: "cylinder", filename: "", radius: 0.05, length: 0.2, origin }] }] }, "l");
  assert.deepEqual(said.visuals, [{ ...bare, name: "shell", type: "mesh", filename: "m.stl", path: "/r/m.stl", scale: [2, 2, 2], origin, color: "#112233", materialName: "grey" }]);
  assert.deepEqual(said.collisions, [{ ...bare, type: "cylinder", radius: 0.05, length: 0.2, origin }]);
  assert.deepEqual([said.mass, said.centerOfMass, said.inertia], [1, origin, inertia]);
  assert.deepEqual(base.childJoints.map(child => child.name), ["shoulder", "camera_mount"]);

  // A fixed joint has no axis: cadgen records none.
  assert.equal(robotLinkFacts(robot, "camera_link").parentJoint.axis, null);
  assert.deepEqual(robotLinkFacts(robot, "wrist_link").endEffectors, ["gripper"]);
});

test("the facts of a resolved robot: cadgen's host path for a mesh file, an SRDF's groups and end effectors on the link", () => {
  const planned = fixturePayload("arm.srdf");
  const carriage = robotLinkFacts(planned, "carriage");
  assert.deepEqual([carriage.groups, carriage.endEffectors, carriage.parentJoint.name, carriage.parentJoint.type], [["arm"], ["tool"], "lift", "prismatic"]);
  assert.deepEqual(carriage.parentJoint.limit, { lower: 0, upper: 0.3, effort: 1, velocity: 1 });
  assert.deepEqual(carriage.childJoints.map(child => `${child.childLink}:${child.name}`), ["finger_left:grip", "finger_right:grip_mirror"]);
  assert.deepEqual(robotLinkFacts(planned, "finger_right").parentJoint.mimic, { joint: "grip", multiplier: -1, offset: 0 });
  const head = robotLinkFacts(planned, "head");
  assert.deepEqual([head.visuals[0].filename, head.visuals[0].path, head.visuals[0].scale], ["meshes/head.glb", "/models/meshes/head.glb", [0.001, 0.001, 0.001]]);
  assert.deepEqual([head.groups, head.endEffectors, head.mass, head.collisions], [[], [], null, []]);
  const base = robotLinkFacts(planned, "base");
  assert.deepEqual([base.isRoot, base.parentJoint.name, base.parentJoint.parentLink, base.visuals[0].type, base.visuals[0].color], [false, "footprint", "base_footprint", "box", "#4d4d59"]);
  // A visual's own name is a fact of the link, as the description wrote it.
  assert.equal(robotLinkFacts(planned, "upper_arm").visuals[0].name, "upper_arm_shell");
  // A four-bar's crank reads back the element: its driver and the linkage's numbers, no mimic formula.
  const crank = robotLinkFacts(fixturePayload("linkage.urdf"), "crank").parentJoint;
  assert.deepEqual([crank.mimic, crank.fourBar], [null, { driver: "output_joint", inputLength: 0.05, groundLength: 0.2, outputLength: 0.08,
    couplerLength: 0.2, inputZero: 1.5253680280265103, outputZero: 1.5707963267948966 }]);
});

test("a root that is only a frame gets no row; a description of nothing but frames keeps them all", () => {
  const body = { visuals: [{ id: "v" }] };
  const robot = {
    links: [{ name: "base_footprint" }, { name: "odom_frame" }, { name: "base_link", ...body }, { name: "arm_link", ...body }],
    joints: [
      joint("odom", "fixed", "odom_frame", "base_footprint"),
      joint("footprint", "fixed", "base_footprint", "base_link"),
      joint("shoulder", "revolute", "base_link", "arm_link"),
    ],
  };
  const tree = buildRobotTree(robot);
  assert.deepEqual(tree.roots.map(root => root.linkName), ["base_link"]);
  assert.deepEqual(tree.elidedLinkNames, ["odom_frame", "base_footprint"]);
  assert.equal(tree.nodesById.has("link:base_footprint"), false);
  assert.deepEqual(robotTreeAncestorIds(tree, "link:arm_link"), ["link:base_link"]);
  // The child still says where it hangs from.
  assert.equal(tree.roots[0].joint.name, "footprint");

  // Not a frame: it carries mass, or its child moves, or it branches.
  const keeps = mutate => { const copy = structuredClone(robot); mutate(copy); return buildRobotTree(copy).roots[0].linkName; };
  assert.equal(keeps(r => { r.links[1].inertial = { mass: 1 }; }), "odom_frame");
  assert.equal(keeps(r => { r.joints[0].type = "continuous"; }), "odom_frame");
  assert.equal(keeps(r => { r.links.push({ name: "imu" }); r.joints.push(joint("imu", "fixed", "odom_frame", "imu")); }), "odom_frame");
  // Geometry-less everywhere (a kinematics-only description): every link is a frame, so none is dropped.
  const bare = { links: robot.links.map(link => ({ name: link.name })), joints: robot.joints };
  assert.deepEqual(buildRobotTree(bare).elidedLinkNames, []);
  assert.equal(buildRobotTree(bare).roots[0].linkName, "odom_frame");
  // The resolved arm: its frame-only footprint is elided and the base leads, the arm's links under it.
  const resolved = buildRobotTree(fixturePayload("arm.urdf"));
  assert.deepEqual(resolved.elidedLinkNames, ["base_footprint"]);
  assert.deepEqual(shape(resolved.roots), [["base", ["upper_arm", ["carriage", ["finger_left", "finger_right"]], "camera", "head"]]]);
});

import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
  clampJointValueDeg, invertRigidTransform, mergeBounds, multiplyTransforms, solveUrdfLinkWorldTransforms, transformBounds, transformPoint
} from "@hardcore/core/lib/urdf/kinematics.js";
import { armOffset, normalize } from "../kit/tools/pose/jointHandleMath.js";
import { parseArmUrdf, parseSwingSdf, robotOf } from "./__tests__/robotFixtures.js";
import { prepareRobotJointHandles, robotJointHandles, robotPosableJoints } from "./jointHandles.js";
import { createRobotScene } from "./robotScene.js";

// The handles are READ from the scene graph. The oracle is how they were SOLVED before there
// was one: the child link's solved frame, less an SDF joint's static child offset.
function solvedHandles(description, parts, values) {
  const frames = solveUrdfLinkWorldTransforms(description, values);
  const centres = new Map();
  for (const part of parts) centres.set(part.linkName, [...(centres.get(part.linkName) || []), transformBounds(part.sourceBounds, part.localTransform)]);
  const direction = (frame, vector) => transformPoint(frame, vector).map((value, index) => value - transformPoint(frame, [0, 0, 0])[index]);
  return robotPosableJoints(description).map((joint) => {
    const child = frames.get(joint.childLink);
    const frame = joint.postMotionTransform ? multiplyTransforms(child, invertRigidTransform(joint.postMotionTransform)) : child;
    const box = centres.has(joint.childLink) ? mergeBounds(centres.get(joint.childLink)) : null;
    const childCentre = box ? box.min.map((value, index) => (value + box.max[index]) / 2) : null;
    const centre = childCentre && joint.postMotionTransform ? transformPoint(joint.postMotionTransform, childCentre) : childCentre;
    const axis = normalize(joint.axis);
    return { id: joint.name, pivot: transformPoint(frame, [0, 0, 0]), axis: normalize(direction(frame, axis)),
      toward: joint.type === "prismatic" ? null : transformPoint(frame, armOffset(axis, centre)), value: clampJointValueDeg(joint, values[joint.name]) };
  });
}
const close = (actual, expected, message) => {
  if (expected === null) { assert.equal(actual, null, message); return; }
  actual.forEach((value, index) => assert.ok(Math.abs(value - expected[index]) < 1e-9, `${message}: ${actual} != ${expected}`));
};

for (const [name, parse, poses] of [
  ["URDF", parseArmUrdf, [{}, { yaw: 90, pitch: -90, lift: 0.25 }, { yaw: -33, pitch: 400, finger: 0.02, wheel: 123 }]],
  ["SDF (a child link offset from its joint)", parseSwingSdf, [{}, { hinge: 40, slide: 0.2 }, { hinge: -500, slide: 9 }]]
]) {
  test(`${name}: handles read from the scene's matrices are the solver's, for any pose`, () => {
    const robot = robotOf(parse());
    const scene = createRobotScene(THREE, robot);
    const prepared = prepareRobotJointHandles(THREE, robot.description, scene);
    for (const values of poses) {
      scene.setJointValues(values);
      const handles = robotJointHandles(THREE, prepared, scene, values, () => {});
      const solved = solvedHandles(robot.description, robot.parts, values);
      assert.deepEqual(handles.map(({ id }) => id), solved.map(({ id }) => id));
      handles.forEach((handle, index) => {
        close(handle.pivot, solved[index].pivot, `${handle.id} pivot`);
        close(handle.axis, solved[index].axis, `${handle.id} axis`);
        close(handle.toward, solved[index].toward, `${handle.id} toward`);
        assert.equal(handle.value, solved[index].value);
      });
    }
  });
}

test("a robot's handles are its drivable joints, in the kit's units, with the limits a slider has", () => {
  const robot = robotOf(parseArmUrdf());
  const scene = createRobotScene(THREE, robot);
  const handles = robotJointHandles(THREE, prepareRobotJointHandles(THREE, robot.description, scene), scene, { lift: 0.25 }, () => {});
  assert.deepEqual(handles.map(({ id, kind, unit }) => `${id}:${kind}:${unit}`),
    ["yaw:continuous:deg", "pitch:revolute:deg", "lift:prismatic:m", "finger:prismatic:m", "wheel:continuous:deg"], "no fixed joint, no mimic follower");
  const lift = handles.find(({ id }) => id === "lift");
  assert.deepEqual([lift.value, lift.min, lift.max, lift.toward], [0.25, 0, 0.5, null], "a slider is a thumb on its track: no arm");
  const yaw = handles.find(({ id }) => id === "yaw");
  assert.deepEqual([yaw.min, yaw.max], [null, null], "a continuous joint has no stops");
});

test("a child centred on its own axis still gets an arm, and the arm turns with the joint", () => {
  const robot = robotOf(parseArmUrdf());
  const scene = createRobotScene(THREE, robot);
  const prepared = prepareRobotJointHandles(THREE, robot.description, scene);
  const armAt = (deg) => {
    scene.setJointValues({ wheel: deg });
    const wheel = robotJointHandles(THREE, prepared, scene, { wheel: deg }, () => {}).find(({ id }) => id === "wheel");
    return new THREE.Vector3(...wheel.toward).sub(new THREE.Vector3(...wheel.pivot));
  };
  const rest = armAt(0), turned = armAt(90);
  assert.ok(Math.abs(rest.length() - 1) < 1e-9 && Math.abs(rest.dot(turned)) < 1e-9, "a unit arm, a quarter turn on");
});

test("a handle writes through the pose store's one write path, and a continuous joint stays one turn", () => {
  const robot = robotOf(parseArmUrdf());
  const scene = createRobotScene(THREE, robot);
  const writes = [];
  const handles = robotJointHandles(THREE, prepareRobotJointHandles(THREE, robot.description, scene), scene, {}, (joint, value) => writes.push([joint.name, value]));
  handles.find(({ id }) => id === "pitch").onChange(400);
  handles.find(({ id }) => id === "yaw").onChange(725);
  handles.find(({ id }) => id === "yaw").onChange(-190);
  // Unclamped: the store owns the limits.
  assert.deepEqual(writes, [["pitch", 400], ["yaw", 5], ["yaw", 170]]);
});

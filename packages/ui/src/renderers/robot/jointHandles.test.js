import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { jointDeltas } from "@text-to-cad/core/common/articulation.js";
import { createRobotScene } from "@text-to-cad/core/lib/urdf/robotScene.js";
import { armOffset, normalize, subtract } from "../kit/tools/pose/jointHandleMath.js";
import { fixturePayload, robotOf } from "./__tests__/robotFixtures.js";
import { prepareRobotJointHandles, robotJointHandles, robotPosableHandles } from "./jointHandles.js";

// The handles are READ from the scene's joint matrices. The oracle is the player: each joint's
// world delta (`jointDeltas`) over its rest origin, axis and arm.
function solvedHandles(robot, scene, values) {
  const deltas = jointDeltas(THREE, robot.articulation, values);
  return robotPosableHandles(robot).map((handle) => {
    const delta = deltas.get(handle.joint);
    const origin = handle.node.origin;
    const axis = normalize(handle.node.axis);
    const centre = (robot.articulation.carries[handle.joint] || []).map(link => scene.linkCentre(link)).find(Boolean) || null;
    const arm = handle.kind === "prismatic" ? null : armOffset(axis, centre ? subtract(centre, origin) : null);
    const at = point => new THREE.Vector3(...point).applyMatrix4(delta).toArray();
    return { id: handle.id, pivot: at(origin), axis: normalize(new THREE.Vector3(...axis).transformDirection(delta).toArray()),
      toward: arm ? at([origin[0] + arm[0], origin[1] + arm[1], origin[2] + arm[2]]) : null };
  });
}
const close = (actual, expected, message) => {
  if (expected === null) { assert.equal(actual, null, message); return; }
  actual.forEach((value, index) => assert.ok(Math.abs(value - expected[index]) < 1e-9, `${message}: ${actual} != ${expected}`));
};

for (const [name, poses] of [
  ["arm.urdf", [{}, { shoulder: 90, lift: 0.25 }, { shoulder: -33, grip: 0.02, nod: 40 }]],
  ["swing.sdf (a child link offset from its joint)", [{}, { hinge: 40 }, { hinge: -60 }]]
]) {
  test(`${name}: handles read from the scene's matrices are the player's, for any pose`, () => {
    const robot = fixturePayload(name.split(" ")[0]);
    const scene = createRobotScene(THREE, robotOf(robot));
    const prepared = prepareRobotJointHandles(THREE, robot, scene);
    for (const values of poses) {
      scene.setControlValues(values);
      const handles = robotJointHandles(THREE, prepared, scene, values, () => {});
      const solved = solvedHandles(robot, scene, { ...robot.articulation.opening, ...values });
      assert.deepEqual(handles.map(({ id }) => id), solved.map(({ id }) => id));
      handles.forEach((handle, index) => {
        close(handle.pivot, solved[index].pivot, `${handle.id} pivot`);
        close(handle.axis, solved[index].axis, `${handle.id} axis`);
        close(handle.toward, solved[index].toward, `${handle.id} toward`);
      });
    }
    scene.dispose();
  });
}

test("a robot's handles are its articulation's: one per moving row, a follower's included, in the kit's units, with the limits a slider has", () => {
  const robot = fixturePayload("arm.urdf");
  const scene = createRobotScene(THREE, robotOf(robot));
  const handles = robotJointHandles(THREE, prepareRobotJointHandles(THREE, robot, scene), scene, { lift: 0.25 }, () => {});
  assert.deepEqual(handles.map(({ id, kind, unit }) => `${id}:${kind}:${unit}`),
    ["shoulder:revolute:deg", "lift:prismatic:m", "grip:prismatic:m", "grip_mirror:prismatic:m", "nod:revolute:deg"], "no fixed joint; a mimic follower is a row of its own");
  const lift = handles.find(({ id }) => id === "lift");
  assert.deepEqual([lift.value, lift.min, lift.max, lift.toward], [0.25, 0, 0.3, null], "a slider is a thumb on its track: no arm");
  const mirror = handles.find(({ id }) => id === "grip_mirror");
  assert.deepEqual([mirror.min, mirror.max, mirror.value + 0], [-0.04, 0, 0], "the follower's own declared range, and its row at the pose");
  scene.dispose();
});

test("a four-bar's crank has no handle and no control: its driver's knob moves it, through the curve cadgen sampled", () => {
  const robot = fixturePayload("linkage.urdf");
  const scene = createRobotScene(THREE, robotOf(robot));
  const handles = robotJointHandles(THREE, prepareRobotJointHandles(THREE, robot, scene), scene, {}, () => {});
  assert.deepEqual(handles.map(({ id, kind }) => `${id}:${kind}`), ["output_joint:revolute"]);
  assert.deepEqual(robot.articulation.controls.map(({ id }) => id), ["output_joint"]);
  // At a key of the curve the crank is exactly where cadgen's closed form put it.
  const { curve } = robot.articulation.joints.find(({ id }) => id === "input_joint").turn;
  const key = Math.floor(curve.input.length / 3);
  scene.setControlValues({ output_joint: curve.input[key] });
  assert.equal(scene.jointRow("input_joint").turn, curve.output[key]);
  scene.dispose();
});

test("a continuous joint has no stops and its drag winds one turn; a child centred on its own axis still gets an arm that turns with the joint", () => {
  const robot = fixturePayload("arm.urdf");
  // A continuous joint of the arm's own shape: the nod, unbounded.
  const free = structuredClone(robot);
  const nod = free.articulation.controls.find(({ id }) => id === "nod");
  nod.min = nod.max = null;
  const handle = free.articulation.handles.find(({ id }) => id === "nod");
  handle.min = handle.max = null;
  const scene = createRobotScene(THREE, robotOf(free));
  const prepared = prepareRobotJointHandles(THREE, free, scene);
  const writes = [];
  const handles = robotJointHandles(THREE, prepared, scene, {}, (id, value) => writes.push([id, value]));
  const knob = handles.find(({ id }) => id === "nod");
  assert.deepEqual([knob.kind, knob.min, knob.max], ["continuous", null, null]);
  knob.onChange(725);
  knob.onChange(-190);
  handles.find(({ id }) => id === "shoulder").onChange(400);
  // A follower's knob writes its LEADER, through the row's weight; a limited knob is clamped to the control's limits.
  handles.find(({ id }) => id === "grip_mirror").onChange(-0.03);
  assert.deepEqual(writes.map(([id, value]) => [id, Math.round(value * 1e6) / 1e6]), [["nod", 5], ["nod", 170], ["shoulder", 90.000210], ["grip", 0.03]]);
  const armAt = (deg) => {
    scene.setControlValues({ nod: deg });
    const now = robotJointHandles(THREE, prepared, scene, { nod: deg }, () => {}).find(({ id }) => id === "nod");
    return new THREE.Vector3(...now.toward).sub(new THREE.Vector3(...now.pivot));
  };
  const rest = armAt(0), turned = armAt(90);
  assert.ok(Math.abs(rest.length() - 1) < 1e-9 && Math.abs(rest.dot(turned)) < 1e-9, "a unit arm, a quarter turn on");
  scene.dispose();
});

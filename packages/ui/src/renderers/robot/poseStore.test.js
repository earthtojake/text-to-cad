import assert from "node:assert/strict";
import test from "node:test";

import { fixturePayload } from "./__tests__/robotFixtures.js";
import { createPoseStore, poseLogic, robotGroupStates } from "./poseStore.js";

const DEG = 180 / Math.PI;
const arm = () => fixturePayload("arm.urdf");
const planned = () => fixturePayload("arm.srdf");

test("a robot opens at its articulation's opening: every control at rest, an SRDF's 'home' state laid over them", () => {
  const plain = createPoseStore(arm());
  assert.deepEqual(plain.getSnapshot().values, { shoulder: 0, lift: 0, grip: 0, nod: 0 });
  assert.deepEqual(plain.groupStates, []);
  assert.deepEqual(plain.controls.map(({ id }) => id), ["shoulder", "lift", "grip", "nod"], "no fixed joint, no mimic follower");

  const store = createPoseStore(planned());
  assert.ok(Math.abs(store.getSnapshot().values.shoulder - (-0.5 * DEG)) < 1e-9, "radians in the SRDF, degrees in the control: cadgen converted");
  assert.equal(store.getSnapshot().values.lift, 0.1);
  assert.deepEqual(robotGroupStates(planned()).map(({ id, label, values }) => [id, label, Object.keys(values)]),
    [["arm/home", "home", ["shoulder", "lift"]], ["arm/raised", "raised", ["shoulder", "lift"]]]);
  assert.equal(store.getSnapshot().groupStateId, "arm/home", "the state the opening pose matches");
});

test("one write path: clamped to the control's limits, deaf to a change under the epsilon, heard at once", () => {
  const store = createPoseStore(arm());
  const heard = [];
  const stop = store.subscribe(() => heard.push(store.getSnapshot().values.shoulder));
  assert.equal(store.write("shoulder", 400), true);
  assert.ok(Math.abs(store.getSnapshot().values.shoulder - 1.5708 * DEG) < 1e-3, "clamped to the control's limit");
  assert.equal(store.write("shoulder", 900), false, "already there");
  assert.equal(store.write("shoulder", store.getSnapshot().values.shoulder - 0.0005), false, "under the epsilon");
  assert.equal(store.write("camera_mount", 5), false, "not a control: a fixed joint");
  assert.equal(store.write("grip_mirror", 0.01), false, "not a control: a follower is posed through its leader");
  assert.equal(store.write("grip", 0.02), true);
  assert.equal(heard.length, 2);
  stop();
  store.write("shoulder", 0);
  assert.equal(heard.length, 2);
  const before = store.getSnapshot();
  assert.equal(store.getSnapshot(), before, "a snapshot is stable until the next write");
});

test("a named pose merges over the pose as it is and is tracked until a control is moved by hand", () => {
  const store = createPoseStore(planned());
  const state = id => store.groupStates.find(candidate => candidate.id === id);
  store.write("grip", 0.03);
  assert.equal(store.getSnapshot().groupStateId, "", "a control off its opening value: the pose matches no state");
  store.selectGroupState(state("arm/raised"));
  assert.deepEqual([store.getSnapshot().values.lift, store.getSnapshot().values.grip], [0.2, 0.03], "merged, not replaced");
  assert.equal(store.getSnapshot().groupStateId, "arm/raised", "tracked, though the grip keeps it from matching");
  store.write("lift", 0.15);
  assert.equal(store.getSnapshot().groupStateId, "", "moving a control by hand releases it");
  store.reset();
  assert.deepEqual(store.getSnapshot().values, store.defaults);
  assert.equal(store.getSnapshot().groupStateId, "arm/home");
});

test("values carried onto a payload keep its known controls, clamped to its limits", () => {
  const store = createPoseStore(arm(), { shoulder: 500, lift: 0.2, gone: 12, camera_mount: 3, grip_mirror: 1 });
  const { values } = store.getSnapshot();
  assert.ok(Math.abs(values.shoulder - 1.5708 * DEG) < 1e-3);
  assert.deepEqual([values.lift, values.grip, "gone" in values, "camera_mount" in values, "grip_mirror" in values], [0.2, 0, false, false, false]);
});

test("what poses a robot is its controls and its named poses: a revision with the same keeps the pose, and the named pose it was chosen as", () => {
  const logic = poseLogic(arm());
  assert.equal(poseLogic(arm()), logic, "the same payload, read again");
  const longer = arm();
  longer.links[2].visuals[0].size = [1, 0.08, 0.08];
  assert.equal(poseLogic(longer), logic, "a longer arm is posed the same way");
  const wider = arm();
  wider.articulation.controls[1].max = 0.6;
  assert.notEqual(poseLogic(wider), logic, "a control's range is part of it");
  assert.notEqual(poseLogic(planned()), logic, "and so are the named poses, and the opening");
  assert.equal(createPoseStore(planned()).logic, poseLogic(planned()));
  // The named pose the values were chosen as comes with them, matching or not.
  const carried = createPoseStore(planned(), { lift: 0.2, grip: 0.03 }, "arm/raised");
  assert.equal(carried.getSnapshot().groupStateId, "arm/raised");
  assert.equal(createPoseStore(planned(), { lift: 0.2, grip: 0.03 }).getSnapshot().groupStateId, "", "where none is carried, the values match none");
});

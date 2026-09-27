import assert from "node:assert/strict";
import test from "node:test";

import { parseArmSrdf, parseArmUrdf } from "./__tests__/robotFixtures.js";
import { createPoseStore, movableJoints } from "./poseStore.js";

const joint = (store, name) => store.joints.find(candidate => candidate.name === name);

test("a robot opens at its declared defaults; an SRDF's 'home' state is laid over them", () => {
  const plain = createPoseStore(parseArmUrdf());
  assert.deepEqual(plain.getSnapshot().values, { yaw: 0, pitch: 0, lift: 0, finger: 0, wheel: 0 });
  assert.deepEqual(plain.groupStates, []);
  assert.deepEqual(movableJoints(parseArmUrdf()).map(({ name }) => name), ["yaw", "pitch", "lift", "finger", "wheel"], "no fixed joint, no mimic follower");

  const planned = createPoseStore(parseArmSrdf());
  const home = (-0.5 * 180) / Math.PI;
  assert.equal(planned.getSnapshot().values.pitch, home, "radians in the SRDF, degrees in the pose");
  assert.deepEqual(planned.groupStates.map(({ id, label }) => [id, label]), [["reach/home", "home"], ["reach/raised", "raised"], ["grip/open", "open"]]);
  assert.equal(planned.getSnapshot().groupStateId, "reach/home", "the state the opening pose matches");
});

test("one write path: clamped, deaf to a change under the epsilon, heard at once", () => {
  const store = createPoseStore(parseArmUrdf());
  const heard = [];
  const stop = store.subscribe(() => heard.push(store.getSnapshot().values.pitch));
  assert.equal(store.write(joint(store, "pitch"), 400), true);
  assert.ok(Math.abs(store.getSnapshot().values.pitch - 90) < 1e-3, "clamped to the joint's limit");
  assert.equal(store.write(joint(store, "pitch"), 900), false, "already there");
  assert.equal(store.write(joint(store, "pitch"), store.getSnapshot().values.pitch - 0.0005), false, "under the epsilon");
  assert.equal(store.write({ name: "camera_mount" }, 5), false, "not a joint a person drives");
  assert.equal(store.write(joint(store, "yaw"), 725), true);
  assert.equal(store.getSnapshot().values.yaw, 725, "a continuous joint is not clamped here: its knob stores one turn");
  assert.equal(heard.length, 2);
  stop();
  store.write(joint(store, "pitch"), 0);
  assert.equal(heard.length, 2);
  const before = store.getSnapshot();
  assert.equal(store.getSnapshot(), before, "a snapshot is stable until the next write");
});

test("a named pose merges over the pose as it is and is tracked until a joint is moved by hand", () => {
  const store = createPoseStore(parseArmSrdf());
  const state = id => store.groupStates.find(candidate => candidate.id === id);
  store.write(joint(store, "wheel"), 40);
  assert.equal(store.getSnapshot().groupStateId, "", "a joint off its default: the pose matches no state");
  store.selectGroupState(state("grip/open"));
  assert.deepEqual([store.getSnapshot().values.finger, store.getSnapshot().values.wheel], [0.04, 40], "merged, not replaced");
  assert.equal(store.getSnapshot().groupStateId, "grip/open", "tracked, though the wheel keeps it from matching");
  store.write(joint(store, "lift"), 0.1);
  assert.equal(store.getSnapshot().groupStateId, "", "moving a joint by hand releases it");
  store.reset();
  assert.deepEqual(store.getSnapshot().values, store.defaults);
  assert.equal(store.getSnapshot().groupStateId, "reach/home");
});

test("values carried onto a description keep its known joints, clamped to its limits", () => {
  const store = createPoseStore(parseArmUrdf(), { pitch: 500, lift: 0.2, gone: 12, camera_mount: 3, finger_mirror: 1 });
  const { values } = store.getSnapshot();
  assert.ok(Math.abs(values.pitch - 90) < 1e-3);
  assert.deepEqual([values.lift, values.yaw, "gone" in values, "camera_mount" in values, "finger_mirror" in values], [0.2, 0, false, false, false]);
});

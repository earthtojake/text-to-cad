import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_POSE_TRANSITION,
  POSE_TRANSITION_BASE_MS,
  animatePoseValues,
  normalizePoseTransition,
  poseTransitionDurationMs,
  readPoseTransition,
  writePoseTransition
} from "./poseTransition.js";

function fakeStorage(initial = {}) {
  const store = { ...initial };
  return {
    getItem: (key) => (Object.hasOwn(store, key) ? store[key] : null),
    setItem: (key, value) => { store[key] = String(value); },
    read: () => store
  };
}

test("animation off means the values are written now, not written fast", () => {
  assert.equal(poseTransitionDurationMs({ animate: false, speed: 1 }), 0);
  assert.equal(poseTransitionDurationMs({ animate: false, speed: 4 }), 0);
});

test("speed divides the base duration", () => {
  assert.equal(poseTransitionDurationMs({ animate: true, speed: 1 }), POSE_TRANSITION_BASE_MS);
  assert.equal(poseTransitionDurationMs({ animate: true, speed: 2 }), Math.round(POSE_TRANSITION_BASE_MS / 2));
  assert.equal(poseTransitionDurationMs({ animate: true, speed: 0.5 }), POSE_TRANSITION_BASE_MS * 2);
});

test("a speed that is not one of the offered ones falls back to 1x", () => {
  // A stored 0.001 would read as "animation is broken" rather than "slow".
  assert.equal(normalizePoseTransition({ animate: true, speed: 0.001 }).speed, 1);
  assert.equal(normalizePoseTransition({ animate: true, speed: -2 }).speed, 1);
  assert.equal(normalizePoseTransition({ animate: true, speed: "2" }).speed, 2);
});

test("the preference survives a round trip, and a blocked store still animates", () => {
  const storage = fakeStorage();
  writePoseTransition(storage, { animate: false, speed: 2 });
  assert.deepEqual(readPoseTransition(storage), { animate: false, speed: 2 });

  const broken = { getItem: () => "{ not json", setItem: () => { throw new Error("blocked"); } };
  assert.deepEqual(readPoseTransition(broken), { ...DEFAULT_POSE_TRANSITION });
  writePoseTransition(broken, { animate: true, speed: 1 });
});

test("a zero duration writes the target once and never asks for a frame", () => {
  const frames = [];
  const originalRaf = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = () => assert.fail("a disabled transition must not animate");
  try {
    animatePoseValues({
      start: { a: 0 },
      target: { a: 10 },
      durationMs: 0,
      onFrame: (values) => frames.push(values)
    });
  } finally {
    globalThis.requestAnimationFrame = originalRaf;
  }
  assert.deepEqual(frames, [{ a: 10 }]);
});

test("a transition walks the numbers and lands exactly on the target", () => {
  const callbacks = [];
  const originalRaf = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = (callback) => { callbacks.push(callback); return callbacks.length; };
  const frames = [];
  try {
    animatePoseValues({
      start: { a: 0, flag: false },
      target: { a: 100, flag: true },
      durationMs: 100,
      onFrame: (values) => frames.push({ ...values })
    });
    callbacks.shift()(1000);
    callbacks.shift()(1050);
    callbacks.shift()(1100);
  } finally {
    globalThis.requestAnimationFrame = originalRaf;
  }
  assert.equal(frames.length, 3);
  assert.equal(frames[0].a, 0, "the first frame is the start, not a jump into the middle");
  assert.ok(frames[1].a > 0 && frames[1].a < 100, `halfway should be between: ${frames[1].a}`);
  assert.equal(frames[2].a, 100, "the last frame is exactly the target");
  // What cannot be walked is carried on every frame, never interpolated.
  assert.deepEqual(frames.map((frame) => frame.flag), [true, true, true]);
});

test("cancelling stops the walk without writing the target", () => {
  const callbacks = [];
  const originalRaf = globalThis.requestAnimationFrame;
  globalThis.requestAnimationFrame = (callback) => { callbacks.push(callback); return callbacks.length; };
  const frames = [];
  try {
    const cancel = animatePoseValues({
      start: { a: 0 },
      target: { a: 100 },
      durationMs: 100,
      onFrame: (values) => frames.push({ ...values })
    });
    callbacks.shift()(1000);
    cancel();
    callbacks.shift()(1100);
  } finally {
    globalThis.requestAnimationFrame = originalRaf;
  }
  assert.deepEqual(frames.map((frame) => frame.a), [0], "a cancelled transition writes nothing more");
});

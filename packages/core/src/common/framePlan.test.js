// The frame schedule a `{fps, seconds, start}` request implies over one clip,
// tested at the arithmetic two callers depend on: getting the last frame's time
// wrong is a stutter on every loop of a video and a jump on every loop of an
// exported GLB, and nothing else would catch either.

import assert from "node:assert/strict";
import test from "node:test";

import { normalizeAnimationClips } from "./animationRuntime.js";
import {
  FRAME_PLAN_MAX_FRAMES,
  framePlanElapsedSec,
  resolveFramePlan
} from "./framePlan.js";

const SLIDE_CLIPS = normalizeAnimationClips({
  slide: {
    duration: 4,
    update(t, m) {
      m.get("Left").translate([t, 0, 0]);
    }
  },
  // The same choreography that STOPS at its end. The evaluator clamps this one
  // rather than wrapping it, so a span running past 4s buys identical frames.
  once: {
    duration: 4,
    loop: false,
    update(t, m) {
      m.get("Left").translate([t, 0, 0]);
    }
  }
});

test("a span defaults to the clip's declared duration", () => {
  const plan = resolveFramePlan({ fps: 30 }, SLIDE_CLIPS.slide);
  assert.deepEqual(plan, { fps: 30, seconds: 4, start: 0, frameCount: 120, warnings: [] });
  // The last frame sits one interval BEFORE start + seconds: at 4s the clip is
  // back where it started, and rendering both ends stutters on every repeat.
  assert.equal(framePlanElapsedSec(plan, 0), 0);
  assert.equal(framePlanElapsedSec(plan, plan.frameCount - 1), 119 / 30);
});

test("a default span from a non-zero start is what is LEFT of the clip", () => {
  // A looping clip wraps, so a whole cycle from anywhere is a clean cycle.
  assert.equal(resolveFramePlan({ fps: 30, start: 1.5 }, SLIDE_CLIPS.slide).seconds, 4);
  // A clip that stops has only its remainder: the full duration here would put
  // 45 of 120 frames past the end, where the evaluator clamps and every one of
  // them is the same final pose.
  const plan = resolveFramePlan({ fps: 30, start: 1.5 }, SLIDE_CLIPS.once);
  assert.equal(plan.seconds, 2.5);
  assert.equal(plan.frameCount, 75);
  assert.ok(framePlanElapsedSec(plan, plan.frameCount - 1) < 4);
});

test("an explicit span and start are the caller's, and fps is the count's other half", () => {
  const plan = resolveFramePlan({ fps: 12, seconds: 1.5, start: 2 }, SLIDE_CLIPS.slide);
  assert.equal(plan.frameCount, 18);
  assert.equal(framePlanElapsedSec(plan, 0), 2);
  assert.equal(framePlanElapsedSec(plan, 17), 2 + (17 / 12));
});

test("an unusable request is refused rather than scheduled", () => {
  assert.throws(() => resolveFramePlan({ fps: 0 }, SLIDE_CLIPS.slide), /fps must be/);
  assert.throws(() => resolveFramePlan({ fps: 240 }, SLIDE_CLIPS.slide), /fps must be/);
  assert.throws(() => resolveFramePlan({ fps: 30, seconds: 0 }, SLIDE_CLIPS.slide), /seconds must be/);
  assert.throws(() => resolveFramePlan({ fps: 30, start: -1 }, SLIDE_CLIPS.slide), /start must be/);
});

test("a span the clip cannot answer is refused or warned about, never silently wrong", () => {
  // Past the end there is nothing to render: every frame would be the last one
  // (clamped) or a wrapped span nobody asked for (looping).
  assert.throws(
    () => resolveFramePlan({ fps: 30, start: 30 }, SLIDE_CLIPS.slide),
    /past the end of a 4s clip/
  );
  assert.throws(
    () => resolveFramePlan({ fps: 30, start: 4 }, SLIDE_CLIPS.once),
    /past the end of a 4s clip/
  );
  // An explicit overrun of a clip that stops is the caller's to make, and the
  // frozen tail it buys is said out loud.
  const { warnings } = resolveFramePlan({ fps: 30, seconds: 6 }, SLIDE_CLIPS.once);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /same final pose/);
  // Overrunning a LOOPING clip is a second lap, which is the honest answer.
  assert.deepEqual(resolveFramePlan({ fps: 30, seconds: 8 }, SLIDE_CLIPS.slide).warnings, []);
});

test("the frame count is bounded, not just the fps", () => {
  // The fps ceiling bounds one multiplicand; a caller writing milliseconds for
  // seconds reaches a six-figure schedule through the other one, and every
  // frame is a full-size PNG on disk before ffmpeg runs.
  assert.throws(
    () => resolveFramePlan({ fps: 30, seconds: 3000 }, SLIDE_CLIPS.slide),
    /90000 frames, past the 7200-frame ceiling/
  );
  assert.equal(
    resolveFramePlan({ fps: 30, seconds: FRAME_PLAN_MAX_FRAMES / 30 }, SLIDE_CLIPS.slide).frameCount,
    FRAME_PLAN_MAX_FRAMES
  );
});

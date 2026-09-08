// The video sequence entry, tested at its two load-bearing claims.
//
// The first is arithmetic: a `video` request plus a clip is a frame schedule,
// and getting the last frame's time wrong is a stutter on every loop that
// nothing else would catch.
//
// The second is why a video is affordable at all. A still pays for loadSource
// and buildModel and throws both away; a sequence pays once and then moves only
// the clock. That is a claim about cadScene's `update` — that a merged
// `callbacks.animation` re-runs the effects pass over the records already built
// instead of rebuilding them — so it is tested against a REAL model, by record
// identity, rather than against a mock that would agree with anything.

import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import { buildModel } from "./cadScene.js";
import { modelOptionsForRenderJob, renderJobContext } from "./renderMeshScene.js";
import { normalizeAnimationClips } from "./animationRuntime.js";
import { resolveAnimationFrame } from "./animationClock.js";
import {
  VIDEO_MAX_FRAMES,
  poseSequenceFrame,
  resolveVideoPlan,
  sequenceFrameBounds,
  videoFrameElapsedSec
} from "./headlessRenderEntry.js";

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

function twoPartMeshData() {
  return {
    vertices: new Float32Array([
      0, 0, 0,
      1, 0, 0,
      0, 1, 0,
      2, 0, 0,
      3, 0, 0,
      2, 1, 0
    ]),
    indices: new Uint32Array([0, 1, 2, 3, 4, 5]),
    normals: new Float32Array([
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1
    ]),
    bounds: { min: [0, 0, 0], max: [3, 1, 0] },
    parts: [
      {
        id: "left",
        name: "Left",
        vertexOffset: 0,
        vertexCount: 3,
        triangleOffset: 0,
        triangleCount: 1,
        bounds: { min: [0, 0, 0], max: [1, 1, 0] }
      },
      {
        id: "right",
        name: "Right",
        vertexOffset: 3,
        vertexCount: 3,
        triangleOffset: 1,
        triangleCount: 1,
        bounds: { min: [2, 0, 0], max: [3, 1, 0] }
      }
    ]
  };
}

function buildSequenceModel(stepAnimation) {
  const meshData = twoPartMeshData();
  const job = { mode: "view", kind: "step", outputs: [{ path: "clip.mp4" }], stepAnimation };
  const context = renderJobContext(meshData, job);
  return buildModel(THREE, { kind: "step", meshData }, modelOptionsForRenderJob(context, job));
}

test("a video's span defaults to the clip's declared duration", () => {
  const plan = resolveVideoPlan({ fps: 30 }, SLIDE_CLIPS.slide);
  assert.deepEqual(plan, { fps: 30, seconds: 4, start: 0, frameCount: 120, warnings: [] });
  // The last frame sits one interval BEFORE start + seconds: at 4s the clip is
  // back where it started, and rendering both ends stutters on every repeat.
  assert.equal(videoFrameElapsedSec(plan, 0), 0);
  assert.equal(videoFrameElapsedSec(plan, plan.frameCount - 1), 119 / 30);
});

test("a default span from a non-zero start is what is LEFT of the clip", () => {
  // A looping clip wraps, so a whole cycle from anywhere is a clean cycle.
  assert.equal(resolveVideoPlan({ fps: 30, start: 1.5 }, SLIDE_CLIPS.slide).seconds, 4);
  // A clip that stops has only its remainder: the full duration here would put
  // 45 of 120 frames past the end, where the evaluator clamps and every one of
  // them is the same final pose.
  const plan = resolveVideoPlan({ fps: 30, start: 1.5 }, SLIDE_CLIPS.once);
  assert.equal(plan.seconds, 2.5);
  assert.equal(plan.frameCount, 75);
  assert.ok(videoFrameElapsedSec(plan, plan.frameCount - 1) < 4);
});

test("a video's span and start are its own, and fps is the frame count's other half", () => {
  const plan = resolveVideoPlan({ fps: 12, seconds: 1.5, start: 2 }, SLIDE_CLIPS.slide);
  assert.equal(plan.frameCount, 18);
  assert.equal(videoFrameElapsedSec(plan, 0), 2);
  assert.equal(videoFrameElapsedSec(plan, 17), 2 + (17 / 12));
});

test("an unusable video request is refused rather than scheduled", () => {
  assert.throws(() => resolveVideoPlan({ fps: 0 }, SLIDE_CLIPS.slide), /fps must be/);
  assert.throws(() => resolveVideoPlan({ fps: 240 }, SLIDE_CLIPS.slide), /fps must be/);
  assert.throws(() => resolveVideoPlan({ fps: 30, seconds: 0 }, SLIDE_CLIPS.slide), /seconds must be/);
  assert.throws(() => resolveVideoPlan({ fps: 30, start: -1 }, SLIDE_CLIPS.slide), /start must be/);
});

test("a span the clip cannot answer is refused or warned about, never silently wrong", () => {
  // Past the end there is nothing to render: every frame would be the last one
  // (clamped) or a wrapped span nobody asked for (looping).
  assert.throws(
    () => resolveVideoPlan({ fps: 30, start: 30 }, SLIDE_CLIPS.slide),
    /past the end of a 4s clip/
  );
  assert.throws(
    () => resolveVideoPlan({ fps: 30, start: 4 }, SLIDE_CLIPS.once),
    /past the end of a 4s clip/
  );
  // An explicit overrun of a clip that stops is the caller's to make, and the
  // frozen tail it buys is said out loud.
  const { warnings } = resolveVideoPlan({ fps: 30, seconds: 6 }, SLIDE_CLIPS.once);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /same final pose/);
  // Overrunning a LOOPING clip is a second lap, which is the honest answer.
  assert.deepEqual(resolveVideoPlan({ fps: 30, seconds: 8 }, SLIDE_CLIPS.slide).warnings, []);
});

test("the frame count is bounded, not just the fps", () => {
  // The fps ceiling bounds one multiplicand; a caller writing milliseconds for
  // seconds reaches a six-figure schedule through the other one, and every
  // frame is a full-size PNG on disk before ffmpeg runs.
  assert.throws(
    () => resolveVideoPlan({ fps: 30, seconds: 3000 }, SLIDE_CLIPS.slide),
    /90000 frames, past the 7200-frame ceiling/
  );
  assert.equal(
    resolveVideoPlan({ fps: 30, seconds: VIDEO_MAX_FRAMES / 30 }, SLIDE_CLIPS.slide).frameCount,
    VIDEO_MAX_FRAMES
  );
});

test("a sequence frame re-poses the records the preparation built; nothing rebuilds", () => {
  const stepAnimation = resolveAnimationFrame(SLIDE_CLIPS, { clip: "slide", time: 0 });
  const model = buildSequenceModel(stepAnimation);
  try {
    const before = model.displayRecords.slice();
    const left = before.find((record) => record.partId === "left");
    const geometry = left.mesh.geometry;
    assert.deepEqual(
      new THREE.Vector3(0, 0, 0).applyMatrix4(left.effectMatrix).toArray(),
      [0, 0, 0]
    );

    poseSequenceFrame(model, stepAnimation, 2.5);

    // The SAME record objects and the same GPU geometry: `update` merged the
    // callbacks and re-ran the effects pass. A rebuild would hand back new
    // records here, and that is the cost a video cannot pay 1800 times.
    assert.deepEqual(model.displayRecords, before);
    assert.equal(model.displayRecords.find((record) => record.partId === "left"), left);
    assert.equal(left.mesh.geometry, geometry);
    // And the frame actually moved: the clip translates Left by t.
    assert.deepEqual(
      new THREE.Vector3(0, 0, 0).applyMatrix4(left.effectMatrix).toArray(),
      [2.5, 0, 0]
    );

    poseSequenceFrame(model, stepAnimation, 0);
    assert.equal(model.displayRecords.find((record) => record.partId === "left"), left);
    assert.deepEqual(
      new THREE.Vector3(0, 0, 0).applyMatrix4(left.effectMatrix).toArray(),
      [0, 0, 0]
    );
  } finally {
    model.dispose();
  }
});

test("the camera frames the whole clip, not one pose of it", () => {
  const stepAnimation = resolveAnimationFrame(SLIDE_CLIPS, { clip: "slide", time: 0 });
  const model = buildSequenceModel(stepAnimation);
  try {
    const plan = resolveVideoPlan({ fps: 4, seconds: 4 }, SLIDE_CLIPS.slide);
    const bounds = sequenceFrameBounds(model, stepAnimation, plan);
    // Left starts at x 0..1 and the last frame (t = 3.75) slides it to 3.75..4.75,
    // so the union reaches past the resting model's own 0..3.
    assert.deepEqual(bounds.min, [0, 0, 0]);
    assert.deepEqual(bounds.max, [4.75, 1, 0]);
    // Fitting to frame 0 alone would have framed 0..3 and let the clip walk out
    // of shot; fitting per frame would have moved the camera on every one.
    const firstFrameBounds = poseSequenceFrame(model, stepAnimation, 0).bounds;
    assert.deepEqual(firstFrameBounds.max, [3, 1, 0]);
  } finally {
    model.dispose();
  }
});

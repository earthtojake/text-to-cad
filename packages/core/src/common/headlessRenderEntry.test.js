// The video sequence entry, tested at its load-bearing claim: why a video is
// affordable at all. A still pays for loadSource and buildModel and throws both
// away; a sequence pays once and then moves only the clock. That is a claim
// about cadScene's `update` — that a merged `callbacks.animation` re-runs the
// effects pass over the records already built instead of rebuilding them — so
// it is tested against a REAL model, by record identity, rather than against a
// mock that would agree with anything.
//
// The schedule those frames follow is arithmetic that now lives beside its own
// module: framePlan.test.js.

import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import { buildModel } from "./cadScene.js";
import { modelOptionsForRenderJob, renderJobContext } from "./renderMeshScene.js";
import { normalizeAnimationClips } from "./animationRuntime.js";
import { resolveAnimationFrame } from "./animationClock.js";
import { resolveFramePlan } from "./framePlan.js";
import {
  poseSequenceFrame,
  sequenceFrameBounds
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
    const plan = resolveFramePlan({ fps: 4, seconds: 4 }, SLIDE_CLIPS.slide);
    const bounds = sequenceFrameBounds(model, stepAnimation, plan);
    // Left starts at x 0..1 and the last frame (t = 3.75) slides it to 3.75..4.75,
    // so the union reaches past the resting model's own 0..3. It is padded by a
    // hair (sequenceFrameBounds samples rather than walking every frame), so the
    // union must CONTAIN the true extent and sit close outside it, not equal it.
    const margin = 0.01 * 4.75;
    for (const axis of [0, 1, 2]) {
      const low = [0, 0, 0][axis];
      const high = [4.75, 1, 0][axis];
      assert.ok(bounds.min[axis] <= low && bounds.min[axis] >= low - margin - 1e-9,
        `min[${axis}] ${bounds.min[axis]} brackets ${low}`);
      assert.ok(bounds.max[axis] >= high && bounds.max[axis] <= high + margin + 1e-9,
        `max[${axis}] ${bounds.max[axis]} brackets ${high}`);
    }
    // Fitting to frame 0 alone would have framed 0..3 and let the clip walk out
    // of shot; fitting per frame would have moved the camera on every one.
    const firstFrameBounds = poseSequenceFrame(model, stepAnimation, 0).bounds;
    assert.deepEqual(firstFrameBounds.max, [3, 1, 0]);
    // A long clip samples instead of enumerating: the pre-pass must not grow
    // with the frame count, or a 1,800-frame render pays for 1,800 poses of a
    // clip whose extent moved smoothly the whole time.
    let posed = 0;
    const counting = { ...model, update: (settings) => { posed += 1; return model.update(settings); } };
    sequenceFrameBounds(counting, stepAnimation, resolveFramePlan({ fps: 60, seconds: 30 }, SLIDE_CLIPS.slide));
    assert.ok(posed <= 192, `sampled ${posed} poses for an 1800-frame plan`);
  } finally {
    model.dispose();
  }
});

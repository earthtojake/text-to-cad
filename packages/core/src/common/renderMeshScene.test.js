import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import {
  buildModel
} from "./cadScene.js";
import {
  modelOptionsForRenderJob,
  projectedVisibleGeometryFrame,
  renderJobContext,
  renderMeshJob,
  resolveOutputCameraProjection
} from "./renderMeshScene.js";
import { evaluateAnimationClip, normalizeAnimationClips } from "./animationRuntime.js";
import { resolveAnimationFrame } from "./animationClock.js";
import { stepModuleFromKinematics } from "./kinematicsModule.js";
import { normalizeStepModuleDefinition } from "./stepModule.js";
import { normalizeStepParameterRenderValues } from "./stepParameters.js";
import { stepParameterRuntime } from "./source.js";

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
    bounds: {
      min: [0, 0, 0],
      max: [3, 1, 0]
    },
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

test("renderMeshJob list capture uses buildModel selection", async () => {
  const result = await renderMeshJob(twoPartMeshData(), {
    mode: "list",
    selection: {
      focus: ["right"]
    }
  });

  assert.equal(result.ok, true);
  assert.equal(result.mode, "list");
  // `ref` is the ONLY identifier a part carries: it pastes straight into --focus/--hide
  // and inspect. `id` and `occurrenceId` were the same string again and again (identical
  // in 600/600 parts on a real assembly) and are gone.
  assert.deepEqual(result.parts.map((part) => part.ref), ["#right"]);
  assert.deepEqual(Object.keys(result.parts[0]).sort(),
    ["bounds", "name", "ref", "triangleCount", "vertexCount"]);
  assert.deepEqual(result.bounds, {
    min: [2, 0, 0],
    max: [3, 1, 0]
  });
});

test("render view focus preserves full assembly while hide still filters", () => {
  const focusedContext = renderJobContext(twoPartMeshData(), {
    mode: "view",
    selection: {
      focus: ["right"]
    }
  });
  const focused = buildModel(
    THREE,
    twoPartMeshData(),
    modelOptionsForRenderJob(focusedContext, {
      mode: "view",
      selection: {
        focus: ["right"]
      }
    })
  );

  assert.deepEqual(focused.displayRecords.map((record) => record.partId), ["left", "right"]);
  assert.deepEqual(focused.bounds, {
    min: [0, 0, 0],
    max: [3, 1, 0]
  });
  // Focus must still be visible in the render: the focused part keeps full
  // opacity while every other part is ghosted, mirroring the interactive
  // viewer's focus treatment.
  const focusedById = new Map(focused.displayRecords.map((record) => [record.partId, record]));
  assert.equal(focusedById.get("right").material.opacity, 1);
  assert.ok(
    focusedById.get("left").material.opacity <= 0.05,
    `expected non-focused part to be ghosted, got opacity ${focusedById.get("left").material.opacity}`
  );
  focused.dispose();

  const hiddenContext = renderJobContext(twoPartMeshData(), {
    mode: "view",
    selection: {
      hide: ["left"]
    }
  });
  const hidden = buildModel(
    THREE,
    twoPartMeshData(),
    modelOptionsForRenderJob(hiddenContext, {
      mode: "view",
      selection: {
        hide: ["left"]
      }
    })
  );

  assert.deepEqual(hidden.displayRecords.map((record) => record.partId), ["right"]);
  assert.deepEqual(hidden.bounds, {
    min: [2, 0, 0],
    max: [3, 1, 0]
  });
  hidden.dispose();
});

test("projectedVisibleGeometryFrame fits actual vertices instead of sparse bounds", () => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array([
    -1, -1, 0,
    1, -1, 0,
    -1, 1, 0,
    1, 1, 0
  ]), 3));
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  mesh.updateWorldMatrix(true, false);
  const camera = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.01, 100);
  camera.position.set(0, 0, 10);
  camera.up.set(0, 1, 0);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);

  const frame = projectedVisibleGeometryFrame([{ mesh }], camera);

  assert.equal(frame.count, 4);
  assert.equal(frame.centerX, 0);
  assert.equal(frame.centerY, 0);
  assert.equal(frame.spanX, 2);
  assert.equal(frame.spanY, 2);
});

test("output projection echo follows the per-output camera decision", () => {
  const orthographicContext = { projection: "orthographic" };
  // Named preset on an orthographic theme stays orthographic.
  assert.equal(resolveOutputCameraProjection(orthographicContext, "iso"), "orthographic");
  // An explicit-position camera forces the perspective camera even on an
  // orthographic theme — the echo must say so.
  assert.equal(
    resolveOutputCameraProjection(orthographicContext, {
      position: [120, -90, 60],
      target: [0, 0, 0]
    }),
    "perspective"
  );
  // Perspective theme/display projection is perspective for any spec.
  assert.equal(resolveOutputCameraProjection({ projection: "perspective" }, "iso"), "perspective");
});

// A snapshot's still frame at clip time t must be the frame the viewer shows
// there. Both go through ONE effects pass (applySceneState, inside buildModel):
// kinematics folds the pose into effect matrices, then the clip's frame is
// merged OVER it. The snapshot reaches that pass through the job's
// `stepAnimation` -> callbacks.animation channel, the same key the docs hero
// drives playback with, so there is no snapshot-side twin to drift.
function roundedPoint(matrix, point) {
  return new THREE.Vector3(...point).applyMatrix4(matrix).toArray().map((v) => Math.round(v * 1e6) / 1e6);
}

const SLIDE_CLIPS = normalizeAnimationClips({
  slide: {
    duration: 4,
    update(t, m) {
      // The animation runtime addresses parts by label (part.label || part.name).
      m.get("Left").translate([t, 0, 0]);
    }
  }
});

function liftRuntime(liftMm) {
  // A one-mate kinematics block in the sidecar's RESOLVED form (world axis
  // numbers), compiled the way loadKinematicsModuleDefinition compiles it.
  const definition = normalizeStepModuleDefinition(
    stepModuleFromKinematics({
      mates: [{
        name: "lift",
        kind: "slider",
        parent: "#Right",
        child: "#Left",
        axis: { origin: [0, 0, 0], dir: [0, 0, 1] },
        limits: { value: [0, 10] }
      }]
    }),
    { url: "/__cad/asset?file=pair.step.json", cadPath: "pair.step" }
  );
  return stepParameterRuntime({
    definition,
    renderParameters: normalizeStepParameterRenderValues(definition, { lift: liftMm }),
    selectorRuntime: null,
    cadPath: "pair.step",
    sourceUrl: "/__cad/asset?file=pair.step.json"
  });
}

// The headless sequence: buildModel from the job's options (which carry the
// frame on callbacks.animation), then the per-output `model.update({
// stepParameters })` renderMeshJob performs before fitting each camera.
function buildStepModel(job) {
  const meshData = twoPartMeshData();
  const context = renderJobContext(meshData, job);
  const model = buildModel(THREE, { kind: "step", meshData }, modelOptionsForRenderJob(context, job));
  model.update({ stepParameters: job.stepParameters || null });
  return model;
}

test("the still frame rides the effects-pass channel the viewer and docs hero use", () => {
  const stepAnimation = resolveAnimationFrame(SLIDE_CLIPS, { clip: "slide", time: 1.5 });
  const job = { mode: "view", kind: "step", outputs: [{ path: "frame.png" }], stepAnimation };
  const options = modelOptionsForRenderJob(renderJobContext(twoPartMeshData(), job), job);
  // cadScene's applyParameters reads callbacks.animation; a job without a
  // frame request leaves the channel empty so the pass is pose-only.
  assert.equal(options.callbacks.animation, stepAnimation);
  assert.equal(
    modelOptionsForRenderJob(renderJobContext(twoPartMeshData(), {}), {}).callbacks.animation,
    null
  );
});

test("a snapshot frame at time t is the clip evaluated at t, on the rendered records", () => {
  const stepAnimation = resolveAnimationFrame(SLIDE_CLIPS, { clip: "slide", time: 1.5 });
  const model = buildStepModel({ mode: "view", kind: "step", outputs: [{ path: "frame.png" }], stepAnimation });
  try {
    const byId = new Map(model.displayRecords.map((record) => [record.partId, record]));
    // What the viewer's pass computes for the same clip and elapsedSec.
    const expected = evaluateAnimationClip(THREE, model.meshData, SLIDE_CLIPS.slide, 1.5);
    assert.deepEqual(
      roundedPoint(byId.get("left").effectMatrix, [0, 0, 0]),
      roundedPoint(expected.matrices.get("left"), [0, 0, 0])
    );
    assert.deepEqual(roundedPoint(byId.get("left").effectMatrix, [0, 0, 0]), [1.5, 0, 0]);
    // The clip never touched the other part, and neither did the still.
    assert.equal(byId.get("right").effectMatrix, null);
    // The frame moves the bounds the camera frames on, exactly as a pose does:
    // the left part now spans x 1.5..2.5 beside the untouched right part.
    assert.deepEqual(model.bounds.min, [1.5, 0, 0]);
    assert.deepEqual(model.bounds.max, [3, 1, 0]);
  } finally {
    model.dispose();
  }
});

test("a snapshot frame layers over the kinematics pose in the viewer's order", () => {
  const stepParameters = liftRuntime(4);
  const posed = buildStepModel({ mode: "view", kind: "step", outputs: [{ path: "pose.png" }], stepParameters });
  const poseMatrix = posed.displayRecords.find((record) => record.partId === "left").effectMatrix.clone();
  posed.dispose();
  assert.deepEqual(roundedPoint(poseMatrix, [0, 0, 0]), [0, 0, 4]);

  const stepAnimation = resolveAnimationFrame(SLIDE_CLIPS, { clip: "slide", time: 1.5 });
  const composed = buildStepModel({
    mode: "view", kind: "step", outputs: [{ path: "frame.png" }], stepParameters, stepAnimation
  });
  try {
    const left = composed.displayRecords.find((record) => record.partId === "left");
    // Pose first, choreography on top in world space: the clip's matrix
    // PREMULTIPLIES the pose (applyAnimationFrameToEffects), never the reverse.
    const animMatrix = evaluateAnimationClip(THREE, composed.meshData, SLIDE_CLIPS.slide, 1.5).matrices.get("left");
    const expected = new THREE.Matrix4().multiplyMatrices(animMatrix, poseMatrix);
    assert.deepEqual(
      left.effectMatrix.elements.map((v) => Math.round(v * 1e6) / 1e6),
      expected.elements.map((v) => Math.round(v * 1e6) / 1e6)
    );
    assert.deepEqual(roundedPoint(left.effectMatrix, [0, 0, 0]), [1.5, 0, 4]);
  } finally {
    composed.dispose();
  }
});

import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import { createStudioFrame, halton, studioFrameJitter } from "./studioFrame.js";

// The frame's passes are GPU work; what is checked here is what it draws WHEN: which sample a
// frame is, where the camera stands for it, how it is averaged, and that it leaves the camera
// and the renderer as it found them.
function rendererStub(scene) {
  const calls = { scenes: 0, passes: [], projections: [], cameraViews: [], presented: 0, targets: [] };
  let target = null;
  return {
    calls,
    autoClear: true,
    outputColorSpace: THREE.SRGBColorSpace,
    shadowMap: { enabled: true, autoUpdate: false, needsUpdate: false },
    getDrawingBufferSize(size) { return size.set(400, 300); },
    getRenderTarget() { return target; },
    setRenderTarget(next) { target = next; },
    render(drawn, camera) {
      if (drawn === scene) {
        calls.scenes += 1;
        calls.projections.push(camera.projectionMatrix.clone());
        calls.cameraViews.push(camera.view ? { ...camera.view } : null);
        assert.equal(target.isXRRenderTarget, true, "the scene is drawn with the canvas's programs");
        assert.equal(target.texture.colorSpace, THREE.SRGBColorSpace);
        return;
      }
      const material = drawn.children[0].material;
      // WebGL refuses a draw that samples a texture of the target it draws into.
      for (const { value } of Object.values(material.uniforms)) {
        if (!value?.isTexture || !target) continue;
        assert.ok(value !== target.texture && value !== target.depthTexture, "a pass samples its own target");
      }
      calls.passes.push({ target, blendAlpha: material.blendAlpha, blending: material.blending });
      if (target === null) calls.presented += 1;
    }
  };
}

function view() {
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 4 / 3, 1, 100);
  camera.position.set(10, -10, 8);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  return { scene, camera };
}

test("the jitter is a Halton sequence about the pixel's centre, none for the first sample", () => {
  assert.deepEqual(studioFrameJitter(0), [0, 0]);
  assert.equal(halton(1, 2), 0.5);
  assert.equal(halton(2, 3), 2 / 3);
  for (let index = 1; index < 64; index += 1) {
    for (const offset of studioFrameJitter(index)) assert.ok(offset >= -0.5 && offset < 0.5);
  }
  assert.deepEqual(studioFrameJitter(1), [0, 1 / 3 - 0.5]);
});

test("a still view converges over its samples, each averaged in at 1/(n+1), and then draws nothing new", () => {
  const { scene, camera } = view();
  const renderer = rendererStub(scene);
  const frame = createStudioFrame(THREE, { samples: 4 });
  const results = [];
  results.push(frame.render(renderer, scene, camera, { still: false }));
  for (let index = 0; index < 3; index += 1) results.push(frame.render(renderer, scene, camera, { still: true }));
  assert.deepEqual(results.map(({ refining, sample }) => [refining, sample]),
    [[true, 0], [true, 1], [true, 2], [false, 3]]);
  assert.equal(frame.converged, true);
  assert.equal(renderer.calls.scenes, 4);
  const composites = renderer.calls.passes.filter((pass) => pass.blending === THREE.CustomBlending);
  assert.deepEqual(composites.map((pass) => pass.blendAlpha), [1, 1 / 2, 1 / 3, 1 / 4]);
  assert.equal(renderer.calls.presented, 4, "every frame presents the accumulation");

  // Converged and still: the accumulation is presented again, nothing is drawn.
  assert.equal(frame.render(renderer, scene, camera, { still: true }).refining, false);
  assert.equal(renderer.calls.scenes, 4);
  assert.equal(renderer.calls.presented, 5);
  assert.equal(renderer.getRenderTarget(), null, "the caller's target is restored");
  frame.dispose();
});

test("anything but a still frame starts the picture again: a change, a camera move, a resize", () => {
  const { scene, camera } = view();
  const renderer = rendererStub(scene);
  const frame = createStudioFrame(THREE, { samples: 8 });
  frame.render(renderer, scene, camera);
  frame.render(renderer, scene, camera, { still: true });
  assert.equal(frame.sample, 2);
  assert.equal(frame.render(renderer, scene, camera, { still: false }).sample, 0, "a frame something else asked for");
  frame.render(renderer, scene, camera, { still: true });
  camera.position.x += 1;
  camera.updateMatrixWorld(true);
  assert.equal(frame.render(renderer, scene, camera, { still: true }).sample, 0, "a camera that moved");
  frame.render(renderer, scene, camera, { still: true });
  renderer.getDrawingBufferSize = (size) => size.set(800, 600);
  assert.equal(frame.render(renderer, scene, camera, { still: true }).sample, 0, "a resized canvas");
  frame.place({ radius: 5 });
  assert.equal(frame.render(renderer, scene, camera, { still: true }).sample, 0, "a model of another size");
  frame.dispose();
});

test("a camera still drifting by a fraction of a pixel (a damped orbit's tail) keeps sampling, and starts again once it has moved the model", () => {
  const { scene, camera } = view();
  const renderer = rendererStub(scene);
  const frame = createStudioFrame(THREE, { samples: 32 });
  frame.place({ radius: 2, center: [0, 0, 0] });
  frame.render(renderer, scene, camera);
  const nudge = (amount) => {
    camera.position.applyAxisAngle(new THREE.Vector3(0, 0, 1), amount);
    camera.lookAt(0, 0, 0);
    camera.updateMatrixWorld(true);
  };
  // 1e-5 rad a frame: a few thousandths of a pixel at this size.
  for (let index = 1; index < 6; index += 1) {
    nudge(1e-5);
    assert.equal(frame.render(renderer, scene, camera, { still: true }).sample, index);
  }
  // Drift is measured from the picture's first sample: small steps that add up start it again.
  let restarted = false;
  for (let step = 0; step < 400 && !restarted; step += 1) {
    nudge(2e-4);
    restarted = frame.render(renderer, scene, camera, { still: true }).sample === 0;
  }
  assert.equal(restarted, true);

  // A close-up from inside the model's bounds: the points behind the camera say nothing.
  frame.place({ radius: 100, center: [0, 0, 0] });
  frame.render(renderer, scene, camera);
  assert.equal(frame.render(renderer, scene, camera, { still: true }).sample, 1);
  frame.dispose();
});

test("each sample but the first moves the camera a fraction of a pixel, and the camera is left as it was", () => {
  const { scene, camera } = view();
  const renderer = rendererStub(scene);
  const frame = createStudioFrame(THREE, { samples: 3 });
  const projection = camera.projectionMatrix.clone();
  frame.render(renderer, scene, camera);
  frame.render(renderer, scene, camera, { still: true });
  frame.render(renderer, scene, camera, { still: true });
  const [first, second, third] = renderer.calls.projections;
  assert.ok(first.equals(projection), "the first sample is the view itself");
  assert.ok(!second.equals(projection) && !third.equals(projection) && !second.equals(third));
  assert.equal(renderer.calls.cameraViews[1].fullWidth, 400, "offset in drawing-buffer pixels");
  assert.equal(renderer.calls.cameraViews[1].offsetX, studioFrameJitter(1)[0]);
  assert.notEqual(camera.view?.enabled, true, "no view offset left on the camera");
  assert.ok(camera.projectionMatrix.equals(projection));
  frame.dispose();
});

test("the studio places its key for each sample and is told whether the casters may have changed", () => {
  const { scene, camera } = view();
  const renderer = rendererStub(scene);
  const seen = [];
  const frame = createStudioFrame(THREE, {
    samples: 3,
    onSample: (index, drawer, { castersChanged }) => seen.push(["sample", index, castersChanged, drawer === renderer]),
    afterSample: (index) => seen.push(["after", index])
  });
  renderer.shadowMap.needsUpdate = true;
  frame.render(renderer, scene, camera);
  renderer.shadowMap.needsUpdate = false;
  frame.render(renderer, scene, camera, { still: true });
  frame.render(renderer, scene, camera, { still: false });
  assert.deepEqual(seen, [
    ["sample", 0, true, true], ["after", 0],
    ["sample", 1, false, true], ["after", 1],
    ["sample", 0, false, true], ["after", 0]
  ]);
  frame.dispose();
});

test("a still picture draws every sample back to back, presents once, and re-renders shadows only when a sample asks", () => {
  const { scene, camera } = view();
  const renderer = rendererStub(scene);
  renderer.shadowMap.autoUpdate = true;
  const autoUpdates = [];
  const frame = createStudioFrame(THREE, {
    samples: 32,
    multisample: 0,
    onSample: (index, drawer) => autoUpdates.push(drawer.shadowMap.autoUpdate)
  });
  frame.renderStill(renderer, scene, camera, { samples: 6 });
  assert.equal(renderer.calls.scenes, 6);
  assert.equal(renderer.calls.presented, 1);
  assert.deepEqual(autoUpdates, [true, false, false, false, false, false]);
  assert.equal(renderer.shadowMap.autoUpdate, true, "restored");
  assert.equal(frame.samples, 32, "a still's count is its own");
  // Occlusion off: no occlusion passes, the composite still runs.
  frame.configure({ occlusion: { strength: 0 } });
  const before = renderer.calls.passes.length;
  frame.render(renderer, scene, camera);
  assert.equal(renderer.calls.passes.length - before, 2, "composite and present");
  frame.dispose();
  assert.throws(() => frame.render(renderer, scene, camera), /disposed/);
});

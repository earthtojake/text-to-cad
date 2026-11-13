import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import { createStudioFrame, halton, studioFrameJitter } from "./studioFrame.js";
import { studioReflectionShares } from "./studioReflections.js";

// The frame's passes are GPU work; what is checked here is what it draws WHEN: which sample a
// frame is, where the camera stands for it, how it is averaged, and that it leaves the camera
// and the renderer as it found them.
function rendererStub(scene) {
  const calls = { scenes: 0, geometry: [], passes: [], projections: [], cameraViews: [], presented: 0, targets: [] };
  let target = null;
  const clear = { color: new THREE.Color(0x123456), alpha: 0.5 };
  return {
    calls,
    clear,
    autoClear: true,
    outputColorSpace: THREE.SRGBColorSpace,
    toneMappingExposure: 1,
    shadowMap: { enabled: true, autoUpdate: false, needsUpdate: false },
    getDrawingBufferSize(size) { return size.set(400, 300); },
    getRenderTarget() { return target; },
    setRenderTarget(next) { target = next; },
    getClearColor(color) { return color.copy(clear.color); },
    getClearAlpha() { return clear.alpha; },
    setClearColor(color, alpha) { clear.color.set(color); clear.alpha = alpha; },
    render(drawn, camera) {
      if (drawn === scene && target?.textures?.length === 2) {
        // The reflections' geometry draw: the scene again, its meshes in stand-in materials.
        const materials = [];
        scene.traverse((object) => { if (object.isMesh) materials.push(object.material); });
        calls.geometry.push({ materials, projection: camera.projectionMatrix.clone(), background: scene.background,
          shadows: this.shadowMap.autoUpdate || this.shadowMap.needsUpdate });
        return;
      }
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

test("the reflections' shares: none for a picture's first sample, a fade in, and all of them over the picture", () => {
  assert.deepEqual(studioReflectionShares(1), [0], "a picture of one sample (a moving view) has none");
  for (const [total, fade] of [[32, 8], [64, 8], [4, 8], [6, 2]]) {
    const shares = studioReflectionShares(total, fade);
    assert.equal(shares.length, total);
    assert.equal(shares[0], 0);
    for (let index = 1; index < total; index += 1) assert.ok(shares[index] >= shares[index - 1] && shares[index] > 0);
    assert.ok(Math.abs(shares.reduce((a, b) => a + b, 0) / total - 1) < 1e-12, "their mean is 1");
  }
  const shares = studioReflectionShares(32, 8);
  assert.equal(shares[8], shares[31], "constant once faded in");
  assert.ok(Math.abs(shares[4] / shares[8] - 0.5) < 1e-12);
});

function reflectingView() {
  const found = view();
  const metal = new THREE.MeshStandardMaterial({ color: 0xc4967a, roughness: 0.34, metalness: 0.9 });
  const glass = new THREE.MeshStandardMaterial({ transparent: true, opacity: 0.4 });
  const part = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), metal);
  const pane = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), glass);
  found.scene.add(part, pane);
  found.scene.background = new THREE.Color(0xffffff);
  return { ...found, part, pane, metal, glass };
}

test("reflections leave a picture's first sample alone and join the samples of a still view", () => {
  const { scene, camera, part, pane, metal, glass } = reflectingView();
  const plain = rendererStub(scene);
  const without = createStudioFrame(THREE, { samples: 4 });
  without.render(plain, scene, camera);
  const renderer = rendererStub(scene);
  const frame = createStudioFrame(THREE, { samples: 4, reflections: true });
  assert.equal(frame.reflections, true);

  // A moving view: frame after frame of first samples, each exactly the frame's own passes.
  for (let index = 0; index < 3; index += 1) frame.render(renderer, scene, camera, { still: false });
  assert.equal(renderer.calls.geometry.length, 0, "no geometry draw while the view moves");
  assert.equal(renderer.calls.passes.length, plain.calls.passes.length * 3);
  assert.equal(renderer.calls.scenes, 3);
  assert.ok(frame.memoryBytes > without.memoryBytes, "its targets are counted");

  // At rest: each later sample draws the geometry once and three more passes (trace, two blurs).
  const before = renderer.calls.passes.length;
  renderer.shadowMap.needsUpdate = false;
  for (let index = 1; index < 4; index += 1) frame.render(renderer, scene, camera, { still: true });
  assert.equal(renderer.calls.scenes, 6);
  assert.equal(renderer.calls.geometry.length, 3);
  assert.equal(renderer.calls.passes.length - before, (plain.calls.passes.length + 3) * 3);
  const composites = renderer.calls.passes.filter((pass) => pass.blending === THREE.CustomBlending);
  assert.deepEqual(composites.slice(-3).map((pass) => pass.blendAlpha), [1 / 2, 1 / 3, 1 / 4], "averaged in as every sample is");

  // The geometry draw: the sample's own jittered camera, the opaque part in a stand-in that carries
  // its finish, the see-through part drawn as nothing, no background, no shadow pass.
  const [first] = renderer.calls.geometry;
  assert.ok(first.projection.equals(renderer.calls.projections[3]), "from the sample's own camera");
  assert.equal(first.materials[0].isShaderMaterial, true);
  assert.equal(first.materials[0].uniforms.uRoughness.value, 0.34);
  assert.equal(first.materials[0].uniforms.uMetalness.value, 0.9);
  assert.equal(first.materials[0].uniforms.uBase.value.getHex(), 0xc4967a);
  assert.equal(first.materials[1].visible, false, "what writes no depth is left out");
  assert.equal(first.background, null);
  assert.equal(first.shadows, false);
  assert.equal(renderer.calls.geometry[1].materials[0], first.materials[0], "one stand-in per material");

  // And everything is as it was.
  assert.equal(part.material, metal);
  assert.equal(pane.material, glass);
  assert.equal(scene.background.getHex(), 0xffffff);
  assert.equal(Object.hasOwn(scene, "onBeforeRender"), false);
  assert.equal(renderer.clear.color.getHex(), 0x123456);
  assert.equal(renderer.clear.alpha, 0.5);
  assert.equal(renderer.getRenderTarget(), null);
  frame.dispose();
  without.dispose();
});

test("reflections are turned on and off on a living frame, and a still's own count shares them out", () => {
  const { scene, camera } = reflectingView();
  const renderer = rendererStub(scene);
  const frame = createStudioFrame(THREE, { samples: 32, multisample: 0 });
  assert.equal(frame.reflections, false);
  frame.render(renderer, scene, camera);
  frame.render(renderer, scene, camera, { still: true });
  const plain = frame.memoryBytes;
  frame.configure({ reflections: true });
  assert.equal(frame.sample, 0, "the picture starts again");
  assert.equal(frame.memoryBytes, plain + 400 * 300 * 36, "36 bytes a pixel, sized as the frame is");
  frame.renderStill(renderer, scene, camera, { samples: 6 });
  assert.equal(renderer.calls.geometry.length, 5, "every sample of the still but its first");
  frame.configure({ reflections: false });
  assert.equal(frame.reflections, false);
  assert.equal(frame.memoryBytes, plain);
  frame.renderStill(renderer, scene, camera, { samples: 3 });
  assert.equal(renderer.calls.geometry.length, 5);
  frame.dispose();
});

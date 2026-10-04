import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import { createStudioFloorReflection } from "./studioFloorReflection.js";

// The mirrored draw is GPU work; what is checked here is WHEN it runs, what it leaves
// out, and that it leaves the renderer and the scene as it found them.
function rendererStub(scene) {
  const calls = { mirrored: 0, passes: 0, visibleDuringMirror: [], targets: [] };
  let target = null;
  const clearColor = new THREE.Color("#123456");
  let clearAlpha = 1;
  return {
    calls,
    autoClear: true,
    outputColorSpace: THREE.SRGBColorSpace,
    state: { buffers: { depth: { setMask() {} } } },
    shadowMap: { enabled: true, autoUpdate: false, needsUpdate: false },
    getDrawingBufferSize(size) { return size.set(800, 600); },
    getRenderTarget() { return target; },
    setRenderTarget(next) { target = next; },
    getClearColor(color) { return color.copy(clearColor); },
    getClearAlpha() { return clearAlpha; },
    setClearColor(color, alpha) { clearColor.set(color); clearAlpha = alpha; },
    clear() {},
    render(drawn, camera) {
      if (drawn !== scene) {
        calls.passes += 1;
        return;
      }
      calls.mirrored += 1;
      calls.targets.push(target);
      calls.shadowsDuringMirror = this.shadowMap.needsUpdate;
      assert.equal(target.isXRRenderTarget, true, "drawn with the canvas's programs");
      assert.ok(camera.position.z < 0, "from the camera mirrored in the floor");
      calls.visibleDuringMirror.push(drawn.children.map((child) => child.visible));
    }
  };
}

function floorScene() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#ffffff");
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial());
  const part = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial());
  scene.add(floor, part);
  const camera = new THREE.PerspectiveCamera(50, 4 / 3, 0.1, 100);
  camera.position.set(4, -4, 3);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  return { scene, floor, part, camera };
}

// A clock and a timer the test turns by hand: no sleeps, no wall clock.
function manualTime() {
  const time = { now: 0, timers: [], frames: 0 };
  time.options = {
    now: () => time.now,
    setTimer: (callback, ms) => { time.timers.push({ callback, at: time.now + ms }); return time.timers.length; },
    clearTimer: (id) => { time.timers[id - 1] = null; },
    requestFrame: () => { time.frames += 1; }
  };
  time.advance = (ms) => {
    time.now += ms;
    for (let index = 0; index < time.timers.length; index += 1) {
      const timer = time.timers[index];
      if (timer && timer.at <= time.now) { time.timers[index] = null; timer.callback(); }
    }
  };
  return time;
}

function orbit(camera, degrees) {
  camera.position.applyAxisAngle(new THREE.Vector3(0, 0, 1), THREE.MathUtils.degToRad(degrees));
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
}

test("the reflection is drawn when the camera moved or the casters changed, and a frame for anything else catches up once an interval", () => {
  const time = manualTime();
  const { scene, floor, camera } = floorScene();
  const reflection = createStudioFloorReflection(THREE, { interval: 250, ...time.options });
  reflection.place({ floorZ: 0, height: 1 });
  const renderer = rendererStub(scene);
  const frame = () => reflection.beforeRender(renderer, scene, camera, [floor]);
  assert.equal(reflection.uniforms.uReflectionReady.value, 0, "nothing shows before the first draw");

  frame();
  assert.equal(renderer.calls.mirrored, 1);
  assert.equal(reflection.uniforms.uReflectionReady.value, 1);
  // Each mirrored draw is faded, softened (a pass per axis) and combined in small passes.
  assert.equal(renderer.calls.passes, 4);

  // A camera move draws it again; a frame that changed neither waits out the interval.
  orbit(camera, 10);
  frame();
  assert.equal(renderer.calls.mirrored, 2);
  frame();
  assert.equal(renderer.calls.mirrored, 2, "a highlight's frame keeps the last reflection");
  time.advance(250);
  assert.equal(time.frames, 1, "and asks for the frame that catches up");
  frame();
  assert.equal(renderer.calls.mirrored, 3);

  // A frame that re-renders shadows changed the casters: the mirrored draw renders them,
  // and the frame keeps them rather than rendering them again.
  renderer.shadowMap.needsUpdate = true;
  frame();
  assert.equal(renderer.calls.mirrored, 4);
  assert.equal(renderer.calls.shadowsDuringMirror, true);
  assert.equal(renderer.shadowMap.needsUpdate, false);
  frame();
  assert.equal(renderer.calls.mirrored, 4);
  reflection.dispose();
});

test("the mirrored draw leaves out what it is given, and restores the renderer and the scene", () => {
  const { scene, floor, part, camera } = floorScene();
  const reflection = createStudioFloorReflection(THREE);
  reflection.place({ floorZ: 0, height: 1 });
  const renderer = rendererStub(scene);
  const background = scene.background;
  reflection.beforeRender(renderer, scene, camera, [floor]);
  assert.deepEqual(renderer.calls.visibleDuringMirror, [[false, true]]);
  assert.equal(floor.visible, true);
  assert.equal(part.visible, true);
  assert.equal(scene.background, background);
  assert.equal(scene.matrixWorldAutoUpdate, true);
  assert.equal(renderer.getRenderTarget(), null);
  assert.equal(renderer.autoClear, true);
  assert.equal(renderer.getClearAlpha(), 1);
  assert.equal(renderer.getClearColor(new THREE.Color()).getHexString(), "123456");
  assert.equal(renderer.calls.targets[0].isXRRenderTarget, false, "drawn as the canvas only while the scene is");
  assert.equal(reflection.uniforms.uReflection.value, renderer.calls.targets[0].texture);
  reflection.dispose();
});

test("seen from below the floor nothing is reflected", () => {
  const { scene, floor, camera } = floorScene();
  const reflection = createStudioFloorReflection(THREE);
  reflection.place({ floorZ: 0, height: 1 });
  const renderer = rendererStub(scene);
  reflection.beforeRender(renderer, scene, camera, [floor]);
  assert.equal(reflection.uniforms.uReflectionReady.value, 1);
  camera.position.set(4, -4, -3);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  reflection.beforeRender(renderer, scene, camera, [floor]);
  assert.equal(renderer.calls.mirrored, 1);
  assert.equal(reflection.uniforms.uReflectionReady.value, 0);
  reflection.dispose();
});

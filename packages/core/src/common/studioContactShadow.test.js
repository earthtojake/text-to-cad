import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import { createStudioContactShadow } from "./studioContactShadow.js";

// The bake itself is GPU work; what is checked here is WHEN it runs and that it
// leaves the renderer, and every caster's material, exactly as it found them.
function rendererStub() {
  const calls = { heights: 0, passes: 0, sidesDuringHeights: [] };
  let target = null;
  const renderer = {
    calls,
    autoClear: true,
    shadowMap: {
      enabled: true,
      autoUpdate: false,
      needsUpdate: false,
      render(lights, scene) {
        calls.heights += 1;
        assert.equal(lights.length, 1);
        assert.equal(this.needsUpdate, true, "the probe's own pass is forced");
        scene.traverse((object) => {
          if (object.castShadow && object.material) calls.sidesDuringHeights.push(object.material.shadowSide);
        });
      }
    },
    getRenderTarget() { return target; },
    setRenderTarget(next) { target = next; },
    render() { calls.passes += 1; }
  };
  return renderer;
}

function studio(options = {}) {
  const scene = new THREE.Scene();
  const keyLight = new THREE.SpotLight(0xffffff, 1);
  keyLight.castShadow = true;
  const contact = createStudioContactShadow(THREE, keyLight, options);
  scene.add(contact.object);
  const part = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshStandardMaterial());
  part.castShadow = true;
  scene.add(part);
  contact.place({ center: [0, 0, 0], half: 10, floorZ: 0, height: 5 });
  return { scene, keyLight, contact, part, camera: new THREE.PerspectiveCamera() };
}

test("the floor shadow bakes after the key's shadows re-render, never on a camera-only frame", () => {
  const { scene, keyLight, contact, camera } = studio();
  const renderer = rendererStub();
  const frame = () => contact.layer.onBeforeRender(renderer, scene, camera);
  assert.equal(contact.layer.material.uniforms.uReady.value, 0, "nothing shows before the first bake");

  frame();
  assert.equal(renderer.calls.heights, 1);
  assert.equal(renderer.calls.passes, 3, "one prepare and two blur passes");
  assert.equal(contact.layer.material.uniforms.uReady.value, 1);

  // Frames that only moved the camera re-render no shadows: nothing is baked.
  frame();
  frame();
  assert.equal(renderer.calls.heights, 1);

  // The probe's own shadow pass is not a reason to bake again.
  contact.sentinel.onBeforeShadow(renderer, contact.sentinel, camera, contact.probe.shadow.camera);
  frame();
  assert.equal(renderer.calls.heights, 1);

  // The key's shadow pass is.
  contact.sentinel.onBeforeShadow(renderer, contact.sentinel, camera, keyLight.shadow.camera);
  assert.equal(contact.stale, true);
  frame();
  assert.equal(renderer.calls.heights, 2);
  assert.equal(contact.stale, false);
});

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
  time.pending = () => time.timers.filter(Boolean).length;
  return time;
}

test("while the scene keeps changing the key's shadow composites every frame, the heights at most once an interval and once more at rest", () => {
  const time = manualTime();
  const { scene, keyLight, contact, camera } = studio({ heightInterval: 100, ...time.options });
  const renderer = rendererStub();
  const keyPass = () => contact.sentinel.onBeforeShadow(renderer, contact.sentinel, camera, keyLight.shadow.camera);
  const frame = () => contact.layer.onBeforeRender(renderer, scene, camera);

  frame();
  assert.deepEqual([renderer.calls.heights, renderer.calls.passes], [1, 3], "the first bake is whole and immediate");

  // A routine plays: every frame re-renders the key's shadows.
  for (let step = 1; step <= 5; step += 1) {
    time.advance(16);
    keyPass();
    frame();
  }
  assert.equal(renderer.calls.heights, 1, "no height pass within the interval");
  assert.equal(renderer.calls.passes, 3 + 5 * 3, "the key's cast shadow is composited on every frame");
  assert.equal(time.pending(), 1, "one frame is asked for, for when the heights are due");

  // t = 100: the interval has passed. The asked-for frame and the routine's next coincide.
  time.advance(20);
  assert.equal(time.frames, 1);
  keyPass();
  frame();
  assert.equal(renderer.calls.heights, 2, "due again once the interval has passed");
  assert.equal(time.pending(), 0);

  // The routine stops between two height passes: the last pose's heights are still owed.
  time.advance(16);
  keyPass();
  frame();
  assert.equal(renderer.calls.heights, 2);
  assert.equal(contact.stale, true);
  time.advance(100);
  assert.equal(time.frames, 2, "the frame that renders them is asked for");
  frame();
  assert.equal(renderer.calls.heights, 3);
  assert.equal(contact.stale, false, "exact at rest");
  const passes = renderer.calls.passes;
  frame();
  time.advance(500);
  frame();
  assert.equal(renderer.calls.passes, passes, "at rest nothing more is baked");
  assert.equal(time.frames, 2);
});

test("heights a moving scene's own frame renders cancel the frame asked for them", () => {
  const time = manualTime();
  const { scene, keyLight, contact, camera } = studio({ heightInterval: 100, ...time.options });
  const renderer = rendererStub();
  const keyPass = () => contact.sentinel.onBeforeShadow(renderer, contact.sentinel, camera, keyLight.shadow.camera);
  const frame = () => contact.layer.onBeforeRender(renderer, scene, camera);
  frame();
  time.advance(16);
  keyPass();
  frame();
  assert.equal(time.pending(), 1, "a frame is asked for, for when the heights are due");
  // The routine's own frame lands first, inside the last millisecond, and renders them.
  time.advance(83.5);
  keyPass();
  frame();
  assert.equal(renderer.calls.heights, 2);
  assert.equal(time.pending(), 0, "that frame is no longer owed");
  time.advance(200);
  assert.equal(time.frames, 0, "and is never asked for");
});

test("a floor at zero opacity is not drawn, so it bakes nothing; shown again it bakes at once", () => {
  const time = manualTime();
  const { scene, keyLight, contact, camera } = studio({ heightInterval: 100, ...time.options });
  const renderer = rendererStub();
  const frame = () => { if (contact.layer.visible) contact.layer.onBeforeRender(renderer, scene, camera); };
  frame();
  contact.setOpacity(0);
  assert.equal(contact.layer.visible, false);
  time.advance(16);
  contact.sentinel.onBeforeShadow(renderer, contact.sentinel, camera, keyLight.shadow.camera);
  frame();
  assert.deepEqual([renderer.calls.heights, renderer.calls.passes], [1, 3]);
  assert.equal(time.pending(), 0, "nothing is owed while nothing is drawn");

  contact.setOpacity(0.6);
  assert.equal(contact.layer.visible, true);
  frame();
  assert.deepEqual([renderer.calls.heights, renderer.calls.passes], [2, 6], "within the interval, still at once");
  assert.equal(contact.stale, false);
  contact.setOpacity(0.6);
  frame();
  assert.equal(renderer.calls.passes, 6, "an unchanged opacity re-bakes nothing");
  contact.dispose();
});

test("the bake restores the renderer and draws single-sided casters double-sided for its own pass only", () => {
  const { scene, contact, part, camera } = studio();
  const renderer = rendererStub();
  const previousTarget = { name: "screen-target" };
  renderer.setRenderTarget(previousTarget);
  part.material.shadowSide = null;
  contact.layer.onBeforeRender(renderer, scene, camera);
  assert.ok(renderer.calls.sidesDuringHeights.includes(THREE.DoubleSide));
  assert.equal(part.material.shadowSide, null);
  assert.equal(renderer.getRenderTarget(), previousTarget);
  assert.equal(renderer.autoClear, true);
  assert.equal(renderer.shadowMap.needsUpdate, false);
  assert.equal(renderer.shadowMap.autoUpdate, false);
});

test("an unchanged placement re-bakes nothing; a moved floor or model does", () => {
  const { scene, contact, camera } = studio();
  const renderer = rendererStub();
  contact.layer.onBeforeRender(renderer, scene, camera);
  contact.place({ center: [0, 0, 0], half: 10, floorZ: 0, height: 5 });
  assert.equal(contact.stale, false);
  contact.place({ center: [0, 0, 0], half: 10, floorZ: -2, height: 5 });
  assert.equal(contact.stale, true);
  assert.equal(contact.layer.position.z, -2);
  assert.ok(contact.layer.scale.x > 20, "the baked square leaves a margin for its faded edge");
  // The probe looks straight up through the floor from just below it.
  const probeCamera = contact.probe.shadow.camera;
  assert.ok(contact.probe.position.z < -2);
  assert.ok(contact.probe.target.position.z > -2);
  assert.equal(probeCamera.right, contact.layer.scale.x / 2);
});

test("a disabled floor shadow hides, and without shadow maps nothing is baked", () => {
  const { scene, contact, camera } = studio();
  const renderer = rendererStub();
  contact.layer.onBeforeRender(renderer, scene, camera);
  contact.setEnabled(false);
  assert.equal(contact.layer.visible, false);
  contact.setEnabled(true);
  assert.equal(contact.layer.visible, true);
  assert.equal(contact.stale, true, "re-enabled after the scene may have changed");

  renderer.shadowMap.enabled = false;
  contact.layer.onBeforeRender(renderer, scene, camera);
  assert.equal(renderer.calls.heights, 1);

  contact.setOpacity(0.25);
  assert.equal(contact.layer.material.uniforms.uOpacity.value, 0.25);
  contact.dispose();
  assert.equal(contact.object.parent, null);
});

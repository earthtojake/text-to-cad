import assert from "node:assert/strict";
import test from "node:test";

import { createRealOrbitRuntime } from "./harness/realOrbit.js";
import {
  orbitControlsDeltaSeconds,
  PREVIEW_AUTO_ROTATE_SPEED,
  PREVIEW_ORBIT_SECONDS_PER_TURN,
  stopOrbitMomentum,
  updateOrbitControls
} from "./orbitControls.js";

test("preview auto-rotate speed uses the configured full-turn duration", () => {
  assert.equal(PREVIEW_ORBIT_SECONDS_PER_TURN, 60);
  assert.equal(PREVIEW_AUTO_ROTATE_SPEED, 1);
});

test("orbitControlsDeltaSeconds converts animation timestamps from ms to seconds", () => {
  assert.equal(orbitControlsDeltaSeconds(1016, 1000), 0.016);
});

test("orbitControlsDeltaSeconds preserves slow render frames", () => {
  assert.equal(orbitControlsDeltaSeconds(1400, 1000), 0.4);
});

test("orbitControlsDeltaSeconds clamps stale frame gaps", () => {
  assert.equal(orbitControlsDeltaSeconds(3000, 1000), 1);
});

test("updateOrbitControls passes seconds while auto-rotate is active", () => {
  const updateArgs = [];
  const controls = {
    autoRotate: true,
    update(...args) {
      updateArgs.push(args);
      return true;
    }
  };
  const state = { orbitControlsLastTimestamp: 1000 };

  assert.equal(updateOrbitControls(controls, 1016, state), true);
  assert.deepEqual(updateArgs, [[0.016]]);
  assert.equal(state.orbitControlsLastTimestamp, 1016);
});

test("updateOrbitControls resets timing when auto-rotate is inactive", () => {
  const updateArgs = [];
  const controls = {
    autoRotate: false,
    update(...args) {
      updateArgs.push(args);
      return false;
    }
  };
  const state = { orbitControlsLastTimestamp: 1016 };

  assert.equal(updateOrbitControls(controls, 1032, state), false);
  assert.deepEqual(updateArgs, [[]]);
  assert.equal(state.orbitControlsLastTimestamp, 0);
});

test("stopOrbitMomentum drops the drag momentum damping would keep adding on update", () => {
  // Real OrbitControls: the fields it reaches into are three's own, and a rename must fail here.
  for (const field of ["_sphericalDelta", "_panOffset", "_scale"]) {
    assert.ok(field in createRealOrbitRuntime().controls, `three's OrbitControls still has ${field}`);
  }
  for (const drag of [runtime => runtime.drag(90, 30), runtime => runtime.drag(40, 25, { pan: true })]) {
    const runtime = createRealOrbitRuntime();
    drag(runtime);
    const held = [runtime.camera.position.x, runtime.camera.position.y, runtime.camera.position.z];
    assert.equal(stopOrbitMomentum(runtime.controls), true);
    runtime.controls.update();
    // (a spherical round trip moves the last bits, never more)
    assert.ok(runtime.camera.position.toArray().every((value, index) => Math.abs(value - held[index]) < 1e-9), "the next update adds nothing");
    // Without it the same update would have kept coasting.
    const coasting = createRealOrbitRuntime();
    drag(coasting);
    coasting.controls.update();
    assert.ok(coasting.camera.position.toArray().some((value, index) => Math.abs(value - held[index]) > 1e-3), "it coasts on without it");
  }
  assert.equal(stopOrbitMomentum(null), false);
});

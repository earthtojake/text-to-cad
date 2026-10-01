import assert from "node:assert/strict";
import test from "node:test";

import { createRealOrbitRuntime } from "./harness/realOrbit.js";
import { applyPerspectiveSnapshot, stepCameraTransition, transitionCameraToPerspectiveSnapshot, transitionCameraToViewPreset } from "./runtimeCamera.js";

// The camera a host hands the viewport is driven through a REAL three OrbitControls, so a
// three change to what `update()` does to a pose is caught here rather than in the browser.

const asked = { position: [30, -20, 15], target: [1, 2, 3], up: [0, 0, 1] };
const vectorOf = vector => [vector.x, vector.y, vector.z];
const closeTo = (actual, expected) => actual.every((value, index) => Math.abs(value - expected[index]) < 1e-9);

test("applyPerspectiveSnapshot leaves the camera where it was put while the Preview orbit plays", () => {
  const runtime = createRealOrbitRuntime({ autoRotate: true });
  assert.equal(applyPerspectiveSnapshot(runtime, asked), true);
  assert.ok(closeTo(vectorOf(runtime.camera.position), asked.position), `position ${vectorOf(runtime.camera.position)} is the request, not one auto-rotate step on`);
  assert.ok(closeTo(vectorOf(runtime.controls.target), asked.target));
  assert.equal(runtime.controls.autoRotate, true, "and the orbit is still playing afterwards");
});

// One frame of the viewer's loop (`useViewerRuntime.renderFrame`): the transition steps, then
// the controls update.
const frameAtStart = runtime => {
  stepCameraTransition(runtime, runtime.cameraTransition.startTime);
  runtime.controls.update();
};

test("an eased fit starts from where the camera was, not from a drag's leftover momentum", () => {
  const runtime = createRealOrbitRuntime();
  runtime.drag(120, 40);
  const start = vectorOf(runtime.camera.position);
  assert.equal(transitionCameraToPerspectiveSnapshot(runtime, { position: [60, 0, 0], target: [0, 0, 0], up: [0, 0, 1] }), true);
  frameAtStart(runtime);
  assert.ok(closeTo(vectorOf(runtime.camera.position), start), `first frame ${vectorOf(runtime.camera.position)} is the lerp at progress 0 (${start})`);
});

test("an eased view-plane move starts from where the camera was, not from a drag's leftover momentum", () => {
  const runtime = createRealOrbitRuntime();
  runtime.drag(-90, 70);
  const start = vectorOf(runtime.camera.position);
  assert.equal(transitionCameraToViewPreset(runtime, { direction: [1, 0, 0], up: [0, 0, 1] }), true);
  frameAtStart(runtime);
  assert.ok(closeTo(vectorOf(runtime.camera.position), start), `first frame ${vectorOf(runtime.camera.position)} is the lerp at progress 0 (${start})`);
});

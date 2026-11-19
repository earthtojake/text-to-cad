import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";
import {
  getKeyboardOrbitCommand,
  reframeReason,
  runtimeFramingBounds,
  stepKeyboardOrbit,
  VIEWING_MODE,
  VIEW_CUBE_CORNERS,
  VIEW_CUBE_EDGES,
  VIEW_PLANE_FACES,
  viewPlaneCameraBasis,
  viewportFitScale
} from "./viewportCameraKit.js";
import { turnSense } from "./turntable.js";

// The framed area of a viewport with a top bar and no side sheets, then the same
// window with a sheet open. Only the ratio between two scales is used, so these
// read as "how much further back the camera has to sit than it did before".
const wide = { aspect: 1120 / 756 };
const narrow = { aspect: 355 / 756 };

test("perspective fit scale is fixed while the framed area stays wider than tall", () => {
  // The vertical field of view is what frames the model, so extra width changes
  // nothing -- and a resize that only adds width must not move the camera.
  const square = viewportFitScale({ fov: 48, aspect: 1 });
  assert.ok(Math.abs(viewportFitScale({ fov: 48, aspect: 2.4 }) - square) < 1e-9);
  assert.ok(Math.abs(viewportFitScale({ fov: 48, aspect: 1.4 }) - square) < 1e-9);
  assert.ok(Math.abs(square - 1 / Math.sin((48 * Math.PI) / 360)) < 1e-9);
});

test("perspective fit scale grows once the framed area is taller than wide", () => {
  const half = viewportFitScale({ fov: 48, aspect: 0.5 });
  assert.ok(half > viewportFitScale({ fov: 48, aspect: 1 }));
  // Width is the limiting dimension now, so halving it pulls the camera back
  // by close to 2x -- exactly 2x only in the small-angle limit.
  assert.ok(half / viewportFitScale({ fov: 48, aspect: 1 }) > 1.8);
});

test("orthographic fit scale tracks the smaller viewport dimension", () => {
  // R / min(width, height) per unit height, expressed per unit radius.
  assert.ok(Math.abs(viewportFitScale({ orthographic: true, ...wide }) - 1) < 1e-9);
  assert.ok(Math.abs(viewportFitScale({ orthographic: true, ...narrow }) - 756 / 355) < 1e-9);
});

test("closing a sheet undoes the scale change that opening it made", () => {
  // Reframing is applied as a ratio, so a viewport that comes back to where it
  // started has to leave the camera where it started.
  const opened = viewportFitScale({ orthographic: true, ...narrow }) / viewportFitScale({ orthographic: true, ...wide });
  const closed = viewportFitScale({ orthographic: true, ...wide }) / viewportFitScale({ orthographic: true, ...narrow });
  assert.ok(opened > 2);
  assert.ok(Math.abs(opened * closed - 1) < 1e-12);
});

test("degenerate viewports fall back instead of producing a non-finite scale", () => {
  for (const metrics of [
    {},
    { aspect: 0 },
    { aspect: Number.NaN },
    { orthographic: true, aspect: 0 },
    { orthographic: true, aspect: Number.NaN },
    { fov: 0, aspect: 1 },
    { fov: Number.NaN, aspect: 1 }
  ]) {
    const scale = viewportFitScale(metrics);
    assert.ok(Number.isFinite(scale) && scale > 0, `bad scale for ${JSON.stringify(metrics)}`);
  }
});

// --- view-plane camera basis -------------------------------------------------------------
//
// A "top" view that is not top-down was the bug the old pole offset (0.02, then 1e-4) carried:
// orthographic projects parallel, so vertical faces that should collapse to nothing acquire
// width at any tilt. The turntable needs no offset, so a pole view is exactly on its pole.

const WORLD_UP_AXIS = [0, 0, 1];

test("every view lands upright and level: off the poles under the world's up, the poles exactly on them with +Y up the screen", () => {
  for (const view of [...VIEW_PLANE_FACES, ...VIEW_CUBE_EDGES, ...VIEW_CUBE_CORNERS]) {
    const basis = viewPlaneCameraBasis(view, WORLD_UP_AXIS);
    const length = Math.hypot(...view.direction);
    assert.deepEqual(basis.direction, view.direction.map(value => value / length), `${view.id} looks exactly along its own direction`);
    const pole = Math.abs(view.direction[2]) === length;
    assert.deepEqual(basis.up, pole ? [0, 1, 0] : WORLD_UP_AXIS, `${view.id}'s up`);
    // Landed: the camera's right is level and its screen's up never points down the world.
    const camera = new THREE.OrthographicCamera();
    camera.position.set(...basis.direction);
    camera.up.set(...basis.up);
    camera.lookAt(0, 0, 0);
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion);
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion);
    assert.ok(Math.abs(right.z) < 1e-12 && up.z > -1e-12, `${view.id} lands upright: right ${right.toArray()}, up ${up.toArray()}`);
    if (pole) assert.ok(up.y > 1 - 1e-12, `${view.id}: +Y up the screen, as the poles always were`);
  }
});

test("a malformed preset is refused rather than producing a broken camera", () => {
  assert.equal(viewPlaneCameraBasis(null, WORLD_UP_AXIS), null);
  assert.equal(viewPlaneCameraBasis({ direction: [0, 0, 0], up: [0, 1, 0] }, WORLD_UP_AXIS), null);
  assert.equal(viewPlaneCameraBasis({ direction: [0, 0, 1], up: [0, 0, 0] }, WORLD_UP_AXIS), null);
});

// Reset and fit are grounded on the model's zero pose. `modelBounds` is the live
// pose -- what lighting, the floor and clipping follow -- and framing against it
// is what made the zoom move when the kinematics did.
const ZERO_POSE = { min: [0, 0, 0], max: [10, 4, 2] };
const POSED = { min: [-6, 0, 0], max: [10, 4, 30] };

test("reset and fit frame the zero pose, never the pose on screen", () => {
  assert.deepEqual(
    runtimeFramingBounds({ zeroPoseBounds: ZERO_POSE, modelBounds: POSED }),
    ZERO_POSE
  );
});

test("before adoption only authored fallback bounds can define the zoom ruler", () => {
  const fallback = { min: [1, 1, 1], max: [2, 2, 2] };
  assert.deepEqual(runtimeFramingBounds({ modelBounds: POSED }, fallback), fallback);
  assert.deepEqual(runtimeFramingBounds({}, fallback), fallback);
  assert.equal(runtimeFramingBounds(null), null);
  assert.equal(runtimeFramingBounds({ modelBounds: POSED }), null, "never use live bounds to define the original zoom");
});

// A model is framed once per viewing mode, on its zero pose. These are the only
// three things that reopen that decision, and neither a pose nor a rebuild is one of them.
const FRAMED = {
  modelKey: "hinge.step",
  framedModelKey: "hinge.step",
  framedCompleteModelKey: "hinge.step",
  mode: VIEWING_MODE.INSPECT,
  framedMode: VIEWING_MODE.INSPECT,
  modelComplete: true
};

test("a different model always fits, even over a camera the user took", () => {
  assert.equal(reframeReason({ ...FRAMED, modelKey: "other.step", userMovedCamera: true }), "model");
  assert.equal(reframeReason({ modelKey: "hinge.step" }), "model", "nothing framed yet is a new model");
});

test("a progressive load whose box still grows fits again when the last component lands, once", () => {
  const loading = { ...FRAMED, framedCompleteModelKey: "", modelComplete: false };
  assert.equal(reframeReason(loading), "", "a partial publish keeps the first frame");
  assert.equal(reframeReason({ ...loading, modelComplete: true }), "complete");
  assert.equal(reframeReason(FRAMED), "", "and not on every publish after that");
});

// The owner's call: "keeping the perspective and zoom level makes sense in every case". A
// saved revision and another publish of the same geometry are both the same
// model, framed already; whatever its zero pose did, only the person's Zoom to fit re-frames it.
test("a rebuild never re-frames, whether its zero pose grew, shrank or stayed", () => {
  const framedOn = { min: [0, 0, 0], max: [10, 4, 2] };
  for (const rebuilt of [{ min: [0, 0, 0], max: [40, 4, 2] }, { min: [2, 1, 0], max: [5, 3, 1] }, { ...framedOn }]) {
    assert.equal(reframeReason({ ...FRAMED, zeroPoseBounds: rebuilt, framedZeroPoseBounds: framedOn }), "",
      `a rebuild to ${JSON.stringify(rebuilt)} keeps the camera`);
    assert.equal(reframeReason({ ...FRAMED, mode: VIEWING_MODE.RENDER, framedMode: VIEWING_MODE.RENDER,
      zeroPoseBounds: rebuilt, framedZeroPoseBounds: framedOn }), "", "in Render as in Inspect");
  }
});

test("the user's own camera stands through a completion", () => {
  assert.equal(reframeReason({ ...FRAMED, framedCompleteModelKey: "", userMovedCamera: true }), "");
});

test("entering a viewing mode fits that mode's own camera, over one the user took", () => {
  const entered = { ...FRAMED, mode: VIEWING_MODE.RENDER };
  assert.equal(reframeReason(entered), "mode", "Render does not inherit Inspect's framing");
  assert.equal(reframeReason({ ...entered, userMovedCamera: true }), "mode",
    "a hand-framed Inspect view does not follow the model into Render");
  assert.equal(
    reframeReason({ ...FRAMED, mode: VIEWING_MODE.INSPECT, framedMode: VIEWING_MODE.RENDER }),
    "mode",
    "and back again"
  );
});

test("staying in a mode is not a reason to re-fit", () => {
  assert.equal(reframeReason(FRAMED), "");
  assert.equal(reframeReason({ ...FRAMED, mode: VIEWING_MODE.RENDER, framedMode: VIEWING_MODE.RENDER }), "");
});

test("a different model opened in another mode is the model's own fit", () => {
  assert.equal(
    reframeReason({ ...FRAMED, modelKey: "other.step", mode: VIEWING_MODE.RENDER, userMovedCamera: true }),
    "model"
  );
});

test('the lit cube face follows the camera direction, and the cube reads the camera through one scratch per runtime', async () => {
  const THREE = await import('three');
  const { getActiveViewPlaneFaceId, readViewPlaneOrientation } = await import('./viewportCameraKit.js');
  const camera = new THREE.PerspectiveCamera();
  const runtime = { THREE, camera, controls: { target: new THREE.Vector3(1, 2, 3) } };
  const look = (x, y, z) => { camera.position.set(1 + x, 2 + y, 3 + z); camera.up.set(0, 0, 1); camera.lookAt(1, 2, 3); };
  look(0, 0, 10);
  assert.equal(getActiveViewPlaneFaceId(runtime), 'z');
  look(10, 10, 10);
  assert.match(getActiveViewPlaneFaceId(runtime), /\S/, 'a corner view lights its corner');
  look(10, 3, 1);
  assert.equal(getActiveViewPlaneFaceId(runtime), '', 'between presets nothing is lit');
  camera.position.copy(runtime.controls.target);
  assert.equal(getActiveViewPlaneFaceId(runtime), '');
  // The orientation reads through one scratch rotation and vector per runtime, frame after frame.
  look(0, -10, 0);
  const front = readViewPlaneOrientation(runtime);
  const scratch = { ...runtime.viewPlaneScratch };
  look(10, 0, 0);
  const side = readViewPlaneOrientation(runtime);
  assert.equal(runtime.viewPlaneScratch.rotation, scratch.rotation);
  assert.equal(runtime.viewPlaneScratch.axis, scratch.axis);
  assert.ok(Math.abs(front.z[1] - 1) < 1e-9, 'from the front, +Z points up the screen');
  assert.ok(Math.abs(side.x[2] - 1) < 1e-9, 'from the +X side, +X points at the viewer');
});

test("a held arrow key goes over the top and on, never rolling, and holds its sideways sense to the keys' release", () => {
  const camera = new THREE.PerspectiveCamera();
  camera.up.set(0, 0, 1);
  camera.position.set(0, -10, 5);
  camera.lookAt(0, 0, 0);
  const keyboardOrbitState = { pressedKeys: new Set(["ArrowUp"]), directionCounts: { left: 0, right: 0, up: 1, down: 0 }, lastFrameTime: 0, sense: 1 };
  const runtime = { THREE, camera, controls: { target: new THREE.Vector3() }, keyboardOrbitState };
  const axes = () => ({ right: new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion), up: new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion) });
  let highest = -1;
  // Two seconds of ArrowUp at 60 frames a second: 151° up from 27° above the horizon.
  for (let frame = 0; frame <= 120; frame += 1) {
    stepKeyboardOrbit(runtime, 1000 + frame * (1000 / 60));
    highest = Math.max(highest, camera.position.z / camera.position.length());
    assert.ok(Math.abs(axes().right.z) < 1e-9, `frame ${frame}: level`);
  }
  assert.ok(highest > 0.99, "it went straight over the top");
  assert.ok(axes().up.z < -0.5 && camera.position.y > 0, "and on, upside down beyond it");
  // ArrowRight held with it: the sense the keys began with (upright, the plain way: anticlockwise from above).
  const before = Math.atan2(camera.position.y, camera.position.x);
  keyboardOrbitState.directionCounts = { left: 0, right: 1, up: 0, down: 0 };
  stepKeyboardOrbit(runtime, 4000);
  stepKeyboardOrbit(runtime, 4016);
  const held = Math.atan2(camera.position.y, camera.position.x);
  assert.ok(held > before, "held: the plain way, though the view is upside down now");
  // Keys pressed afresh, upside down (`useViewerRuntime.js` picks the sense as the first goes down): the other way.
  keyboardOrbitState.sense = turnSense(camera, runtime.controls.target);
  assert.equal(keyboardOrbitState.sense, -1);
  stepKeyboardOrbit(runtime, 4032);
  assert.ok(Math.atan2(camera.position.y, camera.position.x) < held, "begun upside down: the other way about the world");
});

test("the arrow keys orbit and the letters reach nothing in the camera", () => {
  assert.deepEqual(getKeyboardOrbitCommand({ key: "ArrowLeft" }), { direction: "left", keyId: "ArrowLeft" });
  assert.deepEqual(getKeyboardOrbitCommand({ key: "ArrowDown" }), { direction: "down", keyId: "ArrowDown" });
  for (const letter of ["w", "a", "s", "d", "W", "A", "S", "D"]) {
    assert.equal(getKeyboardOrbitCommand({ key: letter, code: `Key${letter.toUpperCase()}` }), null);
  }
});

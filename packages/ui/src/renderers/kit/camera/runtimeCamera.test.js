import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';

import { stepCameraTransition, transitionCameraToPerspectiveSnapshot } from './runtimeCamera.js';
import { viewPlaneCameraBasis, WORLD_UP } from './viewportCameraKit.js';

/**
 * An eased camera move turns the camera about its target: its eye goes round, never through it. A camera
 * turned over (a board's Flip: the eye over the board's left-to-right axis, `[x, -y, -z]` from its target,
 * the up kept) from straight above went on a chord through its target and jumped a half turn in a frame.
 */

const TARGET = [10, -20, 0];
function runtimeAt(direction, distance = 150, up = WORLD_UP) {
  const camera = new THREE.OrthographicCamera(-50, 50, 40, -40, 0.01, 10000);
  camera.position.set(...TARGET.map((value, axis) => value + direction[axis] * distance));
  camera.up.set(...up);
  camera.lookAt(...TARGET);
  return { THREE, camera, controls: { target: new THREE.Vector3(...TARGET), update() {}, dispatchEvent() {} } };
}
/** Every frame of a move, 60 a second, until it is done: the eye, the way it looks, the screen's up and its right. */
function framesOf(runtime, to) {
  assert.equal(transitionCameraToPerspectiveSnapshot(runtime, to), true);
  const { startTime } = runtime.cameraTransition;
  const frames = [];
  for (let at = 0; ; at += 1000 / 60) {
    const moving = stepCameraTransition(runtime, startTime + at);
    runtime.camera.updateMatrixWorld();
    frames.push({ eye: runtime.camera.position.clone(), look: runtime.camera.getWorldDirection(new THREE.Vector3()),
      up: new THREE.Vector3(0, 1, 0).applyQuaternion(runtime.camera.quaternion), right: new THREE.Vector3(1, 0, 0).applyQuaternion(runtime.camera.quaternion) });
    if (!moving) return frames;
  }
}
const turnedOver = runtime => {
  const offset = runtime.camera.position.clone().sub(runtime.controls.target);
  return { position: [offset.x, -offset.y, -offset.z].map((value, axis) => value + TARGET[axis]), target: [...TARGET], up: runtime.camera.up.toArray() };
};
const degrees = (a, b) => THREE.MathUtils.radToDeg(a.angleTo(b));
// The most a half turn eased over the move's 280 ms turns in one frame at 60 a second: the ease's steepest
// (three times its mean) is 180° × 3 / 16.8 frames, about 32°. A jump is a half turn, or a quarter, in one.
const MOST_PER_FRAME = 40;
/** The move is a turn: the eye at its distance, the view and the screen's up turning each frame, never jumping. */
function assertTurns(frames, label) {
  const target = new THREE.Vector3(...TARGET);
  for (const frame of frames) assert.ok(Math.abs(frame.eye.distanceTo(target) - 150) < 1e-6, `${label}: the eye keeps its distance`);
  for (let index = 1; index < frames.length; index += 1) {
    assert.ok(degrees(frames[index - 1].look, frames[index].look) < MOST_PER_FRAME, `${label}: the view turns, frame ${index}`);
    assert.ok(degrees(frames[index - 1].up, frames[index].up) < MOST_PER_FRAME, `${label}: the screen's up turns with it, frame ${index}`);
  }
}

test("Flip from straight above turns the camera over about its target, the screen's up kept, and lands on the camera turned over", () => {
  // Straight above as the view cube's top face and a double-click's Look at leave it: a hair toward the front.
  const runtime = runtimeAt(viewPlaneCameraBasis({ direction: [0, 0, 1], up: [0, 1, 0] }, WORLD_UP).direction);
  const start = { up: new THREE.Vector3(0, 1, 0).applyQuaternion(runtime.camera.quaternion), right: new THREE.Vector3(1, 0, 0).applyQuaternion(runtime.camera.quaternion) };
  const to = turnedOver(runtime);
  const frames = framesOf(runtime, to);
  assertTurns(frames, 'at the pole');
  // A half turn about the screen's up, the eye going the screen's right: the screen's up the same throughout,
  // the board seen from below at the end mirrored left to right, as the 2D view's back is.
  const middle = frames[Math.floor(frames.length / 2)];
  assert.ok(middle.eye.clone().sub(runtime.controls.target).dot(start.right) > 140, 'half way, the eye is at the screen\'s right');
  for (const frame of frames) assert.ok(frame.up.dot(start.up) > 0.999, 'the screen\'s up never moves');
  const end = frames.at(-1);
  assert.deepEqual(runtime.camera.position.toArray().map(value => Math.round(value * 1e6) / 1e6), to.position.map(value => Math.round(value * 1e6) / 1e6));
  assert.deepEqual(runtime.camera.up.toArray(), [...WORLD_UP], 'it ends on the world\'s up, which the orbit turns about');
  assert.ok(end.right.dot(start.right) < -0.999, 'mirrored left to right');
});

test('near the pole, and from any side of it, the turn is the same: no frame jumps, and its way is the pole\'s on its side', () => {
  const pole = framesOf(runtimeAt(viewPlaneCameraBasis({ direction: [0, 0, 1], up: [0, 1, 0] }, WORLD_UP).direction), turnedOver(runtimeAt([0, -1e-4, 1])));
  for (const [x, y] of [[1e-6, -1e-4], [0.02, -0.03], [0.09, -0.07], [-0.09, 0.05], [0.3, -0.2]]) {
    const runtime = runtimeAt(new THREE.Vector3(x, y, 1).normalize().toArray());
    const frames = framesOf(runtime, turnedOver(runtime));
    assertTurns(frames, `off the pole by ${x}, ${y}`);
    // Leaning to the right of the pole, the way is the pole's own: half way the eye is where the pole's is, as near as it leans.
    if (x > 0 && Math.hypot(x, y) < 0.05) {
      const half = frames[Math.floor(frames.length / 2)].eye, poleHalf = pole[Math.floor(pole.length / 2)].eye;
      assert.ok(half.distanceTo(poleHalf) < 150 * Math.hypot(x, y) * 3, `half way, beside the pole's turn: ${half.distanceTo(poleHalf)}`);
    }
  }
});

test("a camera that comes up from under the board to Home's tilt from below stays under it all the way", () => {
  // Entered in 3D from a board's bottom: head on from below (looking up, the 2D view's up), easing to Home turned over.
  const runtime = runtimeAt([0, 0, -1], 150, [0, 1, 0]);
  const home = new THREE.Vector3(2.1, -1.65, 1.08).normalize();
  const below = [home.x, -home.y, -home.z];
  const frames = framesOf(runtime, { position: below.map((value, axis) => TARGET[axis] + value * 150), target: [...TARGET], up: [...WORLD_UP] });
  assertTurns(frames, 'from below');
  for (const frame of frames) assert.ok(frame.look.z > 0, 'the camera looks up at the board the whole way');
});

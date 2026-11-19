import { afterEach, expect, it } from 'vitest';
import { PerspectiveCamera, Vector3 } from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { guardedOrbitControls } from './orbitControlsPointers.js';
import { turntableOrbitControls } from './turntable.js';

// The orbit as the viewer builds it (`useViewerRuntime.js`), driven by real pointer events: a
// turntable that goes over the top. jsdom has PointerEvent but no pointer capture.
if (!HTMLElement.prototype.setPointerCapture) {
  HTMLElement.prototype.setPointerCapture = () => {};
  HTMLElement.prototype.releasePointerCapture = () => {};
}

const Turntable = turntableOrbitControls(guardedOrbitControls(OrbitControls));
const mounted: InstanceType<typeof OrbitControls>[] = [];

/** A camera at `eye`, looking at the origin with the world's z up, under `Controls`; the canvas is 400px tall. */
function mount(eye: number[], { Controls = Turntable }: { Controls?: typeof OrbitControls } = {}) {
  const canvas = document.createElement('canvas');
  Object.defineProperty(canvas, 'clientWidth', { value: 400 });
  Object.defineProperty(canvas, 'clientHeight', { value: 400 });
  document.body.appendChild(canvas);
  const camera = new PerspectiveCamera(45, 1, 0.1, 1000);
  camera.up.set(0, 0, 1);
  camera.position.set(eye[0], eye[1], eye[2]);
  camera.lookAt(0, 0, 0);
  const controls = new Controls(camera, canvas);
  mounted.push(controls);
  return { canvas, camera, controls };
}

function pointer(target: EventTarget, type: string, pointerId: number, x: number, y: number) {
  target.dispatchEvent(new PointerEvent(type, {
    bubbles: true, cancelable: true, pointerId, pointerType: 'mouse', button: 0, buttons: type === 'pointerup' ? 0 : 1, clientX: x, clientY: y,
  }));
}

/** The camera's screen axes in the world, as drawn. */
const axes = (camera: PerspectiveCamera) => ({
  right: new Vector3(1, 0, 0).applyQuaternion(camera.quaternion),
  up: new Vector3(0, 1, 0).applyQuaternion(camera.quaternion),
  back: camera.position.clone().normalize(),
});

afterEach(() => {
  for (const controls of mounted.splice(0)) controls.dispose();
  document.body.innerHTML = '';
});

it('a vertical drag goes over the top and on, the view coming round upside down and never rolled', () => {
  const { canvas, camera } = mount([0, -10, 5]);
  const distance = camera.position.length();
  let highest = -1;
  pointer(canvas, 'pointerdown', 1, 200, 100);
  // Down 150px: 135° toward the camera's up, from 27° above the horizon, over the top.
  for (let y = 110; y <= 250; y += 10) {
    pointer(canvas, 'pointermove', 1, 200, y);
    const { right, back } = axes(camera);
    highest = Math.max(highest, back.z);
    expect(Math.abs(right.z), 'the right stays level: no roll').toBeLessThan(1e-9);
    expect(camera.position.length()).toBeCloseTo(distance, 9);
  }
  pointer(document, 'pointerup', 1, 200, 250);
  const { up, back } = axes(camera);
  expect(highest, 'it passed straight over the top').toBeGreaterThan(0.99);
  expect(back.y, 'it is on the far side now').toBeGreaterThan(0.5);
  expect(up.z, 'upside down: its up points down the world').toBeLessThan(-0.5);
  expect(camera.up.dot(up), 'camera.up is the camera\'s own up, not the world\'s').toBeCloseTo(1, 9);
});

it('a sideways drag holds its sense for the whole gesture, over a pole too; one begun upside down turns the other way', () => {
  const { canvas, camera } = mount([0, -10, 5]);
  // A move to the right: how far the camera turned about the world's z (positive anticlockwise from
  // above), and whether it went to the screen's left, so the model's near side followed the cursor.
  const sideways = (pointerId: number, from: number, y: number) => {
    const before = camera.position.clone(), { right } = axes(camera);
    pointer(canvas, 'pointermove', pointerId, from + 10, y);
    const turn = Math.atan2(camera.position.y, camera.position.x) - Math.atan2(before.y, before.x);
    return { turn: Math.atan2(Math.sin(turn), Math.cos(turn)), followsCursor: camera.position.clone().sub(before).dot(right) < 0 };
  };
  pointer(canvas, 'pointerdown', 1, 200, 100);
  const upright = sideways(1, 200, 100);
  expect(upright.turn).toBeLessThan(0);
  expect(upright.followsCursor).toBe(true);
  pointer(canvas, 'pointermove', 1, 210, 230);
  expect(axes(camera).up.z, 'the same drag took the view over the top').toBeLessThan(0);
  const held = sideways(1, 210, 230);
  expect(held.turn, 'the sense the drag began with, held').toBeLessThan(0);
  pointer(document, 'pointerup', 1, 220, 230);
  // The next drag begins upside down: the other way about the world, the near side following the cursor.
  pointer(canvas, 'pointerdown', 2, 200, 200);
  const reversed = sideways(2, 200, 200);
  expect(reversed.turn).toBeGreaterThan(0);
  expect(reversed.followsCursor).toBe(true);
  pointer(document, 'pointerup', 2, 210, 200);
});

it('away from the poles a drag turns exactly as three\'s OrbitControls did, damping and all', () => {
  const ours = mount([4, -10, 5]), theirs = mount([4, -10, 5], { Controls: guardedOrbitControls(OrbitControls) });
  for (const { controls } of [ours, theirs]) { controls.enableDamping = true; controls.dampingFactor = 0.14; }
  for (const { canvas, controls } of [ours, theirs]) {
    pointer(canvas, 'pointerdown', 1, 200, 200);
    for (let step = 1; step <= 6; step += 1) pointer(canvas, 'pointermove', 1, 200 + step * 7, 200 + step * 3);
    pointer(document, 'pointerup', 1, 242, 218);
    for (let frame = 0; frame < 30; frame += 1) controls.update();
  }
  expect(ours.camera.position.distanceTo(theirs.camera.position)).toBeLessThan(1e-9);
  // Its axes, not `quaternion.angleTo`: that is 2·acos(dot), which reads 3e-8 for a dot one ulp under 1.
  const [a, b] = [axes(ours.camera), axes(theirs.camera)];
  expect(Math.max(a.right.distanceTo(b.right), a.up.distanceTo(b.up))).toBeLessThan(1e-9);
});

it('a view straight down stays exactly straight down through the controls\' every update', () => {
  // As the viewer has it: the controls made under the world's z, then the top view landed (+Y up the screen).
  const { camera, controls } = mount([0, -10, 5]);
  camera.position.set(0, 0, 10);
  camera.up.set(0, 1, 0);
  camera.lookAt(0, 0, 0);
  for (let frame = 0; frame < 3; frame += 1) controls.update();
  expect(Math.hypot(camera.position.x, camera.position.y)).toBeLessThan(1e-12);
  expect(axes(camera).up.y).toBeCloseTo(1, 12);
});

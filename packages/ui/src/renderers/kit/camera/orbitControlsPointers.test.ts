import { afterEach, expect, it } from 'vitest';
import { PerspectiveCamera } from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { guardedOrbitControls } from './orbitControlsPointers.js';

// jsdom has PointerEvent but no pointer capture; OrbitControls calls both on the canvas.
if (!HTMLElement.prototype.setPointerCapture) {
  HTMLElement.prototype.setPointerCapture = () => {};
  HTMLElement.prototype.releasePointerCapture = () => {};
}

const ViewerOrbitControls = guardedOrbitControls(OrbitControls);
let controls: InstanceType<typeof OrbitControls> | null = null;

// A listener's exception never reaches dispatchEvent's caller: the page reports it on window, as
// the viewer's error tracking saw it. Record those instead of letting them escape the test.
const listenerErrors: unknown[] = [];
const recordError = (event: ErrorEvent) => { listenerErrors.push(event.error); event.preventDefault(); };
window.addEventListener('error', recordError);

function mount() {
  const canvas = document.createElement('canvas');
  // jsdom lays nothing out; rotation divides the drag by the canvas height.
  Object.defineProperty(canvas, 'clientWidth', { value: 400 });
  Object.defineProperty(canvas, 'clientHeight', { value: 400 });
  document.body.appendChild(canvas);
  const camera = new PerspectiveCamera(45, 1, 0.1, 1000);
  camera.position.set(0, 0, 10);
  controls = new ViewerOrbitControls(camera, canvas);
  return { canvas, camera, controls };
}

function pointer(target: EventTarget, type: string, pointerId: number, pointerType: string, x = 100, y = 100) {
  target.dispatchEvent(new PointerEvent(type, {
    bubbles: true, cancelable: true, pointerId, pointerType, button: 0, buttons: type === 'pointerup' ? 0 : 1,
    clientX: x, clientY: y,
  }));
}

afterEach(() => {
  const escaped = listenerErrors.splice(0);
  controls?.dispose();
  controls = null;
  document.body.innerHTML = '';
  expect(escaped).toEqual([]);
});

// A Windows pen or touch laptop: a finger rests on the model, the pen lands beside it and the
// finger lifts. Only touch pointers get a tracked position, so the pen left alone in the
// controls' pointer list has none, and three's pointerup read `position.x` off undefined.
it('a pen left alone after a touch lifts ends the gesture instead of throwing', () => {
  const { canvas, controls } = mount();
  pointer(canvas, 'pointerdown', 2, 'touch');
  pointer(canvas, 'pointerdown', 1, 'pen');
  pointer(document, 'pointerup', 2, 'touch');
  expect(listenerErrors).toEqual([]);
  expect(controls.state).toBe(-1);
  pointer(canvas, 'pointermove', 1, 'pen', 140, 100);
  pointer(document, 'pointerup', 1, 'pen');
  // A fresh press still orbits.
  pointer(canvas, 'pointerdown', 3, 'mouse');
  expect(controls.state).toBe(0);
  pointer(document, 'pointerup', 3, 'mouse');
  expect(controls.state).toBe(-1);
});

// The pointerup listener sits on the document, so another pointer's lift anywhere on the page
// reaches it mid-drag: a finger tapping a toolbar while the mouse orbits.
it('another pointer lifting elsewhere leaves a mouse orbit running', () => {
  const { canvas, camera } = mount();
  pointer(canvas, 'pointerdown', 1, 'mouse');
  pointer(document, 'pointerup', 7, 'touch');
  expect(listenerErrors).toEqual([]);
  expect(controls!.state).toBe(0);
  const before = camera.position.clone();
  pointer(canvas, 'pointermove', 1, 'mouse', 160, 100);
  controls!.update();
  expect(camera.position.distanceTo(before)).toBeGreaterThan(0.01);
  pointer(document, 'pointerup', 1, 'mouse');
  expect(controls!.state).toBe(-1);
});

it('two fingers down, one lifted, still rotates with the other', () => {
  const { canvas, camera, controls } = mount();
  pointer(canvas, 'pointerdown', 1, 'touch', 100, 100);
  pointer(canvas, 'pointerdown', 2, 'touch', 200, 100);
  expect(controls.state).toBe(5); // TOUCH_DOLLY_PAN
  pointer(document, 'pointerup', 2, 'touch', 200, 100);
  expect(controls.state).toBe(3); // TOUCH_ROTATE
  const before = camera.position.clone();
  pointer(canvas, 'pointermove', 1, 'touch', 160, 100);
  controls.update();
  expect(camera.position.distanceTo(before)).toBeGreaterThan(0.01);
  pointer(document, 'pointerup', 1, 'touch', 160, 100);
  expect(controls.state).toBe(-1);
});

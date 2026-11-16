import assert from 'node:assert/strict';
import test from 'node:test';
import { PerspectiveCamera } from 'three';
import { measureSelectHandlers, measurementsInBox } from './measureSelection.js';

// A canvas 800 x 600 at (100, 50) on the page, looking down -z at the origin: two measurements, one
// along x at the middle of the view, one far up the screen.
const camera = new PerspectiveCamera(60, 800 / 600, 0.1, 100);
camera.position.set(0, 0, 5);
camera.lookAt(0, 0, 0);
camera.updateMatrixWorld(true);
camera.updateProjectionMatrix();
const runtime = { camera, renderer: { domElement: { getBoundingClientRect: () => ({ left: 100, top: 50, width: 800, height: 600 }) } } };
const taken = (id, a, b) => ({ id, pickA: { point: a }, pickB: { point: b }, measurement: null });
const measurements = [taken('across', [-1, 0, 0], [1, 0, 0]), taken('above', [-1, 1.8, 0], [1, 1.8, 0])];
// The view's middle on the page, where 'across' is drawn.
const middle = { x: 100 + 400, y: 50 + 300 };
const around = ({ x, y }, half) => ({ left: x - half, top: y - half, right: x + half, bottom: y + half });

test('a box takes the measurements whose drawn dimension it touches, in the page\'s pixels, and nothing over empty space', () => {
  // Across 'across''s dimension line, which is drawn just off its ends' line.
  assert.deepEqual(measurementsInBox(measurements, runtime, around(middle, 40)), ['across']);
  assert.deepEqual(measurementsInBox(measurements, runtime, { left: 0, top: 0, right: 2000, bottom: 2000 }), ['across', 'above']);
  assert.deepEqual(measurementsInBox(measurements, runtime, around({ x: middle.x, y: middle.y + 150 }, 20)), []);
  assert.deepEqual(measurementsInBox([], runtime, around(middle, 40)), []);
  assert.deepEqual(measurementsInBox(measurements, { renderer: runtime.renderer }, around(middle, 40)), []);
});

test('under Box select Shift adds the measurements a box takes, a plain box replaces them, and a filter without them takes none', () => {
  const session = (selected) => ({ measurements, selected, select(next) { this.selected = next; this.calls += 1; }, calls: 0 });
  const everything = { left: 0, top: 0, right: 2000, bottom: 2000 };
  const one = session(['above']);
  measureSelectHandlers(one, () => runtime, () => {}).box({ client: around(middle, 40), additive: true });
  assert.deepEqual(one.selected, ['above', 'across']);
  measureSelectHandlers(one, () => runtime, () => {}).box({ client: around(middle, 40), additive: false });
  assert.deepEqual(one.selected, ['across']);
  // The same selection again is not set again.
  const calls = one.calls;
  measureSelectHandlers(one, () => runtime, () => {}).box({ client: around(middle, 40), additive: true });
  assert.equal(one.calls, calls);
  // While Select's filter leaves measurements out, a plain box lets go of them; Shift keeps them.
  const left = session(['above']);
  measureSelectHandlers(left, () => runtime, () => {}, { picks: false }).box({ client: everything, additive: true });
  assert.deepEqual(left.selected, ['above']);
  measureSelectHandlers(left, () => runtime, () => {}, { picks: false }).box({ client: everything, additive: false });
  assert.deepEqual(left.selected, []);
});

import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';

import { applyDrawingViewLock, captureDrawingViewLock } from './drawingViewLock.js';

/** Draw mode: the model must stay under the ink for any pan or zoom made in the editor. */

const size = { width: 800, height: 600 };
function rig(kind, { width, height } = size) {
  const camera = kind === 'orthographic'
    ? new THREE.OrthographicCamera(-40 * width / height, 40 * width / height, 40, -40, 0.1, 5000)
    : new THREE.PerspectiveCamera(48, width / height, 0.1, 5000);
  camera.up.set(0, 0, 1);
  const controls = { target: new THREE.Vector3(12, -7, 5) };
  camera.position.copy(controls.target).add(new THREE.Vector3(2.1, -1.65, 1.08).multiplyScalar(90));
  camera.lookAt(controls.target);
  if (kind === 'orthographic') camera.zoom = 1.7;
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld();
  return { camera, controls, width, height };
}
const pixels = ({ camera, width, height }, point) => {
  camera.updateMatrixWorld();
  const ndc = point.clone().project(camera);
  return { x: (ndc.x + 1) * width / 2, y: (1 - ndc.y) * height / 2 };
};
// Points on the focal plane: the only ones a perspective pan can keep under the ink.
const focalPoints = view => {
  const right = new THREE.Vector3().setFromMatrixColumn(view.camera.matrixWorld, 0);
  const up = new THREE.Vector3().setFromMatrixColumn(view.camera.matrixWorld, 1);
  return [[0, 0], [14, 3], [-9, 11], [6, -13]].map(([x, y]) => view.controls.target.clone().addScaledVector(right, x).addScaledVector(up, y));
};
const close = (actual, expected, message) => {
  assert.ok(Math.abs(actual.x - expected.x) < 1e-3 && Math.abs(actual.y - expected.y) < 1e-3,
    `${message}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
};

for (const kind of ['orthographic', 'perspective']) {
  test(`${kind}: the model follows the editor's pan and zoom exactly, without changing the view direction`, () => {
    const view = rig(kind);
    const points = focalPoints(view), ink = points.map(point => pixels(view, point));
    const lock = captureDrawingViewLock(THREE, view);
    const orientation = view.camera.quaternion.clone();
    for (const viewport of [{ scrollX: 0, scrollY: 0, zoom: 1 }, { scrollX: 135, scrollY: -60, zoom: 1 },
      { scrollX: -220.5, scrollY: 48, zoom: 2.5 }, { scrollX: 900, scrollY: 700, zoom: 0.3 }]) {
      assert.equal(applyDrawingViewLock(THREE, lock, view, viewport), true);
      points.forEach((point, index) => close(pixels(view, point),
        { x: (ink[index].x + viewport.scrollX) * viewport.zoom, y: (ink[index].y + viewport.scrollY) * viewport.zoom }, JSON.stringify(viewport)));
      assert.ok(view.camera.quaternion.angleTo(orientation) < 1e-9, 'the view direction is locked');
    }
  });

  test(`${kind}: a long pan is answered from the lock, so returning the editor returns the camera`, () => {
    const view = rig(kind), lock = captureDrawingViewLock(THREE, view);
    const start = { position: view.camera.position.clone(), target: view.controls.target.clone(), zoom: view.camera.zoom };
    for (let step = 1; step <= 500; step += 1) applyDrawingViewLock(THREE, lock, view, { scrollX: step * 3.3, scrollY: -step * 1.7, zoom: 1 + (step % 7) / 5 });
    applyDrawingViewLock(THREE, lock, view, { scrollX: 0, scrollY: 0, zoom: 1 });
    assert.ok(view.camera.position.distanceTo(start.position) < 1e-6);
    assert.ok(view.controls.target.distanceTo(start.target) < 1e-6);
    assert.ok(Math.abs(view.camera.zoom - start.zoom) < 1e-9);
  });

  test(`${kind}: a viewport resize keeps the model under ink anchored to the editor's top-left`, () => {
    const view = rig(kind);
    const points = focalPoints(view), ink = points.map(point => pixels(view, point));
    const lock = captureDrawingViewLock(THREE, view);
    // The inspector opened: the viewport is narrower, and the runtime refit its projection.
    Object.assign(view, { width: 520, height: 600 });
    if (kind === 'orthographic') { view.camera.left = -40 * 520 / 600; view.camera.right = 40 * 520 / 600; } else view.camera.aspect = 520 / 600;
    view.camera.updateProjectionMatrix();
    applyDrawingViewLock(THREE, lock, view, { scrollX: 10, scrollY: 20, zoom: 1.5 });
    points.forEach((point, index) => close(pixels(view, point), { x: (ink[index].x + 10) * 1.5, y: (ink[index].y + 20) * 1.5 }, 'after resize'));
  });
}

for (const kind of ['orthographic', 'perspective']) {
  test(`${kind}: a lock taken mid-sketch answers the editor's current viewport with the current pose`, () => {
    const view = rig(kind), first = captureDrawingViewLock(THREE, view);
    const points = focalPoints(view), ink = points.map(point => pixels(view, point));
    const viewport = { scrollX: -140, scrollY: 75, zoom: 1.8 };
    applyDrawingViewLock(THREE, first, view, viewport);
    const pose = { position: view.camera.position.clone(), zoom: view.camera.zoom };
    // The viewport runtime was replaced: same camera pose, the editor still scrolled and zoomed.
    const relock = captureDrawingViewLock(THREE, view, viewport);
    applyDrawingViewLock(THREE, relock, view, viewport);
    assert.ok(view.camera.position.distanceTo(pose.position) < 1e-6);
    assert.ok(Math.abs(view.camera.zoom - pose.zoom) < 1e-9);
    const next = { scrollX: 30, scrollY: -20, zoom: 0.9 };
    applyDrawingViewLock(THREE, relock, view, next);
    points.forEach((point, index) => close(pixels(view, point), { x: (ink[index].x + next.scrollX) * next.zoom, y: (ink[index].y + next.scrollY) * next.zoom }, 'after relock'));
  });
}

test('refuses a viewport it cannot measure', () => {
  const view = rig('perspective');
  assert.equal(captureDrawingViewLock(THREE, { ...view, width: 0 }), null);
  const lock = captureDrawingViewLock(THREE, view);
  assert.equal(applyDrawingViewLock(THREE, lock, view, { scrollX: 0, scrollY: 0, zoom: 0 }), false);
  assert.equal(applyDrawingViewLock(THREE, null, view, { scrollX: 0, scrollY: 0, zoom: 1 }), false);
});

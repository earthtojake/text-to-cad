import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';
import { interactiveCameraFrameForBounds, interactiveViewportFitScale, INTERACTIVE_CAMERA_FIT_PADDING } from './viewportCameraFit.js';

function frameBounds(bounds, aspect, orthographic) {
  const camera = orthographic ? new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 10000) : new THREE.PerspectiveCamera(48, aspect, 0.01, 10000);
  camera.position.set(2.1, -1.65, 1.08);
  camera.up.set(0, 0, 1);
  const controls = { target: new THREE.Vector3() };
  const frame = interactiveCameraFrameForBounds(THREE, { camera, controls, bounds, frameAspect: aspect });
  camera.position.copy(frame.position); camera.up.copy(frame.up); camera.lookAt(frame.target);
  if (orthographic) {
    camera.top = frame.halfHeight; camera.bottom = -frame.halfHeight;
    camera.left = -frame.halfHeight * aspect; camera.right = frame.halfHeight * aspect;
  }
  camera.updateProjectionMatrix(); camera.updateMatrixWorld();
  const projected = [];
  for (const x of [bounds.min[0], bounds.max[0]]) for (const y of [bounds.min[1], bounds.max[1]]) for (const z of [bounds.min[2], bounds.max[2]]) {
    projected.push(new THREE.Vector3(x, y, z).project(camera));
  }
  return { camera, frame, projected };
}

for (const orthographic of [false, true]) {
  test(`${orthographic ? 'orthographic' : 'perspective'} fits tall, wide and flat bounds to the limiting viewport dimension`, () => {
    for (const size of [[200, 10, 4], [10, 12, 180], [120, 90, 0], [20, 20, 20]]) {
      for (const aspect of [0.4, 1, 2.8]) {
        const bounds = { min: [14, -37, 53], max: size.map((n, i) => n + [14, -37, 53][i]) };
        const { projected } = frameBounds(bounds, aspect, orthographic);
        const occupancy = Math.max(...projected.flatMap(point => [Math.abs(point.x), Math.abs(point.y)]));
        assert.ok(Math.abs(occupancy - 1 / INTERACTIVE_CAMERA_FIT_PADDING) < 1e-8, `${size} at ${aspect}: ${occupancy}`);
        assert.ok(projected.every(point => point.z >= -1 && point.z <= 1), 'all corners remain in front of the camera');
      }
    }
  });
}

test('fit planning preserves saved camera position, target and manual zoom', () => {
  const camera = new THREE.PerspectiveCamera(38, 2, 0.01, 10000);
  camera.position.set(48, -82, 14); camera.up.set(0, 0, 1); camera.zoom = 2.5;
  const controls = { target: new THREE.Vector3(2, 4, 6) };
  const before = [camera.position.toArray(), camera.up.toArray(), camera.zoom, controls.target.toArray()];
  const frame = interactiveCameraFrameForBounds(THREE, { camera, controls, bounds: { min: [0, 0, 0], max: [10, 20, 30] } });
  assert.deepEqual([camera.position.toArray(), camera.up.toArray(), camera.zoom, controls.target.toArray()], before);
  assert.equal(frame.zoom, 1, 'the explicit fit plan resets zoom only when the caller applies it');
});

test('photographic fits use the final lens and reset independently of an earlier manual pose', () => {
  const camera = new THREE.PerspectiveCamera(48, 1034 / 828, 0.01, 2000);
  camera.up.set(0, 0, 1);
  const controls = { target: new THREE.Vector3(42, 0, 2) };
  const bounds = { min: [39, -3, -5], max: [45, 3, 9] };
  const options = { camera, controls, bounds, viewDirection: [2.1, -1.65, 1.08], viewUp: [0, 0, 1] };
  const oldLensFrame = interactiveCameraFrameForBounds(THREE, options);
  const oldSlope = Math.tan(camera.fov * Math.PI / 360);
  camera.setFocalLength(50);
  const fitted = interactiveCameraFrameForBounds(THREE, options);
  const scaledOldDistance = oldLensFrame.distance * oldSlope / Math.tan(camera.fov * Math.PI / 360);
  assert.ok(Math.abs(scaledOldDistance - fitted.distance) > 0.1,
    'projected depth means fitting before setting the lens cannot be corrected by scaling the whole distance');
  camera.position.set(34.58, -11.75, 19.55); camera.zoom = 2.936;
  controls.target.set(40.58, 0.33, 2);
  const reset = interactiveCameraFrameForBounds(THREE, options);
  assert.deepEqual(reset.position.toArray(), fitted.position.toArray());
  assert.deepEqual(reset.target.toArray(), fitted.target.toArray());
  assert.equal(reset.zoom, 1);
});

test('resizing uses fitted shape and orientation; manual orbit does not redefine its baseline', () => {
  const bounds = { min: [-100, -5, -2], max: [100, 5, 2] };
  const { camera, frame } = frameBounds(bounds, 2.8, true);
  const framing = { bounds, direction: frame.direction.toArray(), up: frame.up.toArray() };
  const wide = interactiveViewportFitScale(THREE, { camera, framing, aspect: 2.8 });
  const narrow = interactiveViewportFitScale(THREE, { camera, framing, aspect: 0.4 });
  assert.ok(narrow > wide);
  camera.position.set(10, 100, 300);
  assert.equal(interactiveViewportFitScale(THREE, { camera, framing, aspect: 0.4 }), narrow);
  assert.ok(Math.abs((narrow / wide) * (wide / narrow) - 1) < 1e-12);
});

test('reset and resize fit against the model near floor, independent of a distant Render clipping plane', () => {
  const camera = new THREE.PerspectiveCamera(38, 1.5, 0.01, 5000);
  const bounds = { min: [-3, -3, -7], max: [3, 3, 7] };
  const options = { camera, controls: { target: new THREE.Vector3() }, bounds,
    viewDirection: [2.1, -1.65, 1.08], viewUp: [0, 0, 1], nearClip: 0.01 };
  const fitted = interactiveCameraFrameForBounds(THREE, options);
  const framing = { bounds, direction: fitted.direction.toArray(), up: fitted.up.toArray(), nearClip: 0.01 };
  const beforeResize = interactiveViewportFitScale(THREE, { camera, framing, aspect: 0.4 });
  camera.near = 1000; camera.position.set(2000, -2000, 1000);
  camera.updateProjectionMatrix();
  const reset = interactiveCameraFrameForBounds(THREE, options);
  assert.deepEqual(reset.position.toArray(), fitted.position.toArray(), 'Reset is independent of the previous zoom');
  assert.equal(interactiveViewportFitScale(THREE, { camera, framing, aspect: 0.4 }), beforeResize,
    'a viewport resize measures the same framing baseline');
  const callerManagedClip = interactiveCameraFrameForBounds(THREE, { ...options, nearClip: undefined });
  assert.ok(callerManagedClip.distance > camera.near, 'standalone callers retain safety against their configured near plane');
});

test('degenerate point bounds and axis-aligned view have finite fit plans', () => {
  const camera = new THREE.PerspectiveCamera(48, 1, 0.01, 1000);
  camera.position.set(0, 0, 100); camera.up.set(0, 0, 1);
  const frame = interactiveCameraFrameForBounds(THREE, {
    camera, controls: { target: new THREE.Vector3() }, bounds: { min: [1, 2, 3], max: [1, 2, 3] }, minRadius: 1,
  });
  assert.ok([...frame.position.toArray(), frame.distance, frame.halfHeight].every(Number.isFinite));
  assert.ok(frame.distance > 0 && frame.halfHeight > 0);
});

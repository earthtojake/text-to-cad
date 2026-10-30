import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';
import { interactiveCameraFrameForBounds, interactiveFitPadding, interactiveViewportFitScale } from './viewportCameraFit.js';

function frameBounds(bounds, aspect, orthographic, padding = undefined, insetLeft = 0, insetBottom = 0) {
  const camera = orthographic ? new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 10000) : new THREE.PerspectiveCamera(48, aspect, 0.01, 10000);
  camera.position.set(2.1, -1.65, 1.08);
  camera.up.set(0, 0, 1);
  const controls = { target: new THREE.Vector3() };
  const frame = interactiveCameraFrameForBounds(THREE, { camera, controls, bounds, frameAspect: aspect, padding, insetLeft, insetBottom });
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

// The share of the viewport the fitted box fills, across and down (NDC: 1 is the edge).
function occupancy(projected) {
  return { across: Math.max(...projected.map(point => Math.abs(point.x))), down: Math.max(...projected.map(point => Math.abs(point.y))) };
}
const near = (actual, expected) => Math.abs(actual - expected) < 1e-8;

// The owner's report: "on wide screens the models appear very large and tight to the top/bottom
// of the screen … on thin screens like side panes and phones the default zoom level is great as-is".
// So a square or narrower viewport keeps 1.1 on both axes, and 16:9 and wider leaves 1.25 down: a
// model whose height limits the fit fills 80% of it. Across, it is 1.1 at every aspect.
const PADDING_DOWN = { 0.4: 1.1, 1: 1.1, [16 / 9]: 1.25, 2.8: 1.25 };
for (const orthographic of [false, true]) {
  test(`${orthographic ? 'orthographic' : 'perspective'} fits tall, wide and flat bounds to the limiting viewport dimension, with room above and below on a wide viewport`, () => {
    for (const size of [[200, 10, 4], [10, 12, 180], [120, 90, 0], [20, 20, 20]]) {
      for (const aspect of [0.4, 1, 16 / 9, 2.8]) {
        const bounds = { min: [14, -37, 53], max: size.map((n, i) => n + [14, -37, 53][i]) };
        const { projected } = frameBounds(bounds, aspect, orthographic);
        const { across, down } = occupancy(projected);
        // The limiting axis meets its padding exactly; the other stays inside its own.
        assert.ok(near(Math.max(across * 1.1, down * PADDING_DOWN[aspect]), 1), `${size} at ${aspect}: ${across} across, ${down} down`);
        assert.ok(projected.every(point => point.z >= -1 && point.z <= 1), 'all corners remain in front of the camera');
      }
    }
    // A tall model is limited by its height: 80% of a wide view's, 91% of a square or a phone's, as before.
    const tall = { min: [0, 0, 0], max: [10, 12, 180] };
    for (const aspect of [16 / 9, 2.8]) assert.ok(near(occupancy(frameBounds(tall, aspect, orthographic).projected).down, 0.8), `${aspect}`);
    for (const aspect of [0.4, 1]) assert.ok(near(occupancy(frameBounds(tall, aspect, orthographic).projected).down, 1 / 1.1), `${aspect}`);
    // A long rod across the view is limited by its width on a 16:9 view, which keeps 1.1 there too.
    const rod = { min: [0, 0, 0], max: [10, 300, 10] };
    assert.ok(near(occupancy(frameBounds(rod, 16 / 9, orthographic).projected).across, 1 / 1.1));
  });
}

test('the padding eases from square to 16:9; an explicit padding (a library card) is both axes', () => {
  assert.deepEqual(interactiveFitPadding(0.4), { x: 1.1, y: 1.1 });
  assert.deepEqual(interactiveFitPadding(1), { x: 1.1, y: 1.1 });
  assert.deepEqual(interactiveFitPadding(Number.NaN), { x: 1.1, y: 1.1 }, 'an unknown aspect is square');
  assert.ok(near(interactiveFitPadding(1 + (16 / 9 - 1) / 2).y, 1.175), 'halfway to 16:9, halfway to 1.25');
  assert.ok(near(interactiveFitPadding(16 / 9).y, 1.25));
  assert.ok(near(interactiveFitPadding(3.5).y, 1.25), 'and no further');
  for (const orthographic of [false, true]) {
    const { across, down } = occupancy(frameBounds({ min: [0, 0, 0], max: [10, 12, 180] }, 2.8, orthographic, 1.08).projected);
    assert.ok(near(Math.max(across, down) * 1.08, 1), `${across} across, ${down} down`);
  }
});

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

for (const orthographic of [false, true]) {
  test(`original framing is invariant under live pose, reset, and saved camera (${orthographic ? 'ortho' : 'perspective'})`, async () => {
    const { originalModelCameraFrame } = await import('./viewportCameraFit.js');
    const camera = orthographic ? new THREE.OrthographicCamera(-20, 20, 20, -20) : new THREE.PerspectiveCamera(48, 1.5);
    const bounds = { min: [-10, -8, -4], max: [20, 30, 12] };
    const options = { camera, bounds, frameAspect: 1.5 };
    const before = originalModelCameraFrame(THREE, options);
    camera.position.set(4000, -5000, 1500); camera.zoom = 4; camera.near = 900;
    camera.up.set(1, 0, 0);
    const after = originalModelCameraFrame(THREE, options);
    assert.deepEqual(after.position.toArray(), before.position.toArray());
    assert.deepEqual(after.target.toArray(), before.target.toArray());
    assert.equal(after.halfHeight, before.halfHeight);
    assert.equal(after.distance, before.distance);
  });
}

// An FEA result's Study panel covers the viewport's left: the model is framed in the width it leaves,
// its box's centre at the middle of that, wholly right of the panel.
for (const orthographic of [false, true]) {
  test(`${orthographic ? 'orthographic' : 'perspective'} frames into the width right of chrome covering the left`, () => {
    const bounds = { min: [0, 0, 0], max: [200, 60, 40] };
    const covered = 0.15;
    const { projected, frame } = frameBounds(bounds, 1440 / 860, orthographic, undefined, covered);
    const xs = projected.map(point => point.x);
    // NDC runs -1..1 across: the panel's right edge is at -1 + 2 * 0.15.
    assert.ok(Math.min(...xs) > -1 + 2 * covered, `left edge ${Math.min(...xs)}`);
    assert.ok(Math.max(...xs) < 1, `right edge ${Math.max(...xs)}`);
    const { camera } = frameBounds(bounds, 1440 / 860, orthographic, undefined, covered);
    assert.ok(Math.abs(new THREE.Vector3(100, 30, 20).project(camera).x - covered) < 1e-6);
    // It orbits about a point beside the model's centre, as a pan leaves it; with nothing covered, about the centre.
    assert.ok(frame.target.distanceTo(new THREE.Vector3(100, 30, 20)) > 1);
    assert.ok(frameBounds(bounds, 1440 / 860, orthographic).frame.target.distanceTo(new THREE.Vector3(100, 30, 20)) < 1e-9);
  });
}

// A colour bar at the foot: the model is framed above it, its centre at the middle of what is left.
for (const orthographic of [false, true]) {
  test(`${orthographic ? 'orthographic' : 'perspective'} frames above chrome covering the foot, and right of the left`, () => {
    const bounds = { min: [0, 0, 0], max: [60, 60, 200] };
    const [left, below] = [0.12, 0.08];
    const { projected, camera } = frameBounds(bounds, 1440 / 860, orthographic, undefined, left, below);
    assert.ok(Math.min(...projected.map(point => point.y)) > -1 + 2 * below, 'above the bar');
    assert.ok(Math.max(...projected.map(point => point.y)) < 1, 'under the top');
    assert.ok(Math.min(...projected.map(point => point.x)) > -1 + 2 * left, 'right of the panel');
    const centre = new THREE.Vector3(30, 30, 100).project(camera);
    assert.ok(Math.abs(centre.y - below) < 1e-6 && Math.abs(centre.x - left) < 1e-6, `${centre.x}, ${centre.y}`);
  });
}

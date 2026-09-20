import assert from 'node:assert/strict';
import test from 'node:test';
import { createRenderSessionState, readRenderSessionCamera, resolveRenderCameraSnapshot, renderSessionStateEqual } from './renderSessionState.js';

const camera = { position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1], projection: 'perspective', focalLength: 75 };

test('camera persistence has no competing display authority', () => {
  assert.deepEqual(createRenderSessionState(), { cadCamera: null });
  assert.deepEqual(createRenderSessionState({ enabled: true, payload: { exposure: 1 }, cadCamera: camera,
    cadProjection: 'orthographic' }), { cadCamera: camera });
  assert.equal(renderSessionStateEqual({ cadCamera: camera, enabled: true }, { cadCamera: camera }), true);
});

test('enabled legacy sessions migrate their camera into the common viewport snapshot', () => {
  assert.deepEqual(createRenderSessionState({ enabled: true,
    cadCamera: { ...camera, position: [0, 0, 1] }, payload: { camera, quality: 'final' } }), { cadCamera: camera });
});

test('camera reads use the current viewport instead of an older stored snapshot', () => {
  const active = { ...camera, position: [90, 80, 70], zoom: 1.4, orthographicHalfHeight: 18 };
  assert.deepEqual(readRenderSessionCamera({ getPerspective: () => active }, camera), active);
  assert.deepEqual(readRenderSessionCamera(null, camera), camera);
});

test('camera presets and projection-only specs resolve against the model bounds', () => {
  const bounds = { min: [0, 0, 0], max: [20, 40, 10] };
  const front = resolveRenderCameraSnapshot({ preset: 'front', projection: 'perspective', focalLength: 80 }, bounds);
  assert.deepEqual(front.target, [10, 20, 5]);
  assert.ok(front.position[1] < 20);
  assert.equal(front.focalLength, 80);
  assert.equal(resolveRenderCameraSnapshot({ projection: 'orthographic' }, bounds).projection, 'orthographic');
});

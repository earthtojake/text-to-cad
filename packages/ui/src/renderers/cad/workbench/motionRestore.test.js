import test from 'node:test';
import assert from 'node:assert/strict';
import { restoreMotionAnimation, restoreMotionParameters } from './motionRestore.js';
const definition = { parameterMap: { x: { id: 'x', type: 'number', defaultValue: 2, min: -100, max: 100 } }, defaultParameterValues: { x: 2 } };
const clips = { turn: { id: 'turn', duration: 5, update() {} } };
test('legacy dual-owner sessions restore only the animation frame with authored parameters', () => {
  const animation = restoreMotionAnimation({ enabled: true, activeClipId: 'turn', elapsedSec: 3 }, clips);
  assert.equal(animation.elapsedSec, 3);
  assert.equal(animation.playing, false);
  assert.deepEqual(restoreMotionParameters(definition, { x: 50 }, animation), { x: 2 });
});
test('position-owned sessions cannot restore a stale playback clock', () => {
  const animation = restoreMotionAnimation({ enabled: false, activeClipId: 'turn', elapsedSec: 3 }, clips);
  assert.equal(animation.elapsedSec, 0);
  assert.deepEqual(restoreMotionParameters(definition, { x: 50 }, animation), { x: 50 });
});
test('independent sidecar completion order and missing blocks retain the same owner', () => {
  const stored = { enabled: true, activeClipId: 'turn', elapsedSec: 3 };
  assert.deepEqual(restoreMotionParameters(definition, { x: 50 }, stored),
    restoreMotionParameters(definition, { x: 50 }, restoreMotionAnimation(stored, clips)));
  assert.deepEqual(restoreMotionParameters(definition, { x: 50 }, null), { x: 50 });
  assert.deepEqual(restoreMotionParameters(null, { x: 50 }, stored), {});
});

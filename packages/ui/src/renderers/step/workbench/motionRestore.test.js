import test from 'node:test';
import assert from 'node:assert/strict';
import { restoreMotionAnimation, restoreMotionParameters } from './motionRestore.js';
const definition = { url: '/x.step.json', articulation: { schemaVersion: 2,
  controls: [{ id: 'x', label: 'x', unit: 'deg', min: -100, max: 100, default: 2 }],
  joints: [], carries: {}, handles: [], poses: {}, opening: { x: 2 } } };
const clips = { turn: { id: 'turn', duration: 5, tracks: [] } };
test('a routine that owns the pose keeps Position\'s values off the model, and a load never resumes it', () => {
  const animation = restoreMotionAnimation({ enabled: true, activeClipId: 'turn', elapsedSec: 3, playing: true, speed: 2 }, clips);
  assert.deepEqual([animation.elapsedSec, animation.playing, animation.speed, animation.activeClipId], [0, false, 2, 'turn']);
  assert.deepEqual(restoreMotionParameters(definition, { x: 50 }, animation), { x: 2 });
});
test('a pose owned by Position comes through, whatever the clock says', () => {
  const animation = restoreMotionAnimation({ enabled: false, activeClipId: 'turn', elapsedSec: 3 }, clips);
  assert.equal(animation.elapsedSec, 0);
  assert.deepEqual(restoreMotionParameters(definition, { x: 50 }, animation), { x: 50 });
  assert.deepEqual(restoreMotionParameters(definition, { x: 50 }, null), { x: 50 });
  assert.deepEqual(restoreMotionParameters(null, { x: 50 }, animation), {});
});
test('a clip the model no longer has leaves the routine unselected, at rest', () => {
  const animation = restoreMotionAnimation({ enabled: true, activeClipId: 'gone', elapsedSec: 3 }, clips);
  assert.deepEqual([animation.enabled, animation.playing, animation.elapsedSec], [false, false, 0]);
});

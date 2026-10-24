import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveSceneQuality } from '@text-to-cad/core/common/sceneSettings.js';
import { previewSceneQuality, previewViewScene } from './previewViewScene.js';

const scene = quality => ({
  quality: resolveSceneQuality(quality),
  display: { mode: 'shaded', clip: { enabled: true, axis: 'x', at: 4 }, exploded: { enabled: true, amount: 0.5 } },
  view: { lighting: { quality: 'preview' } }
});

test('Preview draws one quality tier up, capped at High', () => {
  assert.equal(previewSceneQuality(resolveSceneQuality('interactive')).id, 'standard');
  assert.equal(previewSceneQuality(resolveSceneQuality('standard')).id, 'high');
  assert.equal(previewSceneQuality(resolveSceneQuality('high')).id, 'high');
});

test('Preview suspends the tool effects but no Display setting', () => {
  const resolved = scene('interactive');
  const drawn = previewViewScene(resolved);
  assert.equal(drawn.display.mode, 'shaded');
  assert.equal(drawn.view, resolved.view);
  assert.equal(drawn.display.clip.enabled, false);
  assert.equal(drawn.display.exploded.enabled, false);
  // The settings themselves are untouched: the editor's view still draws them.
  assert.equal(resolved.display.clip.enabled, true);
});

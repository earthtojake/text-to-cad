import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveSceneQuality } from '@text-to-cad/core/common/sceneSettings.js';
import { VIEWER_RENDER_PROFILE, previewSceneQuality, renderProfileKeepsPixelRatio, sceneForRenderProfile } from './renderProfile.js';

const scene = quality => ({
  quality: resolveSceneQuality(quality),
  display: { mode: 'shaded', clip: { enabled: true, axis: 'x', amount: 0.4 }, exploded: { enabled: true, amount: 0.5 } },
  view: { lighting: { quality: 'preview' } }
});

test('the tools profile draws the scene exactly as its settings resolve it', () => {
  const resolved = scene('interactive');
  assert.equal(sceneForRenderProfile(resolved, VIEWER_RENDER_PROFILE.TOOLS), resolved);
  assert.equal(renderProfileKeepsPixelRatio(VIEWER_RENDER_PROFILE.TOOLS), false);
});

test('preview draws one quality tier up, capped at High, and keeps its pixel ratio while it orbits', () => {
  assert.equal(previewSceneQuality(resolveSceneQuality('interactive')).id, 'standard');
  assert.equal(previewSceneQuality(resolveSceneQuality('standard')).id, 'high');
  assert.equal(previewSceneQuality(resolveSceneQuality('high')).id, 'high');
  assert.equal(renderProfileKeepsPixelRatio(VIEWER_RENDER_PROFILE.PREVIEW), true);
});

test('preview suspends the tool effects but no Display setting', () => {
  const resolved = scene('interactive');
  const drawn = sceneForRenderProfile(resolved, VIEWER_RENDER_PROFILE.PREVIEW);
  assert.equal(drawn.display.mode, 'shaded');
  assert.equal(drawn.view, resolved.view);
  assert.equal(drawn.display.clip.enabled, false);
  assert.equal(drawn.display.exploded.enabled, false);
  // The settings themselves are untouched, for the tools view to come back to.
  assert.equal(resolved.display.clip.enabled, true);
});

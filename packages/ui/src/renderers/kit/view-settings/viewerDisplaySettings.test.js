import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeViewSettings, resetViewSettings, resolveViewSettings, viewSettingsAreCustom } from '@text-to-cad/core/common/viewSettings.js';
import { DISPLAY_MODE_OPTIONS } from './DisplayModeOptions.js';
import {
  cameraForViewSettings, mergeViewerDisplaySettings, previewDisplaySettings,
  viewerDisplaySettingsForCamera, viewerDisplaySettingsForMode
} from './viewerDisplaySettings.js';

test('the viewer offers the canonical presets in their intended order', () => {
  assert.deepEqual(DISPLAY_MODE_OPTIONS.map(({ value, label }) => [value, label]), [
    ['solid', 'Solid'], ['render', 'Render'], ['xray', 'X-ray'],
    ['hidden-line', 'Hidden line'], ['wireframe', 'Wireframe'], ['grid', 'Grid']
  ]);
});

test('live display patches merge groups without pinning defaults or losing tools', () => {
  const current = { mode: 'render', camera: { focalLength: 80 }, lighting: { exposure: 1, size: 2 },
    clip: { enabled: true, axis: 'y', at: 0.35 } };
  const next = mergeViewerDisplaySettings(current, { lighting: { exposure: 2 } });
  assert.deepEqual(next, { ...current, lighting: { exposure: 2, size: 2 } });
  assert.throws(() => mergeViewerDisplaySettings(current, { render: { exposure: 1 } }), /Unsupported/);
  assert.throws(() => normalizeViewSettings({ mode: 'shaded_edges' }), /mode/);
});

test('preset selection retains tools while Reset clears all View overrides', () => {
  const current = { mode: 'render', camera: { focalLength: 80 }, lighting: { exposure: 1 },
    clip: { enabled: true, axis: 'y', at: 0.35 }, exploded: { enabled: true, amount: 0.4 } };
  assert.deepEqual(resetViewSettings(current), { mode: 'render' });
  const next = viewerDisplaySettingsForMode(current, 'wireframe');
  assert.deepEqual(next, { mode: 'wireframe', clip: current.clip, exploded: current.exploded });
  assert.equal(viewSettingsAreCustom(next), false);
  assert.deepEqual(mergeViewerDisplaySettings(current, { mode: 'solid', edges: { enabled: false } }), {
    mode: 'solid', clip: current.clip, exploded: current.exploded, edges: { enabled: false }
  });
});

test('preset camera changes retain the actual camera position, target and zoom', () => {
  const camera = { position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1], zoom: 1.4,
    projection: 'orthographic', focalLength: 120, orthographicHalfHeight: 24 };
  for (const mode of ['solid', 'render', 'xray', 'hidden-line', 'wireframe', 'grid']) {
    const next = cameraForViewSettings(camera, { mode });
    const expected = resolveViewSettings({ mode }).camera;
    assert.deepEqual(next, { ...camera, projection: expected.projection, focalLength: expected.focalLength });
  }
  assert.equal(cameraForViewSettings(null, { mode: 'render' }), null);
});

test('the viewer Preview baseline is inherited without an override or Custom state', async () => {
  const { resolveViewSceneSettings } = await import('@text-to-cad/core/common/sceneSettings.js');
  const options = { lightingQuality: 'preview' };
  const scene = resolveViewSceneSettings({ display: { mode: 'render' }, ...options });
  assert.equal(scene.view.lighting.quality, 'preview');
  assert.equal(scene.quality.id, 'standard');
  assert.equal(viewSettingsAreCustom({ mode: 'render' }, options), false);
  assert.equal(viewSettingsAreCustom({ mode: 'render', lighting: { quality: 'preview' } }, options), false);
  assert.equal(viewSettingsAreCustom({ mode: 'render', lighting: { quality: 'final' } }, options), true);
});

test('camera commands activate explicit projection and lens while pose-only updates leave View unchanged', () => {
  const current = { mode: 'render', camera: { enabled: false }, clip: { enabled: true, axis: 'z', at: 0.2 } };
  const pose = { position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1], zoom: 1.4 };
  assert.deepEqual(viewerDisplaySettingsForCamera(current, pose), current);
  const next = viewerDisplaySettingsForCamera(current, { ...pose, projection: 'perspective', focalLength: 85 });
  assert.deepEqual(next, { ...current, camera: { enabled: true, projection: 'perspective', focalLength: 85 } });
  assert.equal(resolveViewSettings(next).camera.projection, 'perspective');
  assert.equal(resolveViewSettings(next).camera.focalLength, 85);
  assert.deepEqual(current.camera, { enabled: false });
  assert.throws(() => viewerDisplaySettingsForCamera(current, { ...pose, focalLength: 500 }), /focalLength/);
});

test('live clip patches place the plane in millimetres; a new axis without a place cuts through the middle', () => {
  const initial = { mode: 'solid', clip: { axis: 'x', at: 2 } };
  const moved = mergeViewerDisplaySettings(initial, { clip: { at: 4.5 } });
  assert.deepEqual(moved.clip, { enabled: true, axis: 'x', invert: false, at: 4.5 });
  assert.deepEqual(mergeViewerDisplaySettings(moved, { clip: { invert: true } }).clip,
    { enabled: true, axis: 'x', invert: true, at: 4.5 }, 'flipping never moves the plane');
  assert.deepEqual(mergeViewerDisplaySettings(moved, { clip: { axis: 'y' } }).clip, { enabled: true, axis: 'y', invert: false });
  assert.deepEqual(mergeViewerDisplaySettings(moved, { clip: { axis: 'y', at: -3 } }).clip,
    { enabled: true, axis: 'y', invert: false, at: -3 });
  assert.throws(() => mergeViewerDisplaySettings(moved, { clip: { offset: 0.5 } }), /Unsupported display\.clip fields: offset/);
});

test('presentation suspends model effects without mutating the saved settings', () => {
  const display = { mode: 'render', clip: { enabled: true, axis: 'y', at: 4 }, exploded: { enabled: true, amount: .7 } };
  const before = structuredClone(display);
  const preview = previewDisplaySettings(display);
  assert.equal(preview.clip.enabled, false);
  assert.equal(preview.exploded.enabled, false);
  assert.equal(preview.exploded.amount, 0);
  assert.equal(preview.mode, 'render');
  assert.deepEqual(display, before);
});

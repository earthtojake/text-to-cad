import assert from 'node:assert/strict';
import test from 'node:test';
import { resolveViewSettings } from '@text-to-cad/core/common/viewSettings.js';
import { DISPLAY_MODE_OPTIONS } from './DisplayModeOptions.js';
import {
  cameraForViewSettings, mergePreviewSettings, mergeViewerDisplaySettings, previewDisplaySettings,
  viewerDisplaySettingsForCamera
} from './viewerDisplaySettings.js';

test('the viewer offers the display modes in their intended order: Preview is no display mode, and Grid a switch', () => {
  assert.deepEqual(DISPLAY_MODE_OPTIONS.map(({ value, label }) => [value, label]), [
    ['solid', 'Solid'], ['shaded', 'Shaded'], ['parts', 'Parts'], ['xray', 'X-ray'], ['hidden-line', 'Hidden line'], ['wireframe', 'Wireframe']
  ]);
});

test('live patches merge only what they say and preserve the shared camera and tools', () => {
  const current = { mode: 'solid', camera: { focalLength: 80 }, clip: { enabled: true, axis: 'y', at: 0.35 } };
  assert.deepEqual(mergeViewerDisplaySettings(current, { mode: 'parts' }), { ...current, mode: 'parts' });
  assert.deepEqual(mergeViewerDisplaySettings(current, { grid: true }), { ...current, grid: true });
  assert.deepEqual(mergeViewerDisplaySettings({ ...current, grid: true }, { grid: false }), current, 'a grid switched off is left unsaid');
  assert.throws(() => mergeViewerDisplaySettings(current, { lighting: { exposure: 1 } }), /Unsupported/);
  assert.throws(() => mergeViewerDisplaySettings(current, { modes: { solid: { flat: true } } }), /Unsupported display fields: modes/);
  // Preview's settings merge group by group, field by field.
  const preview = mergePreviewSettings({ lighting: { exposure: 1, size: 2 } }, { lighting: { exposure: 2 }, floor: { finish: 'glossy' } });
  assert.deepEqual(preview, { lighting: { exposure: 2, size: 2 }, floor: { finish: 'glossy' } });
});

test('preset camera changes retain the actual camera position, target and zoom', () => {
  const camera = { position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1], zoom: 1.4,
    projection: 'orthographic', focalLength: 120, orthographicHalfHeight: 24 };
  for (const mode of ['solid', 'shaded', 'parts', 'xray', 'hidden-line', 'wireframe']) {
    const next = cameraForViewSettings(camera, { mode });
    const expected = resolveViewSettings({ mode }).camera;
    assert.deepEqual(next, { ...camera, projection: expected.projection, focalLength: expected.focalLength });
  }
  assert.equal(cameraForViewSettings(null, { mode: 'solid' }), null);
});

test('camera commands activate explicit projection and lens while pose-only updates leave View unchanged', () => {
  const current = { mode: 'xray', camera: { projection: 'orthographic' }, clip: { enabled: true, axis: 'z', at: 0.2 } };
  const pose = { position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1], zoom: 1.4 };
  assert.deepEqual(viewerDisplaySettingsForCamera(current, pose), current);
  const next = viewerDisplaySettingsForCamera(current, { ...pose, projection: 'perspective', focalLength: 85 });
  assert.deepEqual(next, { ...current, camera: { projection: 'perspective', focalLength: 85 } });
  assert.equal(resolveViewSettings(next).camera.projection, 'perspective');
  assert.equal(resolveViewSettings(next).camera.focalLength, 85);
  assert.deepEqual(current.camera, { projection: 'orthographic' });
  assert.throws(() => viewerDisplaySettingsForCamera(current, { ...pose, focalLength: 500 }), /focalLength/);
});

test('live clip patches place the plane in millimetres; a new axis without a place cuts through the middle', () => {
  const initial = { mode: 'solid', clip: { axis: 'x', at: 2 } };
  const moved = mergeViewerDisplaySettings(initial, { clip: { at: 4.5 } });
  assert.deepEqual(moved.clip, { enabled: true, axis: 'x', invert: false, partColors: true, at: 4.5 });
  assert.deepEqual(mergeViewerDisplaySettings(moved, { clip: { invert: true } }).clip,
    { enabled: true, axis: 'x', invert: true, partColors: true, at: 4.5 }, 'flipping never moves the plane');
  assert.deepEqual(mergeViewerDisplaySettings(moved, { clip: { axis: 'y' } }).clip, { enabled: true, axis: 'y', invert: false, partColors: true });
  assert.deepEqual(mergeViewerDisplaySettings(moved, { clip: { axis: 'y', at: -3 } }).clip,
    { enabled: true, axis: 'y', invert: false, partColors: true, at: -3 });
  assert.throws(() => mergeViewerDisplaySettings(moved, { clip: { offset: 0.5 } }), /Unsupported display\.clip fields: offset/);
});

test('presentation suspends model effects without mutating the saved settings', () => {
  const display = { mode: 'xray', clip: { enabled: true, axis: 'y', at: 4 }, exploded: { enabled: true, amount: .7 } };
  const before = structuredClone(display);
  const preview = previewDisplaySettings(display);
  assert.equal(preview.clip.enabled, false);
  assert.equal(preview.exploded.enabled, false);
  assert.equal(preview.exploded.amount, 0);
  assert.equal(preview.mode, 'xray');
  assert.deepEqual(display, before);
});

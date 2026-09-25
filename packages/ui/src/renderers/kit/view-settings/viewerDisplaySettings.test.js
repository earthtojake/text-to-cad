import assert from 'node:assert/strict';
import test from 'node:test';
import { resolveViewSettings, viewSettingsAreCustom } from '@hardcore/core/common/viewSettings.js';
import { DISPLAY_MODE_OPTIONS } from './DisplayModeOptions.js';
import {
  cameraForViewSettings, mergeViewerDisplaySettings, migrateViewerDisplaySettings, presentationDisplaySettings,
  normalizeViewerDisplaySettings, resetViewerDisplaySettings, viewerDisplaySettingsForCamera, viewerDisplaySettingsForMode
} from './viewerDisplaySettings.js';

test('the viewer offers the canonical presets in their intended order', () => {
  assert.deepEqual(DISPLAY_MODE_OPTIONS.map(({ value, label }) => [value, label]), [
    ['solid', 'Solid'], ['render', 'Render'], ['xray', 'X-ray'],
    ['hidden-line', 'Hidden line'], ['wireframe', 'Wireframe']
  ]);
});

test('live display patches merge groups without pinning defaults or losing tools', () => {
  const current = { mode: 'render', camera: { focalLength: 80 }, lighting: { exposure: 1, size: 2 },
    clip: { enabled: true, axis: 'y', offset: 0.35 } };
  const next = mergeViewerDisplaySettings(current, { lighting: { exposure: 2 } });
  assert.deepEqual(next, { ...current, lighting: { exposure: 2, size: 2 } });
  assert.throws(() => mergeViewerDisplaySettings(current, { render: { exposure: 1 } }), /Unsupported/);
  assert.throws(() => normalizeViewerDisplaySettings({ mode: 'shaded_edges' }), /mode/);
});

test('preset selection retains tools while Reset clears all View overrides', () => {
  const current = { mode: 'render', camera: { focalLength: 80 }, lighting: { exposure: 1 },
    clip: { enabled: true, axis: 'y', offset: 0.35 }, exploded: { enabled: true, amount: 0.4 } };
  assert.deepEqual(resetViewerDisplaySettings(current), { mode: 'render' });
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
  for (const mode of ['solid', 'render', 'xray', 'hidden-line', 'wireframe']) {
    const next = cameraForViewSettings(camera, { mode });
    const expected = resolveViewSettings({ mode }).camera;
    assert.deepEqual(next, { ...camera, projection: expected.projection, focalLength: expected.focalLength });
  }
  assert.equal(cameraForViewSettings(null, { mode: 'render' }), null);
});

test('only persisted sessions migrate old display and photographic settings', () => {
  const migrated = migrateViewerDisplaySettings({ mode: 'hidden_edges',
    guides: { grid: { enabled: false } }, partColor: { mode: 'by_part', colors: ['#123456'] },
    clip: { enabled: true, offset: 0.3 } }, {
    enabled: true, payload: { exposure: 1, quality: 'preview', lighting: { fill: 0.5 },
      backdrop: { ground: true, groundPlacement: 'lowest', transparent: true } },
    cadCamera: { projection: 'orthographic', focalLength: 85 }
  });
  assert.equal(migrated.mode, 'render');
  assert.deepEqual(migrated.camera, { projection: 'orthographic', focalLength: 85 });
  assert.deepEqual(migrated.lighting, { fill: 0.5, quality: 'preview', exposure: 1 });
  assert.deepEqual(migrated.background, { opacity: 0 });
  assert.deepEqual(migrated.floor, { enabled: true, placement: 'lowest' });
  assert.equal(migrated.surfaces.colorMode, 'by-part');
  assert.equal(migrated.grid.enabled, false);
  assert.equal(migrated.clip.offset, 0.3);
  assert.equal(migrateViewerDisplaySettings({ mode: 'shaded' }).mode, 'solid');
  assert.equal(migrateViewerDisplaySettings({ mode: 'hidden_edges' }).mode, 'xray');
});

test('the viewer Preview baseline is inherited without an override or Custom state', async () => {
  const { resolveViewSceneSettings } = await import('@hardcore/core/common/sceneSettings.js');
  const options = { lightingQuality: 'preview' };
  const scene = resolveViewSceneSettings({ display: { mode: 'render' }, ...options });
  assert.equal(scene.view.lighting.quality, 'preview');
  assert.equal(scene.quality.id, 'standard');
  assert.equal(viewSettingsAreCustom({ mode: 'render' }, options), false);
  assert.equal(viewSettingsAreCustom({ mode: 'render', lighting: { quality: 'preview' } }, options), false);
  assert.equal(viewSettingsAreCustom({ mode: 'render', lighting: { quality: 'final' } }, options), true);
});

test('camera commands activate explicit projection and lens while pose-only updates leave View unchanged', () => {
  const current = { mode: 'render', camera: { enabled: false }, clip: { enabled: true, axis: 'z', offset: 0.2 } };
  const pose = { position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1], zoom: 1.4 };
  assert.deepEqual(viewerDisplaySettingsForCamera(current, pose), current);
  const next = viewerDisplaySettingsForCamera(current, { ...pose, projection: 'perspective', focalLength: 85 });
  assert.deepEqual(next, { ...current, camera: { enabled: true, projection: 'perspective', focalLength: 85 } });
  assert.equal(resolveViewSettings(next).camera.projection, 'perspective');
  assert.equal(resolveViewSettings(next).camera.focalLength, 85);
  assert.deepEqual(current.camera, { enabled: false });
  assert.throws(() => viewerDisplaySettingsForCamera(current, { ...pose, focalLength: 500 }), /focalLength/);
});

test('persisted appearance survives corruption elsewhere and invalid appearance does not discard valid groups', () => {
  const recover = migrateViewerDisplaySettings({ mode: 'render', appearance: 'dark',
    surfaces: { color: 'broken', opacity: 0.4 }, camera: { focalLength: 85 }, unexpected: true });
  assert.deepEqual(recover, { mode: 'render', appearance: 'dark', surfaces: { opacity: 0.4 }, camera: { focalLength: 85 } });
  assert.deepEqual(migrateViewerDisplaySettings({ mode: 'solid', appearance: 'invalid', grid: { enabled: false } }),
    { mode: 'solid', grid: { enabled: false } });
  assert.equal(migrateViewerDisplaySettings({ mode: 'shaded_edges', appearance: 'dark' }).appearance, 'dark');
});

test('live clip scalar patches replace the active offset and retain the other axes', () => {
  const initial = { mode: 'solid', clip: { enabled: true, axis: 'x', offsets: { x: 0.2, y: 0.1 } } };
  const changed = mergeViewerDisplaySettings(initial, { clip: { offset: 0.4 } });
  assert.equal(changed.clip.offset, 0.4);
  assert.deepEqual(changed.clip.offsets, { x: 0.4, y: 0.1, z: 0 });
  const zero = mergeViewerDisplaySettings(changed, { clip: { axis: 'y', offset: 0 } });
  assert.equal(zero.clip.axis, 'y');
  assert.equal(zero.clip.offset, 0);
  assert.equal(zero.clip.enabled, false);
  assert.deepEqual(zero.clip.offsets, { x: 0.4, y: 0, z: 0 });
  const explicit = mergeViewerDisplaySettings(changed, { clip: { axis: 'y', offset: 0.3, offsets: { y: 0.7 } } });
  assert.equal(explicit.clip.offset, 0.7);
  assert.deepEqual(explicit.clip.offsets, { x: 0.4, y: 0.7, z: 0 });
});

test('presentation suspends model effects without mutating the saved settings', () => {
  const display = { mode: 'render', clip: { enabled: true, axis: 'y', offsets: { y: .4 } }, exploded: { enabled: true, amount: .7 } };
  const before = structuredClone(display);
  const preview = presentationDisplaySettings(display);
  assert.equal(preview.clip.enabled, false);
  assert.equal(preview.exploded.enabled, false);
  assert.equal(preview.exploded.amount, 0);
  assert.equal(preview.mode, 'render');
  assert.deepEqual(display, before);
});

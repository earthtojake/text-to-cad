import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import { parse } from '@babel/parser';
import traverseModule from '@babel/traverse';
import { clonePerspectiveSnapshot } from '@hardcore/core/lib/perspective.js';
import { cameraForViewSettings, viewerDisplaySettingsForCamera } from '../view-settings/viewerDisplaySettings.js';
import { createViewSettingsStore } from '../view-settings/viewSettingsStore.js';

// The live `setCamera` a host or an agent drives is the SHELL's, for every renderer on it. It
// is exercised here on its own, lifted out of the hook with its real collaborators, because
// what matters about it is ORDER: it must refuse bad input before it touches the viewport or
// the stored display, and a camera that names only a pose must inherit the projection and
// lens already configured rather than writing an override nobody asked for.

const traverse = traverseModule.default || traverseModule;
const source = fs.readFileSync(new URL('./useRendererShell.js', import.meta.url), 'utf8');
let cameraCommand;
traverse(parse(source, { sourceType: 'module', plugins: ['jsx'] }), {
  ObjectMethod(path) {
    if (path.node.key.name !== 'setCamera') return;
    assert.equal(cameraCommand, undefined, 'one live camera command');
    cameraCommand = Function('scope', 'camera', `with (scope) { return (function(camera) ${source.slice(path.node.body.start, path.node.body.end)})(camera); }`);
  }
});
assert.ok(cameraCommand, 'the shell exposes a live setCamera');

function harness(displaySettings) {
  const result = { applied: null, display: displaySettings, perspective: null, recorded: null };
  const viewSettingsStore = createViewSettingsStore(displaySettings);
  viewSettingsStore.subscribe(() => { result.display = viewSettingsStore.getSnapshot().display; });
  const scope = {
    viewSettingsStore, clonePerspectiveSnapshot, cameraForViewSettings, viewerDisplaySettingsForCamera,
    presenting: false, modelKey: 'part.step', sceneScaleMode: 'cad',
    scopeShellCamera: camera => camera,
    viewerRef: { current: { setPerspective(camera) { result.applied = camera; return true; } } },
    setViewerPerspective: camera => { result.perspective = camera; },
    handlePerspectiveChange: camera => { result.recorded = camera; }
  };
  return { result, apply: camera => cameraCommand(scope, camera) };
}
const pose = { position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1], zoom: 1.4 };

test('setCamera turns its controls on and applies the projection and lens it saves in display', () => {
  const current = { mode: 'render', camera: { enabled: false }, clip: { enabled: true, offset: 0.3 } };
  const view = harness(current);
  view.apply({ ...pose, projection: 'perspective', focalLength: 85 });
  assert.deepEqual(view.result.applied, { ...pose, projection: 'perspective', focalLength: 85 });
  assert.deepEqual(view.result.display, { ...current, camera: { enabled: true, projection: 'perspective', focalLength: 85 } });
  assert.deepEqual(view.result.perspective, view.result.applied, 'the viewport shows what was applied');
  assert.deepEqual(view.result.recorded, view.result.applied, 'and the file records it');
});

test('a pose-only setCamera inherits the configured projection and lens, and writes no display override', () => {
  const current = { mode: 'render' };
  const view = harness(current);
  view.apply(pose);
  assert.deepEqual(view.result.display, current);
  assert.deepEqual(view.result.applied, { ...pose, projection: 'perspective', focalLength: 50 });
});

test('an invalid camera is refused before the viewport or the stored display is touched', () => {
  const current = { mode: 'solid' };
  const view = harness(current);
  assert.throws(() => view.apply({ ...pose, focalLength: 500 }), /focalLength/);
  assert.equal(view.result.applied, null, 'nothing reached the viewport');
  assert.equal(view.result.display, current, 'the display is as it was');
  assert.equal(view.result.recorded, null, 'and nothing was recorded');
});

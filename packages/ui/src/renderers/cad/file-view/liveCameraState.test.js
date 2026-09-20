import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import { parse } from '@babel/parser';
import traverseModule from '@babel/traverse';
import { clonePerspectiveSnapshot } from '@hardcore/core/lib/perspective.js';
import { cameraForViewSettings, viewerDisplaySettingsForCamera } from '../workbench/viewerDisplaySettings.js';
import { createRenderSessionState } from '../workbench/renderSessionState.js';
import { createViewSettingsStore } from '../workbench/viewSettingsStore.js';

const traverse = traverseModule.default || traverseModule;
const source = fs.readFileSync(new URL('./CadFileView.js', import.meta.url), 'utf8');
let cameraCommand;
traverse(parse(source, { sourceType: 'module', plugins: ['jsx'] }), {
  ObjectMethod(path) {
    if (path.node.key.name !== 'setCamera') return;
    assert.equal(cameraCommand, undefined, 'one mounted live camera command');
    cameraCommand = Function('scope', 'camera', `with (scope) { return (function(camera) ${source.slice(path.node.body.start, path.node.body.end)})(camera); }`);
  }
});
assert.ok(cameraCommand);

function harness(displaySettings) {
  const result = { applied: null, display: displaySettings, session: null, perspective: null };
  const viewSettingsStore = createViewSettingsStore(displaySettings);
  viewSettingsStore.subscribe(() => { result.display = viewSettingsStore.getSnapshot().display; });
  const scope = {
    viewSettingsStore, clonePerspectiveSnapshot, cameraForViewSettings, viewerDisplaySettingsForCamera, createRenderSessionState,
    selectedKey: 'part.step', selectedEntry: {}, previewMode: false, scopedWorkspacePerspective: camera => camera,
    viewerRef: { current: { setPerspective(camera) { result.applied = camera; return true; } } },
    setRenderSession: session => { result.session = session; },
    setViewerPerspective: camera => { result.perspective = camera; }, handlePerspectiveChange: () => {}
  };
  return { result, apply: camera => cameraCommand(scope, camera) };
}
const pose = { position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1], zoom: 1.4 };

test('setCamera activates its controls and applies the same projection/lens saved in display', () => {
  const current = { mode: 'render', camera: { enabled: false }, clip: { enabled: true, offset: 0.3 } };
  const view = harness(current);
  view.apply({ ...pose, projection: 'perspective', focalLength: 85 });
  assert.deepEqual(view.result.applied, { ...pose, projection: 'perspective', focalLength: 85 });
  assert.deepEqual(view.result.display, { ...current, camera: { enabled: true, projection: 'perspective', focalLength: 85 } });
  assert.deepEqual(view.result.session, { cadCamera: view.result.applied });
  assert.deepEqual(view.result.perspective, view.result.applied);
});

test('pose-only setCamera inherits configured projection/lens without creating display overrides', () => {
  const current = { mode: 'render' };
  const view = harness(current);
  view.apply(pose);
  assert.deepEqual(view.result.display, current);
  assert.deepEqual(view.result.applied, { ...pose, projection: 'perspective', focalLength: 50 });
});

test('invalid camera controls fail before mutating the viewport or stored state', () => {
  const current = { mode: 'solid' };
  const view = harness(current);
  assert.throws(() => view.apply({ ...pose, focalLength: 500 }), /focalLength/);
  assert.equal(view.result.applied, null);
  assert.equal(view.result.display, current);
  assert.equal(view.result.session, null);
});

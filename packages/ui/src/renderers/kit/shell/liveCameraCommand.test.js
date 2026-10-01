import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import { parse } from '@babel/parser';
import traverseModule from '@babel/traverse';
import { clonePerspectiveSnapshot } from '@text-to-cad/core/lib/perspective.js';
import { cameraForViewSettings, viewerDisplaySettingsForCamera } from '../view-settings/viewerDisplaySettings.js';
import { createViewSettingsStore } from '../view-settings/viewSettingsStore.js';
import { applyPerspectiveSnapshot, readScopedPerspectiveSnapshot } from '../camera/runtimeCamera.js';
import { createRealOrbitRuntime } from '../camera/harness/realOrbit.js';
import { cameraReadsBack, orbitReadsBack } from './liveReadback.js';
import { updateOrbitControls, PREVIEW_AUTO_ROTATE_SPEED } from '../camera/orbitControls.js';

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
let resetCommand;
traverse(parse(source, { sourceType: 'module', plugins: ['jsx'] }), {
  ObjectMethod(path) {
    if (path.node.key.name !== 'resetCamera') return;
    assert.equal(resetCommand, undefined, 'one live reset command');
    resetCommand = Function('scope', `with (scope) { return (function() ${source.slice(path.node.body.start, path.node.body.end)})(); }`);
  }
});
assert.ok(resetCommand, 'the shell exposes a live resetCamera');
let atRestCommand;
traverse(parse(source, { sourceType: 'module', plugins: ['jsx'] }), {
  ObjectProperty(path) {
    if (path.node.key.name !== 'atRest' || path.node.value.type !== 'ArrowFunctionExpression') return;
    assert.equal(atRestCommand, undefined, 'one live atRest');
    atRestCommand = Function('scope', `with (scope) { return (${source.slice(path.node.value.start, path.node.value.end)})(); }`);
  }
});
assert.ok(atRestCommand, 'the shell exposes a live atRest for the binding\'s capture');

function harness(displaySettings, viewer = null) {
  const result = { applied: null, display: displaySettings, perspective: null, recorded: null, moving: false };
  const viewSettingsStore = createViewSettingsStore(displaySettings);
  viewSettingsStore.subscribe(() => { result.display = viewSettingsStore.getSnapshot().display; });
  const scope = {
    viewSettingsStore, clonePerspectiveSnapshot, cameraForViewSettings, viewerDisplaySettingsForCamera, cameraReadsBack, orbitReadsBack,
    previewing: false, modelKey: 'model.bin', sceneScaleMode: 'cad',
    scopeShellCamera: camera => camera,
    viewerRef: { current: viewer || { setPerspective(camera) { result.applied = camera; return true; }, isCameraTransitioning: () => result.moving } },
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

test('setCamera is committed when the camera the shell APPLIED reads back at rest, not the request', () => {
  // The applied camera carries the configured lens and, through the scene scale, need not equal
  // the request; a binding that waited for the request would wait forever.
  const view = harness({ mode: 'render' });
  view.result.moving = true;
  const committed = view.apply(pose);
  assert.equal(typeof committed, 'function', 'the command hands the binding its predicate');
  const onScreen = { position: [...pose.position], target: [...pose.target], up: [...pose.up] };
  assert.equal(committed({ camera: onScreen }), false, 'still easing into place');
  view.result.moving = false;
  assert.equal(committed({ camera: { ...onScreen, position: [1, 2, 3] } }), false, 'a different camera on screen');
  assert.equal(committed({ camera: onScreen }), true, 'the applied camera, at rest');
});

test('resetCamera is committed when the eased move has come to rest, not when it has begun', () => {
  let moving = true;
  const committed = resetCommand({ viewerRef: { current: { resetZoom: () => true, isCameraTransitioning: () => moving } } });
  assert.equal(typeof committed, 'function', 'the reset hands the binding its predicate');
  assert.equal(committed(), false, 'still under way');
  moving = false;
  assert.equal(committed(), true, 'at rest');
  assert.throws(() => resetCommand({ viewerRef: { current: { resetZoom: () => false } } }), /unavailable/);
});

test('a setCamera beyond the controls\' distance clamp replies with the clamped camera, not one that never reads back', () => {
  // The REAL controls clamp the radius in `update()`; the viewport's own readback is the truth.
  const runtime = createRealOrbitRuntime({ maxDistance: 20 });
  const viewer = {
    setPerspective: camera => applyPerspectiveSnapshot(runtime, camera),
    getPerspective: () => readScopedPerspectiveSnapshot(runtime, { modelKey: 'model.bin', sceneScaleMode: 'cad', coordinateSystem: 'stored' }),
    isCameraTransitioning: () => Boolean(runtime.cameraTransition)
  };
  const view = harness({ mode: 'solid' }, viewer);
  const committed = view.apply({ position: [200, 0, 0], target: [0, 0, 0], up: [0, 0, 1] });
  const onScreen = viewer.getPerspective();
  assert.ok(Math.abs(Math.hypot(...onScreen.position) - 20) < 1e-6, 'the viewport clamped the distance to maxDistance');
  assert.deepEqual(view.result.recorded, onScreen, 'the file records the camera on screen, not the request');
  assert.equal(committed({ camera: onScreen }), true, 'the clamped camera is the one the reply waits for');
  assert.equal(cameraReadsBack(onScreen, { position: [200, 0, 0], target: [0, 0, 0] }), false, 'the request itself never reads back');
});

test('a setCamera while Preview\'s orbit plays reads back on every frame after it, up to the orbit\'s turn', () => {
  const runtime = createRealOrbitRuntime({ autoRotate: true });
  runtime.controls.autoRotateSpeed = PREVIEW_AUTO_ROTATE_SPEED;
  const loop = { orbitControlsLastTimestamp: 0 };
  updateOrbitControls(runtime.controls, 1000, loop);
  const viewer = {
    setPerspective: camera => applyPerspectiveSnapshot(runtime, camera),
    getPerspective: () => readScopedPerspectiveSnapshot(runtime, { modelKey: 'model.bin', sceneScaleMode: 'cad', coordinateSystem: 'stored' }),
    isCameraTransitioning: () => Boolean(runtime.cameraTransition),
    isOrbiting: () => Boolean(runtime.controls.autoRotate)
  };
  const view = harness({ mode: 'solid' }, viewer);
  const committed = view.apply({ position: [30, -20, 15], target: [1, 2, 3], up: [0, 0, 1] });
  const applied = viewer.getPerspective();
  assert.deepEqual(view.result.recorded, applied, 'the file records the camera that was applied');
  const readback = [];
  for (let frame = 1; frame <= 5; frame += 1) {
    updateOrbitControls(runtime.controls, 1000 + frame * 16.7, loop);
    readback.push(committed({ camera: viewer.getPerspective() }));
  }
  assert.ok(!cameraReadsBack(viewer.getPerspective(), applied), 'the orbit really did turn the camera');
  assert.deepEqual(readback, [true, true, true, true, true], 'the applied camera reads back on frames 1-5');
  const moved = viewer.getPerspective();
  assert.equal(committed({ camera: { ...moved, position: [moved.position[0], moved.position[1], moved.position[2] + 1] } }), false, 'a different height is not the applied camera');
});

test('atRest is false while the viewer\'s camera is transitioning and true otherwise, so a capture waits', () => {
  let moving = true;
  const scope = { viewerRef: { current: { isCameraTransitioning: () => moving } } };
  assert.equal(atRestCommand(scope), false, 'an eased move is under way');
  moving = false;
  assert.equal(atRestCommand(scope), true, 'the camera has come to rest');
  assert.equal(atRestCommand({ viewerRef: { current: null } }), true, 'no viewer, nothing to wait for');
});

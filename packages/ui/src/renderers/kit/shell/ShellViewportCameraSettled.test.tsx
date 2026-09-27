import React from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import * as THREE from 'three';

// The viewport's half of the camera-settled report (`ShellViewport.jsx`): the settles that record
// no perspective, which a renderer sampling the camera for detail cannot see from the stored view.
// The WebGL runtime hook is replaced by one that hands back the callbacks the viewport gives it,
// and the runtime is a real three camera with no renderer. The shell's half (a recorded move, and
// the wiring to the renderer) is RendererSurfaces.test.tsx.
const runtimeHook = vi.hoisted(() => ({ options: null as any }));
vi.mock('../../../../dist/renderers/kit/viewport/useViewerRuntime.js', () => ({
  useViewerRuntime: (options: any) => { runtimeHook.options = options; }
}));
import ShellViewport from '../../../../dist/renderers/kit/shell/ShellViewport.js';

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); runtimeHook.options = null; });

function liveRuntime(modelKey: string) {
  const camera = new THREE.OrthographicCamera(-50, 50, 40, -40, 0.01, 10000);
  camera.position.set(100, -100, 100);
  camera.up.set(0, 0, 1);
  const canvas = document.createElement('canvas');
  return { THREE, camera, orthographicCamera: camera, controls: { target: new THREE.Vector3(), update() {} },
    renderer: { domElement: canvas }, hasVisibleModel: true, activeModelKey: modelKey,
    // What the viewport's own effects (preview's orbit) touch on any runtime.
    interactionState: { restoreTimerId: 0 }, keyboardOrbitState: null, requestRender() {}, scheduleIdleQuality() {} };
}

function mount(props: Record<string, unknown> = {}) {
  const onCameraSettled = vi.fn(), onPerspectiveChange = vi.fn();
  const all = { modelKey: 'part', onCameraSettled, onPerspectiveChange, ...props };
  const view = render(<ShellViewport {...(all as any)} />);
  const runtime = liveRuntime('part');
  runtimeHook.options.runtimeRef.current = runtime;
  return { ...view, all, runtime, onCameraSettled, onPerspectiveChange };
}

it('a viewport resize is a settle every time, even when the stored perspective it emits has not changed', () => {
  const { onCameraSettled, onPerspectiveChange } = mount();
  act(() => { runtimeHook.options.onViewportResize(); });
  expect(onCameraSettled).toHaveBeenCalledTimes(1);
  // The first resize records the camera the viewport now holds.
  expect(onPerspectiveChange).toHaveBeenCalledTimes(1);
  // Same camera, same target, same zoom: an aspect change can still expose part of a scene.
  act(() => { runtimeHook.options.onViewportResize(); });
  expect(onCameraSettled).toHaveBeenCalledTimes(2);
  expect(onPerspectiveChange).toHaveBeenCalledTimes(1);
});

it('a preview camera that moves is a settle, and records no perspective', () => {
  const { all, rerender, runtime, onCameraSettled, onPerspectiveChange } = mount();
  rerender(<ShellViewport {...(all as any)} previewMode />);
  runtime.camera.position.set(0, -200, 50);
  act(() => { runtimeHook.options.emitPerspectiveChange(runtime); });
  expect(onCameraSettled).toHaveBeenCalledTimes(1);
  expect(onPerspectiveChange).not.toHaveBeenCalled();
  // Out of preview, the same move is recorded instead (and the shell turns that into the settle).
  rerender(<ShellViewport {...(all as any)} previewMode={false} />);
  runtime.camera.position.set(10, -200, 50);
  act(() => { runtimeHook.options.emitPerspectiveChange(runtime); });
  expect(onPerspectiveChange).toHaveBeenCalledTimes(1);
  expect(onCameraSettled).toHaveBeenCalledTimes(1);
});

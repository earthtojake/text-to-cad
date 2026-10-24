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
    // What the viewport's own effects (Preview's orbit) touch on any runtime.
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

it("the camera of a viewport that keeps none (Preview's) moving is a settle; the editor's records it instead", () => {
  const { all, rerender, runtime, onCameraSettled, onPerspectiveChange } = mount();
  rerender(<ShellViewport {...(all as any)} preview onPerspectiveChange={null} />);
  runtime.camera.position.set(0, -200, 50);
  act(() => { runtimeHook.options.emitPerspectiveChange(runtime); });
  expect(onCameraSettled).toHaveBeenCalledTimes(1);
  expect(onPerspectiveChange).not.toHaveBeenCalled();
  // A viewport that keeps its camera records the same move (and the shell turns that into the settle).
  rerender(<ShellViewport {...(all as any)} />);
  runtime.camera.position.set(10, -200, 50);
  act(() => { runtimeHook.options.emitPerspectiveChange(runtime); });
  expect(onPerspectiveChange).toHaveBeenCalledTimes(1);
  expect(onCameraSettled).toHaveBeenCalledTimes(1);
});

// On the same mounted viewport: a camera handed to the viewport (the agent's `setCamera`) or a
// Zoom to selection is the person's choice, as a drag is, so the completion fit of a model still
// arriving stands down for it (`reframeReason`'s `userMovedCamera`).
it('a camera handed to the viewport, or a zoom to a selection, is the user\'s camera', () => {
  const viewport = React.createRef<any>();
  const { runtime } = mount({ ref: viewport });
  act(() => { expect(viewport.current.setPerspective({ position: [40, -60, 30], target: [1, 2, 3], up: [0, 0, 1], zoom: 2 })).toBe(true); });
  expect(runtime.userMovedCamera).toBe(true);
  runtime.userMovedCamera = false;
  act(() => { expect(viewport.current.zoomToBounds({ min: [0, 0, 0], max: [4, 2, 1] }, { animate: false })).toBe(true); });
  expect(runtime.userMovedCamera).toBe(true);
});


it('prompt capture preserves the actual projection, lens and zoom for snapshot replay', () => {
  const viewport = React.createRef<any>();
  const { runtime } = mount({ ref: viewport });
  Object.defineProperties(runtime.renderer.domElement, { clientWidth: { value: 800 }, clientHeight: { value: 600 } });
  runtime.camera.zoom = 2;
  const ortho = viewport.current.promptCamera();
  expect(ortho.display.camera).toEqual({ projection: 'orthographic' });
  expect(ortho.camera.orthographicHalfHeight).toBe(20);
  expect(ortho.camera.zoom).toBeUndefined(); // Already folded into the half-height.
  const perspective = new THREE.PerspectiveCamera(50, 800 / 600);
  perspective.setFocalLength(85);
  perspective.position.copy(runtime.camera.position);
  perspective.up.copy(runtime.camera.up);
  perspective.zoom = 1.5;
  (runtime as any).camera = perspective;
  const captured = viewport.current.promptCamera();
  expect(captured.display.camera.projection).toBe('perspective');
  expect(captured.display.camera.focalLength).toBeCloseTo(85);
  expect(captured.camera.zoom).toBe(1.5);
  expect(captured.camera.position).toEqual(perspective.position.toArray());
  expect(captured.camera.orthographicHalfHeight).toBeCloseTo(perspective.position.length() * Math.tan(THREE.MathUtils.degToRad(perspective.getEffectiveFOV()) / 2));
});

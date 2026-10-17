import React from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import * as THREE from 'three';

// The viewport's camera handle (`ShellViewport.jsx`). The WebGL runtime hook is replaced by one
// that hands back the options the viewport gives it, and the runtime is a real three camera with
// no renderer.
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
  const view = render(<ShellViewport {...({ modelKey: 'part', ...props } as any)} />);
  const runtime = liveRuntime('part');
  runtimeHook.options.runtimeRef.current = runtime;
  return { ...view, runtime };
}

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

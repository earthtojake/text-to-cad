import React, { forwardRef, useEffect, useImperativeHandle } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { camExtras, camScene } from './__tests__/camFile';

// A CAM result whose viewer's chunk fails to load is a file that failed to load, never a plain GLB: drawn as one, it
// would show the paths of a plan that is not ready with nothing saying so. Only what loads the file and the WebGL
// viewport are replaced, and the chunk fails.
const loaded = vi.hoisted(() => ({ scene: null as any }));
vi.mock('../../../dist/renderers/kit/shell/ShellViewport.js', () => ({
  default: forwardRef(function StandInViewport(props: any, ref) {
    useImperativeHandle(ref, () => ({ requestRender() {} }));
    const update = props.viewUpdate;
    useEffect(() => { if (update?.revision) update.binding.complete(update.revision); }, [update?.revision, update?.binding]);
    return <div data-stand-in-viewport="" />;
  })
}));
vi.mock('../../../dist/renderers/glb/useGlbScene.js', () => ({
  useGlbScene: () => ({ scene: loaded.scene, revision: 'one', busy: false, error: null, progress: null })
}));
vi.mock('../../../dist/renderers/glb/camView.js', () => { throw new Error('Failed to fetch dynamically imported module: camView.js'); });
import GlbRenderer from '../../../dist/renderers/glb/GlbRenderer.js';
import { ViewerHostContext } from '../../../dist/host/context.js';
import { testHost } from '../../../dist/host/testing/host.js';

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('a CAM result whose viewer fails to load is refused, not drawn as a plain GLB', async () => {
  const root = camScene({ extras: { ...camExtras(), verdict: { status: 'fix', headline: '1 to fix', errors: 1 } } });
  const bounds = { min: [0, 0, 0], max: [10, 10, 5] };
  loaded.scene = { document: { scene: root, clips: [] }, object3D: root, bounds, restBounds: bounds, revision: 'one' };
  const settings = { toolStack: { panels: {}, collapsed: {} } };
  const catalog = { entries: [], error: null };
  const preferences = { getSnapshot: () => settings, subscribe: () => () => {}, update() {} };
  const client = { resources: {}, subscribe: () => () => {}, getSnapshot: () => catalog };
  const path = '/models/part.cam.glb';
  const props = { source: { id: 'one' }, file: { path, name: 'part.cam.glb', kind: 'file' }, document: null, navbarSlot: null,
    onReady() {}, onOpenFile() {}, appearance: { colorScheme: 'light' }, state: null, onStateChange() {}, onNavigationActionsChange() {}, reload() {},
    data: { client, entry: { path, hash: 'h' }, services: { preferences } } };
  render(<ViewerHostContext.Provider value={testHost()}><GlbRenderer {...(props as any)} /></ViewerHostContext.Provider>);
  const alert = await screen.findByRole('alert', {}, { timeout: 30000 });
  expect(alert.textContent).toBeTruthy();
  expect(document.querySelector('[data-file-sidebar-tool="job"]')).toBeNull();
}, 30000);

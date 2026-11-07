import React, { forwardRef, useEffect, useImperativeHandle } from 'react';
import { act, cleanup, render, screen } from '@testing-library/react';
import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// The FEA result viewer is a chunk of its own (`feaView.jsx`): a plain GLB never fetches it, and a result loads
// it before it is drawn, then shows Study. Only what loads the file and the WebGL viewport are replaced.
const loaded = vi.hoisted(() => ({ scene: null as any, requested: 0 }));
vi.mock('../../../dist/renderers/kit/shell/ShellViewport.js', () => ({
  default: forwardRef(function StandInViewport(props: any, ref) {
    useImperativeHandle(ref, () => ({ requestRender() {} }));
    const update = props.viewUpdate;
    useEffect(() => { if (update?.revision) update.binding.complete(update.revision); }, [update?.revision, update?.binding]);
    return <div data-stand-in-viewport="">{typeof props.children === 'function' ? props.children({ hostRef: { current: null }, runtimeRef: { current: null }, mountRef: { current: null }, viewerReadyTick: 1, commitScene: () => true }) : props.children}</div>;
  })
}));
vi.mock('../../../dist/renderers/glb/useGlbScene.js', () => ({
  useGlbScene: () => ({ scene: loaded.scene, revision: 'one', busy: false, error: null, progress: null })
}));
vi.mock('../../../dist/renderers/glb/feaView.js', async (importOriginal) => { loaded.requested += 1; return importOriginal(); });
import GlbRenderer from '../../../dist/renderers/glb/GlbRenderer.js';
import { ViewerHostContext } from '../../../dist/host/context.js';
import { testHost } from '../../../dist/host/testing/host.js';

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function mount(extras: Record<string, unknown> | null) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), 3));
  geometry.setIndex([0, 1, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(12), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0, 50, 100]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(9), 3));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array(3), 1));
  const mesh = new Mesh(geometry);
  if (extras) Object.assign(mesh.userData, extras);
  const root = new Group();
  root.add(mesh);
  const bounds = { min: [0, 0, 0], max: [1, 1, 0] };
  // As `createGlbScene` hands it over: `bounds` a getter reading `restBounds` at rest, which the view frames.
  loaded.scene = { document: { scene: root }, object3D: root, get bounds() { return this.restBounds; }, restBounds: bounds, revision: 'one' };
  const settings = { toolStack: { panels: {}, collapsed: {} } };
  const catalog = { entries: [], error: null };
  const preferences = { getSnapshot: () => settings, subscribe: () => () => {}, update() {} };
  const client = { resources: {}, subscribe: () => () => {}, getSnapshot: () => catalog };
  const props = { source: { id: 'one' }, file: { path: '/models/part.glb', name: 'part.glb', kind: 'file' }, document: null, navbarSlot: null,
    onReady() {}, onOpenFile() {}, appearance: { colorScheme: 'light' }, onStateChange() {}, onNavigationActionsChange() {}, reload() {},
    data: { client, entry: { path: '/models/part.glb', hash: 'h' }, services: { preferences } } };
  return render(<ViewerHostContext.Provider value={testHost()}><GlbRenderer {...(props as any)} /></ViewerHostContext.Provider>);
}

it('a plain GLB never requests the FEA viewer', async () => {
  const { container } = mount(null);
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  expect(loaded.requested).toBe(0);
  expect(screen.queryByRole('region', { name: 'Study' })).toBeNull();
  expect(container.querySelector('[data-fea-field]')).toBeNull();
});

it('an FEA result loads the FEA viewer, then shows Study', async () => {
  mount({ generator: 'cadgen fea', name: 'part von Mises', document: 'part.step', occurrence: 'part', deformation_scale: 1, safety_factor: 2.76, faces: [], findings: [],
    ramp: [[0, [0, 0, 1]], [1, [1, 0, 0]]],
    fields: [{ attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 100, attribute_scale: 1 },
      { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0, attribute_scale: 1000 }],
    checks: [{ kind: 'stress', label: 'Strength', value: 100, limit: 276, unit: 'MPa', ratio: 0.362319, close_at: 0.5, margin: 2, status: 'passes', where: { ref: null, at: [0, 0, 0] } }],
    study: { material: { name: '6061-T6', yield_MPa: 276 }, fixtures: [], loads: [], mesh: { size_mm: 1, refined_from_mm: null }, margin: 2 } });
  // The model waits as the file loading while the chunk comes in (in a test, its whole module graph is transformed).
  expect(screen.queryByRole('region', { name: 'Study' })).toBeNull();
  expect(await screen.findByRole('region', { name: 'Study' }, { timeout: 30000 })).toBeTruthy();
  expect(loaded.requested).toBe(1);
});

it('a result that does not read is the load\'s alert, never drawn as a plain GLB', async () => {
  // The generator says it is a result; without the fields cadgen always writes it does not read.
  mount({ generator: 'cadgen fea', name: 'part von Mises', document: 'part.step', occurrence: 'part' });
  expect((await screen.findByRole('alert', {}, { timeout: 30000 })).textContent).toContain('no fields');
  expect(screen.queryByRole('region', { name: 'Study' })).toBeNull();
});

import React, { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';

// An FEA result's view under the real shell and the real playbar runtime (`useGlbAnimation`, not
// stood in): the Load ramp in preview climbs the colours and the deformation as the playbar's clock
// runs, and Clip cuts the result open. Only what loads the file and the WebGL viewport are replaced.
const loaded = vi.hoisted(() => ({ scene: null as any }));
vi.mock('../../../dist/renderers/kit/shell/ShellViewport.js', () => ({
  default: forwardRef(function StandInViewport(props: any, ref) {
    useImperativeHandle(ref, () => ({ requestRender() {} }));
    // A view update is acknowledged as the viewport does once it holds the frame that shows it.
    const update = props.viewUpdate;
    useEffect(() => { if (update?.revision) update.binding.complete(update.revision); }, [update?.revision, update?.binding]);
    return <div data-stand-in-viewport="">{typeof props.children === 'function' ? props.children({ hostRef: { current: null }, runtimeRef: { current: null }, mountRef: { current: null }, viewerReadyTick: 1, commitScene: () => true }) : props.children}</div>;
  })
}));
vi.mock('../../../dist/renderers/glb/useGlbScene.js', () => ({
  useGlbScene: () => ({ scene: loaded.scene, revision: 'one', busy: false, error: null, progress: null })
}));
import GlbRenderer, { loadFeaView } from '../../../dist/renderers/glb/GlbRenderer.js';
import { ViewerElementContext, ViewerHostContext } from '../../../dist/host/context.js';
import { testHost } from '../../../dist/host/testing/host.js';

// Frames run by hand: each `frame(ms)` runs the callbacks waiting for the next animation frame at that time.
let waiting: Array<(now: number) => void> = [];
const frame = (now: number) => act(() => { const due = waiting; waiting = []; due.forEach(callback => callback(now)); });
// The FEA viewer is its own chunk (`GlbRenderer.lazy.test.tsx`): loaded once here, a result draws as soon as it mounts.
beforeAll(() => loadFeaView());
beforeEach(() => {
  waiting = [];
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
  vi.stubGlobal('requestAnimationFrame', (callback: (now: number) => void) => { waiting.push(callback); return waiting.length; });
  vi.stubGlobal('cancelAnimationFrame', () => {});
  vi.spyOn(performance, 'now').mockReturnValue(0);
});
afterEach(() => { vi.restoreAllMocks(); cleanup(); vi.unstubAllGlobals(); document.querySelectorAll('[data-test-navbar]').forEach(slot => slot.remove()); });

// A result, as `cadgen fea solve` writes it: the file draws its displacement ×10.
const STATIC = {
  generator: 'cadgen fea', name: 'bracket von Mises', deformation_scale: 10, safety_factor: 5.83, document: 'part.step', occurrence: 'bracket',
  ramp: [[0, [0.05, 0.10, 0.90]], [0.25, [0.05, 0.85, 0.95]], [0.5, [0.10, 0.85, 0.15]], [0.75, [0.98, 0.90, 0.10]], [1, [0.90, 0.08, 0.05]]],
  faces: ['bracket/face 1', 'bracket/face 2'],
  fields: [{ attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 100, attribute_scale: 1 },
    { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 2, attribute_scale: 1000 }],
  findings: [],
  checks: [{ kind: 'stress', label: 'Strength', value: 100, limit: 583, unit: 'MPa', ratio: 0.171527, close_at: 0.5, margin: 2, status: 'passes', where: { ref: 'bracket/face 1', at: [0, 0, 0] } }],
  study: { material: { name: 'Steel', yield_MPa: 583 }, fixtures: [{ type: 'fixed', faces: ['bracket/face 1'] }],
    loads: [{ type: 'force', faces: ['bracket/face 2'], vector_N: [0, 0, -100] }], mesh: { size_mm: 1, refined_from_mm: null }, margin: 2 },
};

function mount(extras: Record<string, unknown> | null = STATIC) {
  const geometry = new BufferGeometry();
  // Vertex 2 drawn ×10 its 2 mm: 0.02 m down in z.
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, -0.02, 1, 1, 0]), 3));
  geometry.setIndex([0, 1, 2, 1, 3, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(16).fill(7), 4, true));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array([0, 0, 0, 0, 0, 0, 0, 0, -0.002, 0, 0, 0]), 3));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 0, 1]), 1));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0, 50, 100, 25]), 1));
  const mesh = new Mesh(geometry);
  if (extras) Object.assign(mesh.userData, extras);
  const root = new Group();
  root.add(mesh);
  const bounds = { min: [0, 0, 0], max: [1, 1, 0] };
  // As `createGlbScene` hands it over: `bounds` a getter reading `restBounds` at rest, which the view frames.
  loaded.scene = { document: { scene: root }, object3D: root, get bounds() { return this.restBounds; }, restBounds: bounds, revision: 'one' };
  const slot = document.createElement('div');
  slot.setAttribute('data-test-navbar', '');
  document.body.append(slot);
  let snapshot: any = { toolStack: { panels: {}, collapsed: {} } };
  const preferences = { getSnapshot: () => snapshot, subscribe: () => () => {}, update(patch: any) { snapshot = { ...snapshot, ...patch }; } };
  const catalog = { entries: [], error: null };
  const client = { resources: {}, subscribe: () => () => {}, getSnapshot: () => catalog };
  const props = { source: { id: 'one' }, file: { path: '/models/part.glb', name: 'part.glb', kind: 'file' }, document: null, navbarSlot: slot,
    onReady() {}, onOpenFile() {}, appearance: { colorScheme: 'light' }, state: undefined, onStateChange() {}, onNavigationActionsChange() {}, reload() {},
    data: { client, entry: { path: '/models/part.glb', hash: 'h' }, services: { preferences } } };
  function ViewerElement({ children }: { children: React.ReactNode }) {
    const element = useRef<HTMLDivElement | null>(null);
    return <ViewerElementContext.Provider value={element}><div ref={element}>{children}</div></ViewerElementContext.Provider>;
  }
  render(<ViewerHostContext.Provider value={testHost()}><ViewerElement><GlbRenderer {...(props as any)} /></ViewerElement></ViewerHostContext.Provider>);
  return mesh;
}

it('the Load ramp in preview climbs the colours and the deformation from no load to the load, as the playbar\'s clock runs', () => {
  const mesh = mount();
  // Vertex 2's colour: red at its 100 MPa, the field's top; its z: the file's ×10 drawn.
  const vertex2 = () => Array.from(mesh.geometry.getAttribute('color').array as Uint8Array).slice(8, 11);
  const z2 = () => mesh.geometry.getAttribute('position').getZ(2);
  const full = vertex2();
  expect(z2()).toBeCloseTo(-0.02, 6);
  // The view frames the part as drawn, deformed: the box it frames grew to hold vertex 2.
  expect(loaded.scene.restBounds.min[2]).toBeCloseTo(-0.02, 6);
  expect(loaded.scene.bounds).toBe(loaded.scene.restBounds);
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Preview' })); });
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Play animation' })); });
  // The ramp starts with no load on: the colours at the ramp's low end, the part at rest.
  expect(vertex2()).toEqual([13, 26, 230]);
  expect(z2()).toBeCloseTo(0, 6);
  const seen = [vertex2()];
  for (const ms of [500, 1000, 1500]) { frame(ms); seen.push(vertex2()); }
  // Every tick of its clock puts more of the load on: a new colour, and the part a share of the way down.
  expect(new Set(seen.map(String)).size).toBe(seen.length);
  expect(z2()).toBeCloseTo(-0.015, 6);
  // At the end of its two seconds the whole load is on, and it starts over from none as it loops.
  frame(1999);
  expect(z2()).toBeCloseTo(-0.02, 4);
  expect(vertex2()).toEqual(full);
  frame(2100);
  expect(z2()).toBeCloseTo(-0.001, 6);
});

it('a result has a GLB\'s tools, Clip among them, and a cut never recolours it or its colour bar', () => {
  const mesh = mount();
  const colours = Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);
  // The tools any GLB has, Select first: Clip is the viewer's (`kit/tools/model-effects`), the cut the viewport's.
  const strip = Array.from(document.querySelectorAll('[data-cad-toolbar] button')).map(button => button.getAttribute('aria-label'));
  expect(strip[0]).toBe('Select');
  expect(strip).toContain('Clip');
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Clip' })); });
  act(() => { fireEvent.keyDown(screen.getByRole('slider', { name: 'Clip amount' }), { key: 'End' }); });
  // A cut discards; it never recolours. The colour bar stays the reading it was, and Study stays the sidebar's.
  expect(Array.from(mesh.geometry.getAttribute('color').array as Uint8Array)).toEqual(colours);
  expect(document.querySelector('[aria-label="von Mises stress colour bar"]')).toBeTruthy();
  expect(screen.getByRole('region', { name: 'Study' })).toBeTruthy();
});

import React, { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BufferAttribute, BufferGeometry, Group, Mesh, Vector3 } from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// An FEA result's view under the real shell and the real playbar runtime (`useGlbAnimation`, not
// stood in): Play in preview steps a series' colours through its frames as the playbar's clock runs,
// and Clip cuts the result open. Only what loads the file and the WebGL viewport are replaced.
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
import GlbRenderer from '../../../dist/renderers/glb/GlbRenderer.js';
import { ViewerElementContext, ViewerHostContext } from '../../../dist/host/context.js';
import { testHost } from '../../../dist/host/testing/host.js';

// Frames run by hand: each `frame(ms)` runs the callbacks waiting for the next animation frame at that time.
let waiting: Array<(now: number) => void> = [];
const frame = (now: number) => act(() => { const due = waiting; waiting = []; due.forEach(callback => callback(now)); });
beforeEach(() => {
  waiting = [];
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
  vi.stubGlobal('requestAnimationFrame', (callback: (now: number) => void) => { waiting.push(callback); return waiting.length; });
  vi.stubGlobal('cancelAnimationFrame', () => {});
  vi.spyOn(performance, 'now').mockReturnValue(0);
});
afterEach(() => { vi.restoreAllMocks(); cleanup(); vi.unstubAllGlobals(); document.querySelectorAll('[data-test-navbar]').forEach(slot => slot.remove()); });

// Heat over time, as `cadgen fea solve` writes it: a temperature per frame, warming from 25 °C, the
// model never deformed (its displacement is zero), opening on the hottest frame.
const WARMUP = {
  generator: 'cadgen fea', name: 'heatsink temperature', deformation_scale: 1, document: 'part.step', occurrence: 'o1', faces: ['#o1.f1', '#o1.f2'],
  analysis: { type: 'thermal_transient', tier: 1, word: 'Heat over time', reference_C: 25 },
  fields: [{ attribute: '_TEMPERATURE', name: 'temperature', units: '°C', min: 25, max: 75, attribute_scale: 1, signed: true, per_frame: true }],
  series: { kind: 'time', unit: 's', default: 2, frames: [
    { value: 0, label: '0 s', attributes: { temperature: '_TEMPERATURE' } },
    { value: 60, label: '60 s', attributes: { temperature: '_TEMPERATURE_F1' } },
    { value: 120, label: '2 min', attributes: { temperature: '_TEMPERATURE_F2' } }] },
};

function mount(extras: Record<string, unknown> | null = WARMUP) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0]), 3));
  geometry.setIndex([0, 1, 2, 1, 3, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(16).fill(7), 4, true));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array(12), 3));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array([0, 0, 0, 1]), 1));
  geometry.setAttribute('_temperature', new BufferAttribute(new Float32Array([25, 25, 25, 25]), 1));
  geometry.setAttribute('_temperature_f1', new BufferAttribute(new Float32Array([25, 40, 50, 30]), 1));
  geometry.setAttribute('_temperature_f2', new BufferAttribute(new Float32Array([25, 60, 75, 40]), 1));
  const mesh = new Mesh(geometry);
  if (extras) Object.assign(mesh.userData, extras);
  const root = new Group();
  root.add(mesh);
  const bounds = { min: [0, 0, 0], max: [1, 1, 0] };
  loaded.scene = { document: { scene: root }, object3D: root, bounds, restBounds: bounds, revision: 'one' };
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

it('Play in preview steps a heat-over-time result\'s colours through its frames, and leaves the unmoving model\'s positions alone', () => {
  const mesh = mount();
  // Vertex 2's colour: red at the hottest frame's 75 °C, which the result opens on; blue at the start's 25 °C.
  const vertex2 = () => Array.from(mesh.geometry.getAttribute('color').array as Uint8Array).slice(8, 11);
  const position = mesh.geometry.getAttribute('position');
  const hottest = vertex2();
  const placed = position.version;
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Preview' })); });
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Play animation' })); });
  const seen = [vertex2()];
  for (const ms of [250, 750, 1500, 2250]) { frame(ms); seen.push(vertex2()); }
  // Play starts at 0 s, all 25 °C, and every tick of its clock shows a new blend of two frames.
  expect(seen[0]).toEqual([13, 26, 230]);
  expect(seen[0]).not.toEqual(hottest);
  expect(new Set(seen.map(String)).size).toBe(seen.length);
  // A temperature moves nothing: its frames share the file's displacement, so no tick rewrites the
  // positions (and their normals and markers).
  expect(position.version).toBe(placed);
});

it('Clip cuts a result open: on the strip after Select, a neutral panel that an edit makes a cut on the mesh, its colours and colour bar untouched', async () => {
  const mesh = mount();
  const material = mesh.material as any;
  // What the viewport's next frame sets on whatever material the mesh draws with.
  const drawnPlanes = () => { mesh.onBeforeRender(null as any, null as any, null as any, mesh.geometry, material, null as any); return material.clippingPlanes || []; };
  const colours = Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);
  expect(screen.getAllByRole('button').map(button => button.getAttribute('aria-label')).filter(name => name === 'Select' || name === 'Clip')).toEqual(['Select', 'Clip']);
  expect(screen.queryByRole('region', { name: 'Clip controls' })).toBeNull();
  // A press opens the panel neutral: no cut yet.
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Clip' })); });
  expect(screen.getByRole('region', { name: 'Clip controls' }).textContent).toContain('0%');
  expect(drawnPlanes()).toHaveLength(0);
  // An edit cuts: all the way along X keeps x <= 0, the near half facing the default camera.
  act(() => { fireEvent.keyDown(screen.getByRole('slider', { name: 'Clip amount' }), { key: 'End' }); });
  expect(screen.getByRole('region', { name: 'Clip controls' }).textContent).toContain('100%');
  // The cut is drawn once the viewport has applied the view (`useAppliedViewSettings`).
  await waitFor(() => expect(drawnPlanes()).toHaveLength(1));
  const [plane] = drawnPlanes();
  expect(plane.distanceToPoint(new Vector3(1, 0, 0))).toBeLessThan(0);
  expect(plane.distanceToPoint(new Vector3(0, 0, 0))).toBeCloseTo(0, 9);
  // The cut discards; it never recolours. The colour bar stays the reading it was.
  expect(Array.from(mesh.geometry.getAttribute('color').array as Uint8Array)).toEqual(colours);
  expect(document.querySelector('[aria-label="temperature colour bar"]')).toBeTruthy();
  // Preview suspends the tool effects: the whole result, cut again on the way back.
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Preview' })); });
  expect(drawnPlanes()).toHaveLength(0);
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Exit preview' })); });
  expect(drawnPlanes()).toHaveLength(1);
  // Back to Select, the applied cut keeps its panel; its X removes the cut and the panel.
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Select' })); });
  expect(screen.getByRole('region', { name: 'Clip controls' })).toBeTruthy();
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Close clip controls' })); });
  expect(screen.queryByRole('region', { name: 'Clip controls' })).toBeNull();
  await waitFor(() => expect(drawnPlanes()).toHaveLength(0));
});

it('a GLB that is not a result has no Clip', () => {
  mount(null);
  expect(screen.queryByRole('button', { name: 'Clip' })).toBeNull();
});

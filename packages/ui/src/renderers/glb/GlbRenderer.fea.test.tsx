import React, { forwardRef, useImperativeHandle } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// The GLB renderer's FEA surfaces under the real shell, with only what loads the file and the WebGL
// viewport replaced: a result's field and deformation are Display's (an Analysis section), its colour
// bar is a reading with no controls, and a GLB that is not a result has neither.
const loaded = vi.hoisted(() => ({ root: null as any, revision: 'one', animation: null as any }));
vi.mock('../../../dist/renderers/kit/shell/ShellViewport.js', () => ({
  default: forwardRef(function StandInViewport(props: any, ref) {
    useImperativeHandle(ref, () => ({ requestRender() {} }));
    return <div data-stand-in-viewport="">{typeof props.children === 'function' ? props.children({ hostRef: { current: null }, runtimeRef: { current: null }, mountRef: { current: null }, viewerReadyTick: 1, commitScene: () => true }) : props.children}</div>;
  })
}));
vi.mock('../../../dist/renderers/glb/useGlbScene.js', () => ({
  useGlbScene: () => ({ scene: { document: { scene: loaded.root }, revision: loaded.revision }, revision: loaded.revision, busy: false, error: null, progress: null })
}));
vi.mock('../../../dist/renderers/glb/useGlbAnimation.js', () => ({ useGlbAnimation: () => loaded.animation }));
import GlbRenderer from '../../../dist/renderers/glb/GlbRenderer.js';
import { writeFileView } from '../../../dist/renderers/kit/shell/fileView.js';
import { ViewerHostContext } from '../../../dist/host/context.js';
import { testHost } from '../../../dist/host/testing/host.js';

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
});
afterEach(() => { loaded.animation = null; cleanup(); vi.unstubAllGlobals(); document.querySelectorAll('[data-test-navbar]').forEach(slot => slot.remove()); });

// Two triangles the way GLTFLoader hands a result over: lower-cased custom attributes, extras in userData.
function resultRoot(extras: Record<string, unknown> | null) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0]), 3));
  geometry.setIndex([0, 1, 2, 1, 3, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(16).fill(7), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0, 50, 100, 25]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array([0, 0, 0, 0, 0, 0.001, 0, 0, 0.002, 0, 0, 0.0005]), 3));
  const mesh = new Mesh(geometry);
  if (extras) Object.assign(mesh.userData, extras);
  const root = new Group();
  root.add(mesh);
  return { mesh, root };
}
const RESULT = {
  generator: 'cadgen fea', name: 'part von Mises', deformation_scale: 10, safety_factor: 5.83,
  fields: [
    { attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 47.3, attribute_scale: 1 },
    { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.0288, attribute_scale: 1000 },
  ],
};
const colourBytes = (mesh: Mesh) => Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);

function mount(extras: Record<string, unknown> | null, state?: unknown) {
  const built = resultRoot(extras);
  loaded.root = built.root;
  const slot = document.createElement('div');
  slot.setAttribute('data-test-navbar', '');
  document.body.append(slot);
  const save = vi.fn();
  const settings = { toolStack: { panels: {}, collapsed: {} } };
  const preferences = { getSnapshot: () => settings, subscribe: () => () => {}, update() {} };
  const catalog = { entries: [], error: null };
  const client = { resources: {}, subscribe: () => () => {}, getSnapshot: () => catalog };
  const props = { source: { id: 'one' }, file: { path: '/models/part.glb', name: 'part.glb', kind: 'file' }, document: null, navbarSlot: slot,
    onReady() {}, onOpenFile() {}, appearance: { colorScheme: 'light' }, state, onStateChange: save, onNavigationActionsChange() {}, reload() {},
    data: { client, entry: { path: '/models/part.glb', hash: 'h' }, services: { preferences } } };
  const view = render(<ViewerHostContext.Provider value={testHost()}><GlbRenderer {...(props as any)} /></ViewerHostContext.Provider>);
  return { ...view, ...built, save };
}
const openDisplay = () => act(() => { fireEvent.click(screen.getByRole('button', { name: 'Display' })); });

it('puts the field and deformation in Display, and a colour bar with one plain line on the view', () => {
  const { container } = mount(RESULT);
  const bar = container.querySelector('[role="group"][aria-label="von Mises stress colour bar"]')!;
  expect(bar.querySelector('[data-fea-summary]')!.textContent).toBe('Peak stress 47 MPa · holds 5.8× this load · moves up to 0.029 mm');
  expect(bar.textContent).toContain('47.3 MPa');
  // The bar is a reading: nothing on it to press or drag.
  expect(bar.querySelectorAll('button, input, [role="slider"], [role="combobox"]').length).toBe(0);
  expect(screen.queryByRole('combobox', { name: 'Result field' })).toBeNull();
  openDisplay();
  expect(screen.getByText('Analysis')).toBeTruthy();
  expect(screen.getByRole('combobox', { name: 'Result field' }).textContent).toContain('von Mises stress');
  expect(screen.getByRole('slider', { name: 'Deformation scale' })).toBeTruthy();
});

it('the field switch recolours the mesh and changes the bar\'s line', () => {
  const { mesh, container } = mount(RESULT);
  const stress = colourBytes(mesh);
  expect(stress.slice(0, 4)).toEqual([13, 26, 230, 255]);
  openDisplay();
  act(() => { fireEvent.click(screen.getByRole('combobox', { name: 'Result field' })); });
  act(() => { fireEvent.click(screen.getByRole('option', { name: 'displacement' })); });
  expect(colourBytes(mesh)).not.toEqual(stress);
  const bar = container.querySelector('[role="group"][aria-label="displacement colour bar"]')!;
  expect(bar.querySelector('[data-fea-summary]')!.textContent).toBe('Moves up to 0.029 mm');
});

it('the deformation value rescales the drawn displacement from the file\'s positions, and the choice is saved with the file', () => {
  vi.useFakeTimers();
  const { mesh, save } = mount(RESULT);
  const position = mesh.geometry.getAttribute('position');
  openDisplay();
  const value = screen.getByRole('textbox', { name: 'Deformation scale value' });
  act(() => { fireEvent.change(value, { target: { value: '0' } }); fireEvent.blur(value); });
  // 10x of vertex 2's 0.002 m is baked in; at 0x it is back where it was.
  expect(position.getZ(2)).toBeCloseTo(-0.02, 6);
  act(() => { vi.advanceTimersByTime(500); });
  vi.useRealTimers();
  expect(save.mock.calls.at(-1)![0].renderer.fea.value).toEqual({ field: null, scale: 0 });
});

it('takes the stored choice back for the same result, and not for a re-solved one', () => {
  const stored = writeFileView({ renderer: { fea: { field: '_displacement', scale: 5 } }, signatures: { fea: '_von_mises,_displacement:10' } });
  const { mesh, container } = mount(RESULT, stored);
  expect(container.querySelector('[role="group"][aria-label="displacement colour bar"]')).toBeTruthy();
  expect(mesh.geometry.getAttribute('position').getZ(2)).toBeCloseTo(-0.01, 6);
  cleanup();
  const resolved = mount({ ...RESULT, deformation_scale: 20 }, stored);
  expect(resolved.container.querySelector('[role="group"][aria-label="von Mises stress colour bar"]')).toBeTruthy();
});

it('a GLB that is not a result has no colour bar, no Analysis section and its colours untouched', () => {
  const { mesh, container } = mount(null);
  expect(container.querySelector('[aria-label$="colour bar"]')).toBeNull();
  openDisplay();
  expect(screen.queryByText('Analysis')).toBeNull();
  expect(colourBytes(mesh).every(byte => byte === 7)).toBe(true);
});

it('the colour bar steps up above the playbar when the result also has routines, and a stored scale is held to the slider\'s range', () => {
  const plain = mount(RESULT);
  const low = (plain.container.querySelector('[aria-label$="colour bar"]')!.parentElement as HTMLElement).style.bottom;
  expect(low).toBe('var(--cad-viewport-bottom-center, 1.75rem)');
  cleanup();
  loaded.animation = { clips: [{ id: 'a' }] };
  const stored = writeFileView({ renderer: { fea: { field: null, scale: 9999 } }, signatures: { fea: '_von_mises,_displacement:10' } });
  const animated = mount(RESULT, stored);
  const high = (animated.container.querySelector('[aria-label$="colour bar"]')!.parentElement as HTMLElement).style.bottom;
  expect(high).not.toBe(low);
  expect(high).toContain('3rem');
  // The slider tops out at four times the file's own 10x.
  expect(animated.mesh.geometry.getAttribute('position').getZ(2)).toBeCloseTo(0.06, 6);
});

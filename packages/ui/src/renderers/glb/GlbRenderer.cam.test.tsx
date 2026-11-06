import React, { forwardRef, useEffect, useImperativeHandle } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { camExtras, camScene } from './__tests__/camFile';

// The CAM result viewer is a chunk of its own (`camView.jsx`): a plain GLB never fetches it, and a result loads it
// before it is drawn, then offers Job in the file sidebar. Only what loads the file and the WebGL viewport are replaced.
const loaded = vi.hoisted(() => ({ scene: null as any, requested: 0, overlays: 0 }));
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
vi.mock('../../../dist/renderers/glb/camView.js', async (importOriginal) => { loaded.requested += 1; return importOriginal(); });
import GlbRenderer from '../../../dist/renderers/glb/GlbRenderer.js';
import { useReducedMotion } from '../../../dist/renderers/glb/cam/useCamResult.js';
import { ViewerHostContext } from '../../../dist/host/context.js';
import { testHost } from '../../../dist/host/testing/host.js';

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function mount(root: Group, path = '/models/part.glb', { state = null as unknown, onStateChange = (_: any) => {} } = {}) {
  const bounds = { min: [0, 0, 0], max: [10, 10, 5] };
  loaded.scene = { document: { scene: root, clips: [] }, object3D: root, bounds, restBounds: bounds, revision: 'one' };
  const settings = { toolStack: { panels: {}, collapsed: {} } };
  const catalog = { entries: [], error: null };
  const preferences = { getSnapshot: () => settings, subscribe: () => () => {}, update() {} };
  const client = { resources: {}, subscribe: () => () => {}, getSnapshot: () => catalog };
  const props = { source: { id: 'one' }, file: { path, name: path.split('/').at(-1), kind: 'file' }, document: null, navbarSlot: null,
    onReady() {}, onOpenFile() {}, appearance: { colorScheme: 'light' }, state, onStateChange, onNavigationActionsChange() {}, reload() {},
    data: { client, entry: { path, hash: 'h' }, services: { preferences } } };
  return render(<ViewerHostContext.Provider value={testHost()}><GlbRenderer {...(props as any)} /></ViewerHostContext.Provider>);
}

it('a plain GLB never requests the CAM viewer', async () => {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), 3));
  const root = new Group();
  root.add(new Mesh(geometry));
  mount(root);
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  expect(loaded.requested).toBe(0);
  expect(document.querySelector('[data-file-sidebar-tool="job"]')).toBeNull();
  expect(document.querySelector('[data-tool-panel-id="job"]')).toBeNull();
});

/** Job's tile in the file sidebar, once the result has loaded; pressed, it opens the section. */
async function openJob() {
  const tile = await waitFor(() => {
    const found = document.querySelector<HTMLElement>('[data-file-sidebar-tool="job"]');
    if (!found) throw new Error('no Job tile yet');
    return found;
  }, { timeout: 30000 });
  expect(tile.getAttribute('aria-label')).toBe('Job');
  // None is open as a file opens.
  expect(tile.getAttribute('aria-pressed')).toBe('false');
  fireEvent.click(tile);
  expect(tile.getAttribute('aria-pressed')).toBe('true');
  return screen.getByRole('region', { name: 'Job' });
}

it('a CAM result loads the CAM viewer, then offers Job in the file sidebar; a row isolates its operation until it is chosen again', async () => {
  mount(camScene(), '/models/part.cam.glb');
  // The model waits as the file loading while the chunk comes in.
  expect(document.querySelector('[data-file-sidebar-tool="job"]')).toBeNull();
  expect(await openJob()).toBeTruthy();
  expect(loaded.requested).toBe(1);
  // A result never explodes: its nodes are the part, the stock and the paths.
  expect(screen.queryByRole('button', { name: 'Explode' })).toBeNull();
  const pocket = screen.getByRole('button', { name: 'Select Pocket' });
  fireEvent.click(pocket);
  expect(pocket.getAttribute('aria-pressed')).toBe('true');
  // The row chosen is Quick Edit's chip: the part the job was planned from, by the operation's faces.
  const chip = await waitFor(() => {
    const found = document.querySelector('[data-quick-edit-ref="cam:op:1"]');
    if (!found) throw new Error('no chip yet');
    return found;
  });
  expect(chip.textContent).toContain('Pocket');
  fireEvent.click(screen.getByRole('button', { name: 'Select Face' }));
  expect(screen.getByRole('button', { name: 'Select Pocket' }).getAttribute('aria-pressed')).toBe('false');
  fireEvent.click(screen.getByRole('button', { name: 'Select Face' }));
  expect(screen.getByRole('button', { name: 'Select Face' }).getAttribute('aria-pressed')).toBe('false');
  expect(document.querySelector('[data-quick-edit-ref^="cam:"]')).toBeNull();
  // Its chip's X lets go of the choice, as a second press of its row does.
  fireEvent.click(screen.getByRole('button', { name: 'Select Pocket' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Remove Pocket' }));
  expect(screen.getByRole('button', { name: 'Select Pocket' }).getAttribute('aria-pressed')).toBe('false');
}, 30000);

it('an operation\'s eye hides its paths, and the file\'s view keeps what is hidden with Job\'s Show rows', async () => {
  const onStateChange = vi.fn();
  const view = mount(camScene(), '/models/part.cam.glb', { onStateChange });
  await openJob();
  fireEvent.click(screen.getByRole('button', { name: 'Hide Face' }));
  expect(screen.getByRole('button', { name: 'Reveal Face' })).toBeTruthy();
  // Hiding is not choosing: nothing is isolated.
  expect(screen.getByRole('button', { name: 'Select Face' }).getAttribute('aria-pressed')).toBe('false');
  // What Display used to gate is Job's Show rows: the stock starts put away, and its eye brings it out.
  fireEvent.click(screen.getByRole('button', { name: 'Reveal Stock' }));
  expect(screen.getByRole('button', { name: 'Hide Stock' })).toBeTruthy();
  view.unmount();
  const record = onStateChange.mock.lastCall![0];
  expect(record.renderer.cam.signature).toBe('cam:1');
  expect(record.renderer.cam.value).toMatchObject({ hidden: [0], toolpaths: true, tool: true, stock: true });
  // Opened again with that view: Face is still hidden, and the stock still shown.
  mount(camScene(), '/models/part.cam.glb', { state: record });
  await openJob();
  expect(screen.getByRole('button', { name: 'Reveal Face' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Hide Pocket' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Hide Stock' })).toBeTruthy();
}, 30000);

it('reduces motion where the app says so or the system does', () => {
  const seen: boolean[] = [];
  function Probe() { seen.push(useReducedMotion()); return null; }
  render(<ViewerHostContext.Provider value={testHost()}><Probe /></ViewerHostContext.Provider>);
  expect(seen.at(-1)).toBe(false);
  render(<ViewerHostContext.Provider value={testHost({ environment: { colorScheme: 'light', reducedMotion: true } })}><Probe /></ViewerHostContext.Provider>);
  expect(seen.at(-1)).toBe(true);
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: query === '(prefers-reduced-motion: reduce)', media: query,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
  render(<ViewerHostContext.Provider value={testHost()}><Probe /></ViewerHostContext.Provider>);
  expect(seen.at(-1)).toBe(true);
});

it('a damaged CAM result is refused as a file that failed to load, naming what it is missing', async () => {
  // Drawn with a default in a missing value's place, it would show a plan nobody wrote.
  const extras = camExtras();
  delete extras.setups[0].operations[0].t0;
  mount(camScene({ extras }), '/models/part.cam.glb');
  const alert = await screen.findByRole('alert', {}, { timeout: 30000 });
  expect(alert.textContent).toContain('cam.setups[0].operations[0].t0 is not a number');
  expect(document.querySelector('[data-file-sidebar-tool="job"]')).toBeNull();
}, 30000);

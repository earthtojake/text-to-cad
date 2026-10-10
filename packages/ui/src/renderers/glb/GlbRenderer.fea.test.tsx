import React, { forwardRef, useImperativeHandle, useRef } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// The GLB renderer's FEA surfaces under the real shell, with only what loads the file and the WebGL
// viewport replaced: a result's study, field and deformation are Select's Study panel, its colour
// bar is a reading with no controls, and a GLB that is not a result has neither.
const loaded = vi.hoisted(() => ({ root: null as any, scene: null as any, revision: 'one', animation: null as any, runtime: null as any, host: null as any, own: null as any }));
vi.mock('../../../dist/renderers/kit/shell/ShellViewport.js', () => ({
  default: forwardRef(function StandInViewport(props: any, ref) {
    useImperativeHandle(ref, () => ({ requestRender() {} }));
    return <div data-stand-in-viewport="">{typeof props.children === 'function' ? props.children({ hostRef: { current: loaded.host || (loaded.runtime ? { clientWidth: 800, clientHeight: 600, style: {}, addEventListener() {}, removeEventListener() {} } : null) }, runtimeRef: { current: loaded.runtime }, mountRef: { current: null }, viewerReadyTick: 1, commitScene: () => true }) : props.children}</div>;
  })
}));
vi.mock('../../../dist/renderers/glb/useGlbScene.js', () => ({
  useGlbScene: () => ({ scene: loaded.scene, revision: loaded.revision, busy: false, error: null, progress: null })
}));
// The renderer's own clips (its analysis's routine) are kept to be played by hand.
vi.mock('../../../dist/renderers/glb/useGlbAnimation.js', () => ({ useGlbAnimation: (_document: any, _render: any, own: any) => { loaded.own = own; return loaded.animation; } }));
import GlbRenderer from '../../../dist/renderers/glb/GlbRenderer.js';
import { writeFileView } from '../../../dist/renderers/kit/shell/fileView.js';
import { createAnimationClock } from '../../../dist/renderers/kit/tools/playbar/animationClock.js';
import { ViewerElementContext, ViewerHostContext } from '../../../dist/host/context.js';
import { testHost } from '../../../dist/host/testing/host.js';
import * as THREE from 'three';

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
});
afterEach(() => { vi.restoreAllMocks(); loaded.animation = null; loaded.runtime = null; loaded.host = null; cleanup(); vi.unstubAllGlobals(); document.querySelectorAll('[data-test-navbar]').forEach(slot => slot.remove()); });

// Two triangles the way GLTFLoader hands a result over: lower-cased custom attributes, extras in userData.
// `faces`: the source face of each vertex (`_FACE`), for a result that records its study.
// `attributes`: what another analysis's result carries instead, by name: values and item size (null drops one).
function resultRoot(extras: Record<string, unknown> | null, faces: number[] | null = null, attributes: Record<string, [number[], number] | null> = {}) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0]), 3));
  geometry.setIndex([0, 1, 2, 1, 3, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(16).fill(7), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0, 50, 100, 25]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array([0, 0, 0, 0, 0, 0.001, 0, 0, 0.002, 0, 0, 0.0005]), 3));
  if (faces) geometry.setAttribute('_face', new BufferAttribute(new Float32Array(faces), 1));
  for (const [name, values] of Object.entries(attributes)) {
    if (values) geometry.setAttribute(name, new BufferAttribute(new Float32Array(values[0]), values[1]));
    else geometry.deleteAttribute(name);
  }
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
// The viewer's own element, which the shell asks whose Escape it is.
function ViewerElement({ children }: { children: React.ReactNode }) {
  const element = useRef<HTMLDivElement | null>(null);
  return <ViewerElementContext.Provider value={element}><div ref={element}>{children}</div></ViewerElementContext.Provider>;
}
const colourBytes = (mesh: Mesh) => Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);

function mount(extras: Record<string, unknown> | null, state?: unknown, { actions = () => {}, host = testHost(), faces = null, settings = { toolStack: { panels: {}, collapsed: {} } }, attributes = {} }: { actions?: (actions: readonly any[]) => void, host?: any, faces?: number[] | null, settings?: any, attributes?: Record<string, [number[], number] | null> } = {}) {
  const built = resultRoot(extras, faces, attributes);
  loaded.root = built.root;
  // One scene per file, as the hook holds it: a render is not a new result.
  loaded.scene = { document: { scene: built.root }, revision: loaded.revision };
  const slot = document.createElement('div');
  slot.setAttribute('data-test-navbar', '');
  document.body.append(slot);
  const save = vi.fn();
  // The tab's settings, as a store: a closed or resized panel is written back and read again.
  let snapshot = settings;
  const listeners = new Set<() => void>();
  const preferences = { getSnapshot: () => snapshot, subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
    update(patch: any) { snapshot = { ...snapshot, ...patch }; listeners.forEach(listener => listener()); } };
  const catalog = { entries: [], error: null };
  const client = { resources: {}, subscribe: () => () => {}, getSnapshot: () => catalog };
  const props = { source: { id: 'one' }, file: { path: '/models/part.glb', name: 'part.glb', kind: 'file' }, document: null, navbarSlot: slot,
    onReady() {}, onOpenFile() {}, appearance: { colorScheme: 'light' }, state, onStateChange: save, onNavigationActionsChange: actions, reload() {},
    data: { client, entry: { path: '/models/part.glb', hash: 'h' }, services: { preferences } } };
  const view = render(<ViewerHostContext.Provider value={host}><ViewerElement><GlbRenderer {...(props as any)} /></ViewerElement></ViewerHostContext.Provider>);
  return { ...view, ...built, save };
}
const openDisplay = () => act(() => { fireEvent.click(screen.getByRole('button', { name: 'Display' })); });
const studyPanel = () => screen.queryByRole('region', { name: 'Study' });
const rowTexts = (panel: HTMLElement) => Array.from(panel.querySelectorAll('[data-study-row]')).map(row => row.textContent);

it('puts the field and deformation in Study, under Select, and on the view a colour bar that is only the scale', () => {
  const { container } = mount(RESULT);
  const bar = container.querySelector('[role="group"][aria-label="von Mises stress colour bar"]')!;
  // The field in Show's words and its range; what it means for the part is the verdict's.
  expect(bar.textContent).toBe('Stress047.3 MPa');
  // The bar is a reading: nothing on it to press or drag.
  expect(bar.querySelectorAll('button, input, [role="slider"], [role="combobox"]').length).toBe(0);
  expect(screen.getByRole('button', { name: 'Select' }).getAttribute('aria-pressed')).toBe('true');
  const study = studyPanel()!;
  // The field in plain words: the file's own name is the colour bar's.
  expect(study.querySelector('[role="combobox"][aria-label="Result field"]')!.textContent).toBe('Stress');
  expect(study.querySelector('[role="slider"][aria-label="Deformation scale"]')).toBeTruthy();
  // Display is the view's alone: no Analysis section, no second field select.
  openDisplay();
  expect(screen.queryByText('Analysis')).toBeNull();
  expect(screen.getAllByRole('combobox', { name: 'Result field' })).toHaveLength(1);
});

it('the field switch recolours the mesh and changes the bar\'s field and range', () => {
  const { mesh, container } = mount(RESULT);
  const stress = colourBytes(mesh);
  expect(stress.slice(0, 4)).toEqual([13, 26, 230, 255]);
  act(() => { fireEvent.click(screen.getByRole('combobox', { name: 'Result field' })); });
  act(() => { fireEvent.click(screen.getByRole('option', { name: 'Displacement' })); });
  expect(colourBytes(mesh)).not.toEqual(stress);
  const bar = container.querySelector('[role="group"][aria-label="displacement colour bar"]')!;
  expect(bar.querySelector('[data-fea-field]')!.textContent).toBe('Displacement');
  expect(bar.querySelector('[data-fea-max]')!.textContent).toBe('0.0288 mm');
});

it('the deformation value rescales the drawn displacement from the file\'s positions, and the choice is saved with the file', () => {
  vi.useFakeTimers();
  const { mesh, save } = mount(RESULT);
  const position = mesh.geometry.getAttribute('position');
  const value = screen.getByRole('textbox', { name: 'Deformation scale value' });
  act(() => { fireEvent.change(value, { target: { value: '0' } }); fireEvent.blur(value); });
  // 10x of vertex 2's 0.002 m is baked in; at 0x it is back where it was.
  expect(position.getZ(2)).toBeCloseTo(-0.02, 6);
  act(() => { vi.advanceTimersByTime(500); });
  vi.useRealTimers();
  expect(save.mock.calls.at(-1)![0].renderer.fea.value).toMatchObject({ field: null, scale: 0, loadScale: null, threshold: null });
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

it('a GLB that is not a result has no colour bar, no Select tool, no Study and its colours untouched', () => {
  const { mesh, container } = mount(null);
  expect(container.querySelector('[aria-label$="colour bar"]')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Select' })).toBeNull();
  expect(studyPanel()).toBeNull();
  openDisplay();
  expect(screen.queryByText('Analysis')).toBeNull();
  expect(colourBytes(mesh).every(byte => byte === 7)).toBe(true);
});

it('the colour bar steps up above the playbar while it is there, in preview, and a stored scale is held to the slider\'s range', () => {
  const plain = mount(RESULT);
  const low = (plain.container.querySelector('[aria-label$="colour bar"]')!.parentElement as HTMLElement).style.bottom;
  expect(low).toBe('var(--cad-viewport-bottom-center, 1.75rem)');
  cleanup();
  loaded.animation = { clips: [{ id: 'a', label: 'Load ramp', duration: 2 }], activeClipId: 'a', clock: createAnimationClock(), speed: 1, loopEnabled: true,
    onClipSelect() {}, onPlayToggle() {}, onScrub() {}, onSpeedChange() {}, onLoopToggle() {}, onRelease() {} };
  const stored = writeFileView({ renderer: { fea: { field: null, scale: 9999 } }, signatures: { fea: '_von_mises,_displacement:10' } });
  const animated = mount(RESULT, stored);
  const bottom = () => (animated.container.querySelector('[aria-label$="colour bar"]')!.parentElement as HTMLElement).style.bottom;
  // Out of preview there is no playbar under the model to clear.
  expect(bottom()).toBe(low);
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Preview' })); });
  const high = bottom();
  expect(high).not.toBe(low);
  expect(high).toContain('3rem');
  // The slider tops out at four times the file's own 10x.
  expect(animated.mesh.geometry.getAttribute('position').getZ(2)).toBeCloseTo(0.06, 6);
});

// What the result's checks found stays in the file for the agent; the viewer's status is Study's verdict.
const PEAK = { check: 'fea', severity: 'error', type: 'peak', summary: 'The peak stress, 120 MPa, is above the 100 MPa this material yields at',
  description: 'The peak stress is above yield.', items: [{ text: 'the peak stress', ref: '#o1.f3', at: [10, 20, 30] }] };
const SOFT = { check: 'fea', severity: 'warning', type: 'bend', summary: 'The part bends visibly: 0.4 mm', description: 'It bends.', items: [{ text: 'the tip', ref: null }] };
const FOUND = { ...RESULT, document: 'part.step', occurrence: 'o1' };

it('a result with findings raises no alert card and puts no findings icon in the navbar', () => {
  const actions = vi.fn();
  mount({ ...FOUND, findings: [PEAK, SOFT] }, undefined, { actions });
  expect(screen.queryByRole('alert')).toBeNull();
  expect(screen.queryByText(PEAK.summary)).toBeNull();
  expect(actions.mock.calls.flat(2).filter((action: any) => action?.label)).toEqual([]);
});

it('lays the deformation slider out as Display\'s sliders are: under its label, never on its row', () => {
  mount(RESULT);
  const label = screen.getByText('Deformation');
  const thumb = screen.getByRole('slider', { name: 'Deformation scale' });
  const slider = thumb.closest('[data-slot="slider"]')!;
  const column = label.closest('[data-position-control] > div')!;
  // Same silhouette as FileSheetSliderField's other uses: label and slider are separate blocks in one column ...
  expect(slider.contains(label) || label.contains(slider)).toBe(false);
  expect(column.contains(slider)).toBe(true);
  expect(label.parentElement).toBe(column);
  expect(slider.parentElement!.parentElement).toBe(column);
  expect(slider.parentElement!.previousElementSibling).toBe(label);
  // ... and the slider carries the precision-slider height (h-4), so it is no taller than the gap pulled up under the label.
  expect(slider.classList.contains('h-4')).toBe(true);
});

// What S1 adds: the study the result was solved for, and the face each vertex lies on.
const STUDY = {
  material: { name: '6061-T6', yield_MPa: 276, youngs_GPa: 68.9, poisson: 0.33 },
  fixtures: [{ type: 'fixed', faces: ['#o1.f1'] }],
  loads: [{ type: 'force', faces: ['#o1.f2'], vector_N: [0, 0, -2500] }],
  mesh: { size_mm: 1.9205, order: 2, elements: 52271, refined_from_mm: 2.7686 },
  margin: 2,
};
const STUDIED = { ...FOUND, study: STUDY, faces: ['#o1.f1', '#o1.f2'] };
// Vertices 0-2 lie on face index 0 (#o1.f1), vertex 3 on face index 1 (#o1.f2).
const FACES = [0, 0, 0, 1];
async function copiedPrompt(copied: string[]) {
  act(() => { fireEvent.change(screen.getByRole('textbox', { name: 'Describe your changes' }), { target: { value: 'move it' } }); });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy Prompt' })); });
  return copied.at(-1);
}
const clipboardHost = (copied: string[]) => testHost({ clipboard: { writeText: async (text: any) => { copied.push(await text); }, readText: async () => '', writeImage: async () => {} } });

it('Study reads in plain words: where it is held, what pushes it and what it is made of, then What you see, then Details, shut', () => {
  mount(STUDIED, undefined, { faces: FACES });
  const study = studyPanel()!;
  expect(study.querySelector('h3')!.textContent).toBe('Study');
  expect(study.querySelector('button[aria-label="Close study"]')).toBeTruthy();
  // Each heading with the glyph its marker is drawn as, each face by name under it, a load as how much and
  // which way with its faces shut under it, the material's name; the mesh is Details', shut.
  const plain = () => rowTexts(study).map(text => text!.replace(/\u2011/g, '-'));
  expect(plain()).toEqual(['Held at', 'Face 1', 'Pushed', '2500 N down', 'Made of', '6061-T6', 'What you see', 'Details']);
  expect(Array.from(study.querySelectorAll('[data-study-heading]')).map(row => [row.textContent, Boolean(row.querySelector('svg'))]))
    .toEqual([['Held at', true], ['Pushed', true], ['Made of', true]]);
  // The old jargon is gone.
  for (const word of ['Fixed', 'Loads', 'Material', 'Result', 'Mesh']) expect(screen.queryByText(word, { exact: true })).toBeNull();
  expect(study.querySelector('[role="combobox"][aria-label="Result field"]')).toBeTruthy();
  // The load's faces open by its chevron.
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Expand 2500 N down' })); });
  expect(plain()).toEqual(['Held at', 'Face 1', 'Pushed', '2500 N down', 'Face 2', 'Made of', '6061-T6', 'What you see', 'Details']);
  // Details opens by its chevron, the mesh's size there, how it got there its hint.
  expect(screen.getByRole('button', { name: 'Expand Details' }).getAttribute('aria-expanded')).toBe('false');
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Expand Details' })); });
  expect(plain().slice(-2)).toEqual(['Details', 'Mesh1.9 mm elements']);
  // It opens at its content's height, so Result's slider is not under its foot; a person's own cap still holds.
  expect(study.style.maxHeight).toBe('');
  cleanup();
  mount(STUDIED, undefined, { faces: FACES, settings: { toolStack: { panels: { tree: { height: 200 } }, collapsed: {} } } });
  expect(studyPanel()!.style.maxHeight).toBe('200px');
});

it('a face both fixed and loaded is named for both, chosen from either row or picked', async () => {
  const copied: string[] = [];
  const both = { ...STUDY, loads: [{ type: 'force', faces: ['#o1.f1'], vector_N: [0, 0, -2500] }] };
  mount({ ...STUDIED, study: both }, undefined, { faces: FACES, host: clipboardHost(copied) });
  act(() => { fireEvent.click(screen.getAllByRole('button', { name: 'Select Face 1' })[0]); });
  expect(await copiedPrompt(copied)).toBe('move it\n\nFile: /models/part.glb\nReferences:\nFixed and loaded face 1 · /models/part.step#o1.f1');
});

it('a result written before its study was recorded shows Study with the Result alone', () => {
  mount(FOUND);
  const study = studyPanel()!;
  expect(rowTexts(study)).toEqual(['What you see']);
  expect(study.querySelector('[role="slider"][aria-label="Deformation scale"]')).toBeTruthy();
});

it('choosing a fixed face tints only its triangles and carries it into Quick Edit by the source STEP', async () => {
  const copied: string[] = [];
  const { mesh } = mount(STUDIED, undefined, { faces: FACES, host: clipboardHost(copied) });
  const plain = colourBytes(mesh);
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Select Face 1' })); });
  const tinted = colourBytes(mesh);
  // Face index 0's vertices change; vertex 3, face index 1's, keeps its colour.
  for (const vertex of [0, 1, 2]) expect(tinted.slice(vertex * 4, vertex * 4 + 3)).not.toEqual(plain.slice(vertex * 4, vertex * 4 + 3));
  expect(tinted.slice(12)).toEqual(plain.slice(12));
  expect(screen.getByRole('button', { name: 'Select Face 1' }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('region', { name: 'Quick Edit' }).querySelector('[data-quick-edit-chip="references"]')!.textContent).toBe('1 ref');
  expect(await copiedPrompt(copied)).toBe('move it\n\nFile: /models/part.glb\nReferences:\nFixed face 1 · /models/part.step#o1.f1');
  // Escape lets go, and the colours come back.
  act(() => { fireEvent.keyDown(document.querySelector('[data-stand-in-viewport]')!, { key: 'Escape' }); });
  expect(colourBytes(mesh)).toEqual(plain);
  expect(screen.getByRole('button', { name: 'Select Face 1' }).getAttribute('aria-pressed')).toBe('false');
});

it('choosing a load tints its face and says how much, on which face', async () => {
  const copied: string[] = [];
  const { mesh } = mount(STUDIED, undefined, { faces: FACES, host: clipboardHost(copied) });
  const plain = colourBytes(mesh);
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Select 2500 N down' })); });
  expect(colourBytes(mesh).slice(0, 12)).toEqual(plain.slice(0, 12));
  expect(colourBytes(mesh).slice(12, 15)).not.toEqual(plain.slice(12, 15));
  expect(await copiedPrompt(copied)).toBe('move it\n\nFile: /models/part.glb\nReferences:\n2500 N load on face 2 · /models/part.step#o1.f2');
});

it('a press on the result with Select picks the face under it into a Reference with its ref, its role and Copy', async () => {
  const copied: string[] = [];
  const host = document.createElement('div');
  host.getBoundingClientRect = () => ({ left: 0, top: 0, width: 800, height: 600, right: 800, bottom: 600, x: 0, y: 0, toJSON() {} });
  const canvas = document.createElement('canvas');
  host.append(canvas);
  document.body.append(host);
  // Looking down at the first triangle (face index 0) from above its middle.
  const camera = new THREE.OrthographicCamera(-0.5, 0.5, 0.375, -0.375, 0.001, 10);
  camera.position.set(0.25, 0.25, 1);
  camera.updateMatrixWorld();
  loaded.runtime = { THREE, camera, renderer: { domElement: canvas } };
  loaded.host = host;
  mount(STUDIED, undefined, { faces: FACES, host: clipboardHost(copied) });
  act(() => {
    fireEvent.pointerDown(canvas, { button: 0, pointerId: 1, clientX: 400, clientY: 300 });
    fireEvent.pointerUp(canvas, { button: 0, pointerId: 1, clientX: 400, clientY: 300 });
  });
  const reference = screen.getByRole('region', { name: 'Reference details' });
  expect(reference.querySelector('h3')!.textContent).toBe('Face 1');
  expect(Array.from(reference.querySelectorAll('[data-info-row]')).map(row => row.textContent)).toEqual(['Ref#o1.f1', 'Studyfixed']);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy' })); });
  expect(copied).toEqual(['/models/part.step#o1.f1']);
  expect(screen.getByRole('button', { name: 'Select Face 1' }).getAttribute('aria-pressed')).toBe('true');
  host.remove();
});

// Looking down at the first triangle (face index 0) from above its middle, for a press on the result.
function pressOnTheResult(mounting: () => void) {
  const host = document.createElement('div');
  host.getBoundingClientRect = () => ({ left: 0, top: 0, width: 800, height: 600, right: 800, bottom: 600, x: 0, y: 0, toJSON() {} });
  const canvas = document.createElement('canvas');
  host.append(canvas);
  document.body.append(host);
  const camera = new THREE.OrthographicCamera(-0.5, 0.5, 0.375, -0.375, 0.001, 10);
  camera.position.set(0.25, 0.25, 1);
  camera.updateMatrixWorld();
  loaded.runtime = { THREE, camera, renderer: { domElement: canvas } };
  loaded.host = host;
  mounting();
  act(() => {
    fireEvent.pointerDown(canvas, { button: 0, pointerId: 1, clientX: 400, clientY: 300 });
    fireEvent.pointerUp(canvas, { button: 0, pointerId: 1, clientX: 400, clientY: 300 });
  });
  return () => host.remove();
}

const ASSEMBLED = {
  ...STUDIED, faces: ['#o1.1.f1', '#o1.2.f1', '#o1.1.f9'], weakest_part: 'post', weakest_part_peak_MPa: 180, safety_factor: 1.46, max_displacement_mm: 0.2,
  parts: [
    { ref: '#o1.1', name: 'post', material: '6061-T6', yield_MPa: 276, peak_MPa: 180, safety_factor: 1.46, max_displacement_mm: 0.2 },
    { ref: '#o1.2', name: 'base', material: 'Steel', yield_MPa: 250, peak_MPa: 40, safety_factor: 2.5, max_displacement_mm: 0.01 },
  ],
  connections: [{ between: ['#o1.1', '#o1.2'], names: ['post', 'base'], type: 'bonded', area_mm2: 100, gap_mm: 0, faces: ['#o1.1.f1', '#o1.2.f1'] }],
};
// Two parts would have no Parts panel (it shows from six up); the view asks for it.
function mountAssembly(copied: string[], extras: Record<string, unknown> = { view: { show: { parts: true } } }) {
  const built = mount({ ...ASSEMBLED, ...extras }, undefined, { faces: [0, 0, 2, 1], host: clipboardHost(copied) });
  built.mesh.geometry.setAttribute('_part', new BufferAttribute(new Float32Array([0, 0, 0, 1]), 1));
  return built;
}

const partsPanel = () => screen.queryByRole('region', { name: 'Parts' });

it('an assembly has a Parts panel above Study, each part with its joints, the weakest open, and Study holds only the study', () => {
  mountAssembly([]);
  const parts = partsPanel()!;
  const study = studyPanel()!;
  expect(parts.querySelector('h3')!.textContent).toBe('Parts');
  expect(parts.querySelector('button[aria-label="Close parts"]')).toBeTruthy();
  expect(parts.compareDocumentPosition(study) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  // The weakest part (post) opens with its joint under it, naming only the other part; base starts shut.
  const plain = (panel: HTMLElement) => rowTexts(panel).map(text => text!.replace(/\u2011/g, '-').replace(/\u00a0/g, ' '));
  expect(plain(parts)).toEqual(['post6061-T6 · holds 1.4×', '↔ basebonded · 100 mm²', 'baseSteel · holds 2.5×']);
  expect(parts.querySelector('[data-study-row="part:0"] [data-study-detail]')!.className).not.toMatch(/truncate|ellipsis|overflow-hidden|whitespace-nowrap/);
  // Opened, base lists the same joint, naming post.
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Expand base' })); });
  expect(plain(parts).slice(2)).toEqual(['baseSteel · holds 2.5×', '↔ postbonded · 100 mm²']);
  // Study no longer lists parts or joints; what the parts are made of, which differ, is how many.
  expect(study.querySelector('[data-study-row="material:name"]')!.textContent!.replace(/\u00a0/g, ' ')).toBe('2 materials');
  expect(study.querySelector('[data-study-row^="part:"], [data-study-row^="joint:"], [data-study-row="parts"], [data-study-row="connections"]')).toBeNull();
});

it('Select carries the mark while Parts or Study is closed, and a press brings back the closed ones', () => {
  mountAssembly([]);
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Close parts' })); });
  expect(partsPanel()).toBeNull();
  expect(studyPanel()).toBeTruthy();
  const select = screen.getByRole('button', { name: 'Select' });
  expect(select.getAttribute('aria-description')).toBe('Parts closed');
  act(() => { fireEvent.click(select); });
  expect(partsPanel()).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Select' }).getAttribute('aria-description')).toBeNull();
});

it('an assembly shows Parts from six parts up, and its view can show or hide it either way', () => {
  const more = (count: number) => Array.from({ length: count }, (_, index) => ({ ...ASSEMBLED.parts[index % 2], ref: `#o1.${index + 1}`, name: `part ${index + 1}` }));
  for (const [count, view, shown] of [[4, undefined, false], [6, undefined, true], [4, { show: { parts: true } }, true], [6, { show: { parts: false } }, false]] as const) {
    mountAssembly([], { parts: more(count), ...(view ? { view } : {}) });
    expect(Boolean(partsPanel())).toBe(shown);
    expect(studyPanel()).toBeTruthy();
    cleanup();
  }
});

it('a single part has no Parts panel', () => {
  mount(STUDIED, undefined, { faces: FACES });
  expect(partsPanel()).toBeNull();
  expect(studyPanel()).toBeTruthy();
});

it('with Parts hidden, a face picked on an assembly names its part, and the Reference says the part\'s material and what it holds', () => {
  const release = pressOnTheResult(() => { mountAssembly([], {}); });
  expect(partsPanel()).toBeNull();
  const reference = screen.getByRole('region', { name: 'Reference details' });
  expect(reference.querySelector('h3')!.textContent).toBe('post · face 1');
  const rows = Array.from(reference.querySelectorAll('[data-info-row]')).map(row => row.textContent!.replace(/\u2011/g, '-').replace(/\u00a0/g, ' '));
  expect(rows).toEqual(['Ref#o1.1.f1', 'Studyfree', 'Part6061-T6 · holds 1.4×']);
  release();
});

it('choosing a part tints its triangles and carries it into Quick Edit', async () => {
  const copied: string[] = [];
  const { mesh } = mountAssembly(copied);
  const plain = colourBytes(mesh);
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Select post' })); });
  const tinted = colourBytes(mesh);
  for (const vertex of [0, 1, 2]) expect(tinted.slice(vertex * 4, vertex * 4 + 3)).not.toEqual(plain.slice(vertex * 4, vertex * 4 + 3));
  expect(tinted.slice(12)).toEqual(plain.slice(12));
  expect(await copiedPrompt(copied)).toBe("move it\n\nFile: /models/part.glb\nReferences:\nPart 'post' · /models/part.step#o1.1");
});

it('choosing a joint tints both sides\' interface faces and carries both parts into Quick Edit', async () => {
  const copied: string[] = [];
  const { mesh } = mountAssembly(copied);
  const plain = colourBytes(mesh);
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Select post ↔ base' })); });
  const joint = colourBytes(mesh);
  // Vertex 2 lies on a face that is no interface but is the post's: tinted lightly, so between the plain
  // colour and the interface vertices' full tint, and the base's vertex 3 on its interface face is full.
  const channel = (vertex: number) => joint[vertex * 4] - plain[vertex * 4];
  expect(joint.slice(8, 11)).not.toEqual(plain.slice(8, 11));
  for (const vertex of [0, 1, 3]) expect(joint.slice(vertex * 4, vertex * 4 + 3)).not.toEqual(plain.slice(vertex * 4, vertex * 4 + 3));
  expect(Math.abs(channel(2))).toBeLessThan(Math.abs(channel(0)));
  expect(await copiedPrompt(copied)).toBe("move it\n\nFile: /models/part.glb\nReferences:\nBonded joint between 'post' and 'base' · /models/part.step#o1.1.f1,o1.2.f1");
});

it('a joint chosen under either of its parts is the same choice: both copies pressed, the same refs', async () => {
  const copied: string[] = [];
  mountAssembly(copied);
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Expand base' })); });
  const copies = screen.getAllByRole('button', { name: 'Select post ↔ base' });
  expect(copies).toHaveLength(2);
  act(() => { fireEvent.click(copies[1]); });
  for (const copy of screen.getAllByRole('button', { name: 'Select post ↔ base' })) expect(copy.getAttribute('aria-pressed')).toBe('true');
  expect(await copiedPrompt(copied)).toBe("move it\n\nFile: /models/part.glb\nReferences:\nBonded joint between 'post' and 'base' · /models/part.step#o1.1.f1,o1.2.f1");
});

// The study's view: the agent chooses What you see's controls, their order, ranges and words, and named presets.
const VIEWED = {
  ...RESULT,
  view: {
    controls: [
      { drives: 'load_scale', type: 'number', label: 'Rider weight', min: 0.5, max: 3, default: 1, unit: '×' },
      { drives: 'gravity', type: 'number', label: 'Gravity', max: 2 },
      { drives: 'field', type: 'enum', label: 'Show', options: ['von_mises', 'displacement'], default: 'von_mises' },
      { drives: 'deformation', type: 'slider', label: 'Wobble', max: 9 },
      { drives: 'threshold', type: 'number', label: 'Show above', field: 'von_mises', min: 0, max: 100, default: 40, unit: 'MPa' },
      { drives: 'deformation', type: 'number', label: 'Exaggerate', min: 0, max: 50, default: 12 },
    ],
    presets: [{ label: 'Landing (3×)', load_scale: 3 }],
  },
};
const resultRows = () => Array.from(studyPanel()!.querySelectorAll('[data-study-result] [data-position-control], [data-study-result] [role="combobox"]'));
const setValue = (name: string, value: string) => act(() => {
  const box = screen.getByRole('textbox', { name });
  fireEvent.change(box, { target: { value } });
  fireEvent.blur(box);
});
const choose = (combobox: string, option: string) => {
  act(() => { fireEvent.click(screen.getByRole('combobox', { name: combobox })); });
  act(() => { fireEvent.click(screen.getByRole('option', { name: option })); });
};

it('Result shows the view\'s controls in its order, with its words and ranges, skipping what it does not know; no view shows today\'s two', () => {
  mount(VIEWED);
  const sliders = screen.getAllByRole('slider');
  expect(sliders.map(slider => slider.getAttribute('aria-label'))).toEqual(['Rider weight', 'Show above', 'Exaggerate']);
  expect(sliders.map(slider => [slider.getAttribute('aria-valuemin'), slider.getAttribute('aria-valuemax'), slider.getAttribute('aria-valuenow')]))
    .toEqual([['0.5', '3', '1'], ['0', '100', '40'], ['0', '50', '12']]);
  // In the view's order: the preset, the load, the field, the threshold, the deformation.
  expect(resultRows().map(row => row.textContent?.replace(/\s+/g, ' ').trim())).toEqual(
    ['Default', 'Rider weight', 'Stress', 'Show above', 'Exaggerate']);
  expect(screen.queryByRole('slider', { name: 'Gravity' })).toBeNull();
  expect(screen.queryByRole('slider', { name: 'Wobble' })).toBeNull();
  expect(screen.getByRole('textbox', { name: 'Rider weight slider value' }).getAttribute('value')).toBe('×1.00');
  expect(screen.getByRole('textbox', { name: 'Show above slider value' }).getAttribute('value')).toBe('40.0 MPa');
  cleanup();
  mount(RESULT);
  expect(screen.getAllByRole('slider').map(slider => slider.getAttribute('aria-label'))).toEqual(['Deformation scale']);
  expect(screen.getByRole('slider', { name: 'Deformation scale' }).getAttribute('aria-valuemax')).toBe('40');
  expect(screen.getByRole('textbox', { name: 'Deformation scale value' }).getAttribute('value')).toBe('×10.0');
  expect(screen.queryByRole('combobox', { name: 'Preset' })).toBeNull();
});

it('each slider\'s thumb stands at its control\'s value, and the slider takes the row\'s whole width under its label and value field', () => {
  mount(VIEWED);
  const now = () => screen.getAllByRole('slider').map(slider => slider.getAttribute('aria-valuenow'));
  expect(now()).toEqual(['1', '40', '12']);
  setValue('Exaggerate slider value', '24');
  setValue('Rider weight slider value', '2.5');
  expect(now()).toEqual(['2.5', '40', '24']);
  choose('Preset', 'Landing (3×)');
  expect(now()).toEqual(['3', '40', '12']);
  // The label and the value field share the first line; the slider is the second, both columns wide.
  const row = screen.getByRole('slider', { name: 'Exaggerate' }).closest('[data-slider-layout="wide"]')!;
  const [label, value, sliderBox] = Array.from(row.children);
  expect(label.textContent).toBe('Exaggerate');
  expect(value.contains(screen.getByRole('textbox', { name: 'Exaggerate slider value' })) || value === screen.getByRole('textbox', { name: 'Exaggerate slider value' })).toBe(true);
  expect(sliderBox.className).toContain('col-span-2');
  expect(sliderBox.querySelector('[data-slot="slider"]')).toBeTruthy();
});

it('at twice the load, the bar and the deformation are twice the solved ones, what each part holds is half, and a part flips to yields', () => {
  const parts = [{ ref: '#o1.1', name: 'post', material: 'steel', safety_factor: 5.83 }, { ref: '#o1.2', name: 'base', material: 'steel', safety_factor: 1.5 }];
  const { container, mesh } = mount({ ...VIEWED, view: { controls: [VIEWED.view.controls[0], VIEWED.view.controls[5]], show: { parts: true } }, parts });
  const colours = colourBytes(mesh);
  const tip = mesh.geometry.getAttribute('position').getZ(2);
  const partDetails = () => Array.from(screen.getByRole('region', { name: 'Parts' }).querySelectorAll('[data-study-detail]')).map(detail => detail.textContent!.replace(/\u00a0/g, ' '));
  expect(partDetails()).toEqual(['steel · holds 5.8×', 'steel · holds 1.5×']);
  setValue('Rider weight slider value', '2');
  expect(container.querySelector('[data-fea-max]')!.textContent).toBe('94.6 MPa');
  expect(partDetails()).toEqual(['steel · holds 2.9×', 'steel · yields']);
  // The colours keep their place on a bar that now reads twice as high; the displacement is drawn twice as far.
  expect(colourBytes(mesh)).toEqual(colours);
  // The file baked in 10x of vertex 2's 0.002 m: 12x at the solved load, 24x at twice it.
  expect(tip).toBeCloseTo(0.002 * (12 - 10), 6);
  expect(mesh.geometry.getAttribute('position').getZ(2)).toBeCloseTo(0.002 * (24 - 10), 6);
});

it('a threshold greys every vertex whose value is under it, and the load moves what is over it', () => {
  const { mesh } = mount({ ...VIEWED, view: { controls: [VIEWED.view.controls[0], VIEWED.view.controls[4]] } });
  const grey = () => [0, 1, 2, 3].map(vertex => colourBytes(mesh).slice(vertex * 4, vertex * 4 + 3).every(byte => byte === 150));
  // 0, 50, 100 and 25 MPa against 40.
  expect(grey()).toEqual([true, false, false, true]);
  setValue('Rider weight slider value', '2');
  expect(grey()).toEqual([true, false, false, false]);
  setValue('Show above slider value', '0');
  expect(grey()).toEqual([false, false, false, false]);
});

it('a preset sets the values it names, and moving any control is Custom', () => {
  const { container } = mount(VIEWED);
  choose('Preset', 'Landing (3×)');
  expect(screen.getByRole('textbox', { name: 'Rider weight slider value' }).getAttribute('value')).toBe('×3.00');
  expect(container.querySelector('[data-fea-max]')!.textContent).toBe('142 MPa');
  expect(screen.getByRole('combobox', { name: 'Preset' }).textContent).toBe('Landing (3×)');
  setValue('Exaggerate slider value', '20');
  expect(screen.getByRole('combobox', { name: 'Preset' }).textContent).toBe('Custom');
  choose('Preset', 'Default');
  expect(screen.getByRole('textbox', { name: 'Rider weight slider value' }).getAttribute('value')).toBe('×1.00');
  expect(screen.getByRole('combobox', { name: 'Preset' }).textContent).toBe('Default');
});

it('draws the loads and fixtures on the model, the chosen load\'s arrows in the chosen colour, and Display\'s switch hides them', () => {
  const both = { ...STUDY, loads: [{ type: 'force', faces: ['#o1.f1'], vector_N: [0, 0, -2500] }] };
  const { mesh, unmount } = mount({ ...STUDIED, study: both }, undefined, { faces: [0, 0, 0, 0] });
  const group = mesh.children.find(child => child.name === 'fea-markers')!;
  const [shafts, heads, cones] = group.children as THREE.InstancedMesh[];
  expect([shafts.visible, heads.visible, cones.visible]).toEqual([true, true, true]);
  expect([heads.count, cones.count]).toEqual([2, 2]);
  const colour = new THREE.Color();
  heads.getColorAt(0, colour);
  expect(colour.getHexString()).toBe('18181b');
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Select 2500 N down' })); });
  heads.getColorAt(0, colour);
  expect(colour.getHexString()).toBe('ff40f2');
  cones.getColorAt(0, colour);
  expect(colour.getHexString()).toBe('71717a');
  // The arrows stand on the deformed face: drawn at 0x, they come back with it.
  const before = new THREE.Matrix4();
  heads.getMatrixAt(0, before);
  setValue('Deformation scale value', '0');
  const after = new THREE.Matrix4();
  heads.getMatrixAt(0, after);
  expect(new THREE.Vector3().setFromMatrixPosition(after).z).toBeLessThan(new THREE.Vector3().setFromMatrixPosition(before).z);
  openDisplay();
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Disable Loads and fixtures' })); });
  expect(group.children.map(child => child.visible)).toEqual([false, false, false, false, false, false]);
  unmount();
  expect(group.parent).toBeNull();
});

it('a view that turns the markers off opens with the switch off', () => {
  const both = { ...STUDY, loads: [{ type: 'force', faces: ['#o1.f1'], vector_N: [0, 0, -2500] }] };
  const { mesh } = mount({ ...STUDIED, study: both, view: { show: { loads: false, fixtures: false } } }, undefined, { faces: [0, 0, 0, 0] });
  const group = mesh.children.find(child => child.name === 'fea-markers')!;
  expect(group.children.map(child => child.visible)).toEqual([false, false, false, false, false, false]);
  openDisplay();
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Enable Loads and fixtures' })); });
  expect(group.children.map(child => child.visible)).toEqual([true, true, true, true, true, true]);
});

// The answer at a glance, at the top of Study: its headline, the load the weakest check takes, then each check.
const verdictOf = () => {
  const section = screen.getByRole('region', { name: 'Verdict' });
  const text = (key: string) => section.querySelector(`[data-fea-verdict-${key}]`)?.textContent ?? null;
  const rows = Array.from(section.querySelectorAll('[data-fea-check]')).map(row => [row.getAttribute('data-fea-check'),
    row.querySelector('[data-fea-check-label]')!.textContent, row.querySelector('[data-fea-check-line]')!.textContent!.replace(/\u00a0/g, ' ')]);
  return { status: section.getAttribute('data-fea-verdict'), title: text('title'), caption: text('caption'), rows, section };
};

it('leads Study with the verdict: too weak, close to the limit or strong enough, each in its status tone', () => {
  for (const [factor, status, title, tone] of [[0.68, 'weak', 'Too weak', 'text-error'], [1.5, 'close', 'Close to the limit', 'text-warning'], [5.83, 'strong', 'Strong enough', 'text-success']] as const) {
    mount({ ...STUDIED, safety_factor: factor }, undefined, { faces: FACES });
    const verdict = verdictOf();
    expect([verdict.status, verdict.title]).toEqual([status, title]);
    expect(verdict.section.querySelector('[data-fea-verdict-title]')!.parentElement!.className).toContain(tone);
    expect(verdict.rows).toEqual([[status, 'Strength', '47 MPa, limit 276 MPa']]);
    // It comes before the setup.
    expect(verdict.section.compareDocumentPosition(studyPanel()!.querySelector('[data-study-row="fixed"]')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    cleanup();
  }
});

it('draws how hard each check works: filled to the value over the limit, held at full and striped past it, with a tick at the margin', () => {
  mount({ ...STUDIED, safety_factor: 1.6 }, undefined, { faces: FACES });
  const bar = () => screen.getByRole('meter', { name: 'Strength: how much of its limit' });
  const fill = () => (bar().querySelector('[data-fea-verdict-fill]') as HTMLElement).style.width;
  expect(fill()).toBe('62.5%');
  expect(bar().getAttribute('aria-valuenow')).toBe('63');
  expect(bar().hasAttribute('data-over')).toBe(false);
  // The margin of 2: the tick at half the limit, said to assistive technology.
  expect((bar().querySelector('[data-fea-verdict-tick]') as HTMLElement).style.left).toBe('50%');
  expect(bar().getAttribute('aria-valuetext')).toBe('63% of its limit, your 2× margin at 50%');
  cleanup();
  mount({ ...STUDIED, safety_factor: 0.5 }, undefined, { faces: FACES });
  expect(fill()).toBe('100%');
  expect(bar().getAttribute('aria-valuenow')).toBe('200');
  expect(bar().hasAttribute('data-over')).toBe(true);
  expect(verdictOf().caption).toBe('OK only to 0.5× this load');
});

it('the verdict follows the load control, and can change its word', () => {
  const controls = [VIEWED.view.controls[0]];
  mount({ ...STUDIED, safety_factor: 1.5, view: { controls } }, undefined, { faces: FACES });
  expect([verdictOf().status, verdictOf().caption]).toEqual(['close', 'OK up to 1.5× this load']);
  setValue('Rider weight slider value', '2');
  expect([verdictOf().status, verdictOf().caption, verdictOf().rows]).toEqual(['weak', 'OK only to 0.7× this load', [['weak', 'Strength', '95 MPa, limit 276 MPa']]]);
  setValue('Rider weight slider value', '0.5');
  expect([verdictOf().status, verdictOf().caption]).toEqual(['strong', 'OK up to 3.0× this load']);
});

it('with no stress, says to check the load reaches the part, in no tone and with no bar; an assembly\'s numbers are its weakest part\'s', () => {
  const unloaded = { ...STUDIED, safety_factor: null, fields: [{ ...RESULT.fields[0], max: 0 }, RESULT.fields[1]] };
  mount(unloaded, undefined, { faces: FACES });
  expect(verdictOf()).toMatchObject({ status: 'none', title: 'No stress', caption: 'Check the load reaches the part', rows: [] });
  expect(screen.queryByRole('meter')).toBeNull();
  cleanup();
  // A result with a stress but no safety factor (older than it) has no verdict, and still opens.
  mount({ ...STUDIED, safety_factor: null }, undefined, { faces: FACES });
  expect(screen.queryByRole('region', { name: 'Verdict' })).toBeNull();
  expect(studyPanel()).toBeTruthy();
  cleanup();
  mountAssembly([]);
  expect(verdictOf()).toMatchObject({ status: 'close', rows: [['close', 'Strength', '180 MPa, limit 276 MPa']] });
});

it('a slider\'s thumb stands where its value is on its range, not at the left end', () => {
  mount({ ...RESULT, view: { controls: [VIEWED.view.controls[5], VIEWED.view.controls[0]] } });
  const thumb = (name: string) => screen.getByRole('slider', { name });
  // ×12 on 0 to 50 is 24% along; ×1 on 0.5 to 3 is 20%.
  expect(thumb('Exaggerate').getAttribute('aria-valuenow')).toBe('12');
  expect((thumb('Exaggerate').parentElement as HTMLElement).style.left).toMatch(/^calc\(24% \+ /);
  expect((thumb('Rider weight').parentElement as HTMLElement).style.left).toMatch(/^calc\(20% \+ /);
  setValue('Exaggerate slider value', '50');
  expect((thumb('Exaggerate').parentElement as HTMLElement).style.left).toMatch(/^calc\(100% /);
  // The track it runs along is drawn, unfilled past the thumb, so where the thumb stands reads.
  const track = thumb('Exaggerate').closest('[data-slot="slider"]')!;
  expect(track.className).toContain('[&_[data-slot=slider-track]]:bg-foreground/20');
});

// The checks the study picked, as cadgen judged them: the stress check and a sag on the loaded face.
const STRESS_CHECK = { kind: 'stress', label: 'Strength', value: 47.3, limit: 276, unit: 'MPa', ratio: 0.171527, close_at: 0.5, margin: 2, status: 'passes', where: { ref: '#o1.f1', at: [0, 0, 0] } };
const SAG_CHECK = { kind: 'displacement', label: 'Tip sag', value: 0.62, limit: 0.5, unit: 'mm', ratio: 1.24, close_at: 0.9, status: 'fails', where: { ref: '#o1.f2', at: [1, 0, 0] }, faces: ['#o1.f2'] };
const LOAD_WHEN_FAILING = { drives: 'load_scale', type: 'number', label: 'Load', min: 0.1, max: 2, default: 1, unit: '×', when: 'failing' };

it('heads the verdict with how many checks fail and the load the weakest takes, then each check the same way, all following the load', () => {
  mount({ ...STUDIED, checks: [STRESS_CHECK, SAG_CHECK], view: { controls: [{ ...LOAD_WHEN_FAILING, when: undefined }] } }, undefined, { faces: FACES });
  expect(verdictOf()).toMatchObject({ status: 'weak', title: 'Fails 1 of 2 checks', caption: 'OK only to 0.8× this load',
    rows: [['weak', 'Tip sag', '0.62 mm, limit 0.5 mm'], ['strong', 'Strength', '47 MPa, limit 276 MPa']] });
  // No margin tick on a displacement: its limit is the person's.
  expect(screen.getByRole('meter', { name: 'Tip sag: how much of its limit' }).querySelector('[data-fea-verdict-tick]')).toBeNull();
  expect(screen.getByRole('meter', { name: 'Strength: how much of its limit' }).getAttribute('aria-valuenow')).toBe('17');
  setValue('Load slider value', '0.5');
  expect(verdictOf()).toMatchObject({ status: 'strong', title: 'Passes all checks', caption: 'OK up to 1.6× this load',
    rows: [['strong', 'Tip sag', '0.31 mm, limit 0.5 mm'], ['strong', 'Strength', '24 MPa, limit 276 MPa']] });
});

it('every part of Study is chattable: a check in the verdict, the material and the mesh each go to Quick Edit with what they say', async () => {
  const prompt = async (names: string[]) => {
    cleanup();
    const copied: string[] = [];
    const { mesh } = mount({ ...STUDIED, checks: [STRESS_CHECK, SAG_CHECK] }, undefined, { faces: FACES, host: clipboardHost(copied) });
    const plain = colourBytes(mesh);
    for (const name of names) act(() => { fireEvent.click(screen.getByRole('button', { name })); });
    const tinted = colourBytes(mesh).some((byte, index) => byte !== plain[index]);
    return { tinted, pressed: screen.getByRole('button', { name: names.at(-1) }).getAttribute('aria-pressed'), text: (await copiedPrompt(copied))!.split('\n').at(-1) };
  };
  // A check by the faces it is over, which it tints; another by the face it peaks on.
  expect(await prompt(['Select Tip sag'])).toEqual({ tinted: true, pressed: 'true',
    text: 'Tip sag fails: moves 0.62 mm, limit 0.5 mm (OK only to 0.8× this load) · /models/part.step#o1.f2' });
  expect((await prompt(['Select Strength'])).text).toBe('Strength passes: peak 47 MPa, limit 276 MPa (OK up to 5.8× this load) · /models/part.step#o1.f1');
  // The material and the mesh are about the whole part, so they tint nothing.
  expect(await prompt(['Select 6061-T6'])).toEqual({ tinted: false, pressed: 'true', text: 'Made of 6061-T6 (yield 276 MPa) · /models/part.step#o1' });
  expect((await prompt(['Expand Details', 'Select Mesh'])).text).toBe('Mesh of 1.9 mm elements, refined from 2.8 mm · /models/part.step#o1');
});

it('a result with no checks in the file has today\'s verdict: its one check, from the safety factor', () => {
  mount({ ...STUDIED, safety_factor: 1.5 }, undefined, { faces: FACES });
  expect(verdictOf()).toMatchObject({ status: 'close', title: 'Close to the limit', caption: 'OK up to 1.5× this load', rows: [['close', 'Strength', '47 MPa, limit 276 MPa']] });
  // The verdict leads, then one list: the setup, What you see, Details.
  const body = verdictOf().section.parentElement!.parentElement!;
  expect(body.querySelectorAll('ul[aria-label="Study"]')).toHaveLength(1);
  expect(rowTexts(studyPanel()!).map(text => text!.replace(/‑/g, '-'))).toEqual(['Held at', 'Face 1', 'Pushed', '2500 N down', 'Made of', '6061-T6', 'What you see', 'Details']);
});

it('composes Study from the view\'s sections, in its order, leaving out what it omits and what it does not know', () => {
  mount({ ...STUDIED, view: { sections: ['controls', 'verdict', 'chart'] } }, undefined, { faces: FACES });
  const study = studyPanel()!;
  expect(rowTexts(study)).toEqual(['What you see']);
  const verdict = verdictOf().section;
  expect(study.querySelector('[data-study-row="result"]')!.compareDocumentPosition(verdict) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  cleanup();
  mount({ ...STUDIED, view: { sections: ['setup', 'details'] } }, undefined, { faces: FACES });
  expect(screen.queryByRole('region', { name: 'Verdict' })).toBeNull();
  expect(rowTexts(studyPanel()!).map(text => text!.replace(/‑/g, '-'))).toEqual(['Held at', 'Face 1', 'Pushed', '2500 N down', 'Made of', '6061-T6', 'Details']);
  expect(screen.queryByRole('slider')).toBeNull();
});

it('shows a control `when` the checks say, live with the load, the hidden one drawn at its default and its value kept', () => {
  const threshold = { drives: 'threshold', type: 'number', label: 'Show above', field: 'von_mises', min: 0, max: 100, default: 0, unit: 'MPa', when: 'failing' };
  const { mesh } = mount({ ...STUDIED, checks: [STRESS_CHECK, SAG_CHECK], view: { controls: [LOAD_WHEN_FAILING, threshold] } }, undefined, { faces: FACES });
  const sliders = () => screen.queryAllByRole('slider').map(slider => slider.getAttribute('aria-label'));
  const grey = () => [0, 1, 2, 3].map(vertex => colourBytes(mesh).slice(vertex * 4, vertex * 4 + 3).every(byte => byte === 150));
  // Too much sag as solved: the load and the threshold show.
  expect(sliders()).toEqual(['Load', 'Show above']);
  setValue('Show above slider value', '40');
  expect(grey()).toEqual([true, false, false, true]);
  // At half the load every check passes: the threshold hides and greys nothing, while the load slider stays to be dragged back.
  setValue('Load slider value', '0.5');
  expect(sliders()).toEqual(['Load']);
  expect(grey()).toEqual([false, false, false, false]);
  // Back at the load as solved it fails again, and the threshold returns at the value it had.
  setValue('Load slider value', '1');
  expect(sliders()).toEqual(['Load', 'Show above']);
  expect(screen.getByRole('textbox', { name: 'Show above slider value' }).getAttribute('value')).toBe('40.0 MPa');
  expect(grey()).toEqual([true, false, false, true]);
});

// Track V1: one result per analysis family, each built here as cadgen writes it.
const zOf = (mesh: Mesh, vertex: number) => mesh.geometry.getAttribute('position').getZ(vertex);
const own = () => loaded.own[0];
const play = (seconds: number) => act(() => { own().play.apply(seconds); });
const release = () => act(() => { own().play.release(); });
const barText = (container: HTMLElement) => container.querySelector('[aria-label$="colour bar"]')!.textContent;
const NO_STRESS = { _von_mises: null };

// A modal result: its modes a series, each mode's shape an attribute (mode 1's the displacement the file baked in).
const MODAL = {
  ...STUDIED, safety_factor: null, analysis: { type: 'modal', tier: 1, word: 'Vibration' },
  study: { ...STUDY, loads: [] },
  fields: [{ attribute: '_DISPLACEMENT', name: 'mode shape', units: 'mm', min: 0, max: 1, attribute_scale: 1000, field: 'mode_shape', per_frame: true }],
  series: { kind: 'mode', unit: 'Hz', default: 0, frames: [{ value: 85.2, label: 'Mode 1 · 85 Hz', attributes: { mode_shape: '_DISPLACEMENT' } },
    { value: 118.4, label: 'Mode 2 · 118 Hz', attributes: { mode_shape: '_MODE_SHAPE_F1' } }] },
  checks: [
    { kind: 'frequency', label: '', value: 85.2, limit: 60, unit: 'Hz', ratio: 0.704, close_at: 0.9, status: 'passes', mode: 1, at: { frame: 0, value: 85.2, unit: 'Hz' } },
    { kind: 'frequency', label: 'Motor speed', value: 118.4, limit: 110, unit: 'Hz', ratio: 1.08, close_at: 0.9, status: 'fails', mode: 2, avoid_Hz: [110, 130],
      at: { frame: 1, value: 118.4, unit: 'Hz' }, where: { ref: '#o1.f2' } }],
};
const MODE_2 = { ...NO_STRESS, _mode_shape_f1: [[0, 0, 0, 0, 0, -0.001, 0, 0, -0.004, 0, 0, 0], 3] as [number[], number] };

it('a modal result picks its mode, deforms by that mode\'s shape, jumps to the mode a check is about and vibrates in preview', () => {
  const { mesh, container } = mount(MODAL, undefined, { faces: FACES, attributes: MODE_2 });
  // What you see with no view: the mode, then the deformation; the colours are the shape's, over every mode's range.
  expect(screen.getByRole('combobox', { name: 'Mode' }).textContent).toBe('Mode 1 · 85 Hz');
  expect(screen.getAllByRole('slider').map(slider => slider.getAttribute('aria-label'))).toEqual(['Deformation scale']);
  expect(barText(container)).toBe('Mode shape01.00 mm');
  expect(zOf(mesh, 2)).toBeCloseTo(0, 6);
  choose('Mode', 'Mode 2 · 118 Hz');
  // Mode 1's 10x comes off and mode 2's goes on.
  expect(zOf(mesh, 2)).toBeCloseTo(-0.06, 6);
  expect(barText(container)).toBe('Mode shape01.00 mm');
  choose('Mode', 'Mode 1 · 85 Hz');
  expect(verdictOf()).toMatchObject({ status: 'weak', title: 'Fails 1 of 2 checks', caption: 'Mode 2 at 118 Hz, inside 110–130 Hz' });
  // Choosing the check that is about mode 2 shows mode 2.
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Select Motor speed' })); });
  expect(screen.getByRole('combobox', { name: 'Mode' }).textContent).toBe('Mode 2 · 118 Hz');
  expect(zOf(mesh, 2)).toBeCloseTo(-0.06, 6);
  // Its routine is Vibrate: one swing a second, through rest, out to the shape and back the other way.
  expect([own().label, own().duration]).toEqual(['Vibrate', 1]);
  play(0);
  expect(zOf(mesh, 2)).toBeCloseTo(-0.02, 6);
  play(0.25);
  expect(zOf(mesh, 2)).toBeCloseTo(-0.06, 6);
  play(0.75);
  expect(zOf(mesh, 2)).toBeCloseTo(0.02, 6);
  release();
  expect(zOf(mesh, 2)).toBeCloseTo(-0.06, 6);
  // Its markers are its fixtures, and Display's gate says so.
  openDisplay();
  expect(screen.getByText('Cones where it holds it.')).toBeTruthy();
});

// A steady thermal result: a signed temperature and a heat flow, no displacement to deform by.
const THERMAL = {
  ...FOUND, deformation_scale: 1, safety_factor: null, analysis: { type: 'thermal', tier: 1, word: 'Heat', reference_C: 20 }, faces: ['#o1.f1', '#o1.f2'],
  fields: [{ attribute: '_TEMPERATURE', name: 'temperature', units: '°C', min: 20, max: 84, signed: true },
    { attribute: '_HEAT_FLUX', name: 'heat flux', units: 'W/m²', min: 0, max: 5000 }],
  study: { material: STUDY.material, fixtures: [], loads: [], mesh: STUDY.mesh, temperatures: [{ faces: ['#o1.f1'], C: 25 }],
    heat: [{ faces: ['#o1.f1'], W: 15 }], convection: [{ faces: ['#o1.f1'], h_W_m2K: 10, ambient_C: 25 }] },
  checks: [{ kind: 'temperature', label: '', value: 84.2, limit: 100, unit: '°C', ratio: 0.79, close_at: 0.9, status: 'passes', faces: ['#o1.f2'], reference: 20 }],
};
const HEAT_FIELDS = { _von_mises: null, _displacement: null, _temperature: [[20, 40, 60, 84], 1] as [number[], number], _heat_flux: [[0, 1000, 2000, 5000], 1] as [number[], number] };

it('a thermal result reads its setup as Kept at, Heated and Cooled by air, shows its own minimum, deforms nothing and plays nothing', async () => {
  const copied: string[] = [];
  // Every vertex on face 1, which the study keeps cool, heats and cools by air.
  const { mesh, container } = mount(THERMAL, undefined, { faces: [0, 0, 0, 0], attributes: HEAT_FIELDS, host: clipboardHost(copied) });
  const positions = Array.from(mesh.geometry.getAttribute('position').array as Float32Array);
  expect(rowTexts(studyPanel()!).map(text => text!.replace(/‑/g, '-'))).toEqual(
    ['Kept at', '25 °C', 'Heated', '15 W', 'Cooled by air', 'Air at 25 °C', 'Made of', '6061-T6', 'What you see', 'Details']);
  // The field alone: there is no displacement to draw larger.
  expect(screen.getByRole('combobox', { name: 'Result field' }).textContent).toBe('Temperature');
  expect(screen.queryAllByRole('slider')).toEqual([]);
  // A signed field's bar starts at its own minimum.
  expect(barText(container)).toBe('Temperature20.084.0 °C');
  expect(verdictOf()).toMatchObject({ status: 'strong', title: 'Cool enough', caption: 'Hottest 84 °C, 16 °C under its limit' });
  expect(loaded.own).toEqual([]);
  expect(Array.from(mesh.geometry.getAttribute('position').array as Float32Array)).toEqual(positions);
  // Its markers: a dot, a wavy arrow and the air's strokes; the heat row chooses its arrows and its face.
  const group = mesh.children.find(child => child.name === 'fea-markers')!;
  const heads = group.getObjectByName('fea-heat-heads') as THREE.InstancedMesh;
  const colour = new THREE.Color();
  heads.getColorAt(0, colour);
  expect(colour.getHexString()).toBe('18181b');
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Select 15 W' })); });
  heads.getColorAt(0, colour);
  expect(colour.getHexString()).toBe('ff40f2');
  expect(await copiedPrompt(copied)).toBe('move it\n\nFile: /models/part.glb\nReferences:\n15 W of heat into face 1 · /models/part.step#o1.f1');
  // Display's gate is titled for heat and says what it draws.
  openDisplay();
  expect(screen.getByText('Dots where its temperature is fixed, wavy arrows where heat goes in, strokes where air cools it.')).toBeTruthy();
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Disable Heat inputs and temperatures' })); });
  expect(group.children.every(child => !child.visible)).toBe(true);
});

// A transient result: time frames, each frame's stress and displacement its own, opening on the peak.
const TRANSIENT = {
  ...STUDIED, safety_factor: null, analysis: { type: 'transient', tier: 1, word: 'Over time' },
  fields: [{ attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 90, per_frame: true },
    { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 2, attribute_scale: 1000, per_frame: true }],
  series: { kind: 'time', unit: 's', default: 2, frames: [
    { value: 0, label: '0 ms', attributes: { von_mises: '_VON_MISES', displacement: '_DISPLACEMENT' } },
    { value: 0.01, label: '10 ms', attributes: { von_mises: '_VON_MISES_F1', displacement: '_DISPLACEMENT_F1' } },
    { value: 0.02, label: '20 ms', attributes: { von_mises: '_VON_MISES_F2', displacement: '_DISPLACEMENT_F2' } }] },
  checks: [{ kind: 'stress', label: 'Start', value: 90, limit: 276, unit: 'MPa', ratio: 0.326, close_at: 0.5, margin: 2, status: 'passes', where: { ref: '#o1.f1' },
    at: { frame: 0, value: 0, unit: 's' } }],
};
const vectorsUp = (z: number[]) => [[0, 0, z[0], 0, 0, z[1], 0, 0, z[2], 0, 0, z[3]], 3] as [number[], number];
const TIME_FIELDS = {
  _von_mises: [[0, 0, 0, 0], 1] as [number[], number], _von_mises_f1: [[10, 20, 30, 45], 1] as [number[], number], _von_mises_f2: [[20, 40, 60, 90], 1] as [number[], number],
  _displacement: vectorsUp([0, 0, 0, 0]), _displacement_f1: vectorsUp([0, 0.0005, 0.001, 0.0005]), _displacement_f2: vectorsUp([0, 0.001, 0.002, 0.001]),
};

it('a transient result scrubs its time frames, snapping to them, jumps to a check\'s moment and plays its frames', () => {
  const { mesh } = mount(TRANSIENT, undefined, { faces: FACES, attributes: TIME_FIELDS });
  const vertex3 = () => colourBytes(mesh).slice(12, 15);
  // It opens on the peak, the last frame: its stress and displacement.
  expect(screen.getAllByRole('slider').map(slider => slider.getAttribute('aria-label'))).toEqual(['Time', 'Deformation scale']);
  expect(screen.getByRole('textbox', { name: 'Time slider value' }).getAttribute('value')).toBe('20 ms');
  expect(zOf(mesh, 2)).toBeCloseTo(0.02, 6);
  expect(vertex3()).toEqual([230, 20, 13]);
  setValue('Time slider value', '0.012');
  expect(screen.getByRole('textbox', { name: 'Time slider value' }).getAttribute('value')).toBe('10 ms');
  expect(zOf(mesh, 2)).toBeCloseTo(0.01, 6);
  expect(vertex3()).toEqual([27, 217, 38]);
  // The check is about the first moment: choosing it moves the scrubber there.
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Select Start' })); });
  expect(screen.getByRole('textbox', { name: 'Time slider value' }).getAttribute('value')).toBe('0 ms');
  expect(zOf(mesh, 2)).toBeCloseTo(0, 6);
  // Play runs the frames over three seconds, each blended into the next.
  expect([own().label, own().duration]).toEqual(['Play', 3]);
  play(0.75);
  expect(zOf(mesh, 2)).toBeCloseTo(0.005, 6);
  play(3);
  expect(zOf(mesh, 2)).toBeCloseTo(0.02, 6);
  expect(vertex3()).toEqual([230, 20, 13]);
  release();
  expect(zOf(mesh, 2)).toBeCloseTo(0, 6);
});

it('a random vibration\'s RMS fields show at the sigma chosen, the bar saying the level', () => {
  const random = { ...FOUND, safety_factor: null, analysis: { type: 'random_vibration' }, study: { ...STUDY, sigma: 3 },
    fields: [{ attribute: '_VON_MISES_RMS', name: 'von Mises RMS', units: 'MPa', min: 0, max: 30 }] };
  const { container, mesh } = mount(random, undefined, { attributes: { _von_mises: null, _von_mises_rms: [[0, 10, 20, 30], 1] } });
  expect(screen.getByRole('combobox', { name: 'Sigma' }).textContent).toBe('3σ');
  expect(barText(container)).toBe('Stress (3σ)090.0 MPa');
  const colours = colourBytes(mesh);
  choose('Sigma', '1σ');
  expect(barText(container)).toBe('Stress (1σ)030.0 MPa');
  // The values and the range scale together, so the colours keep their place.
  expect(colourBytes(mesh)).toEqual(colours);
  expect(loaded.own).toEqual([]);
});

it('a result that took steps to fit says so: "adapted" in the verdict and a Details row per step, chosen with its faces', async () => {
  const copied: string[] = [];
  const words = 'Coarsened the mesh away from the hole to fit: the peak is still meshed at 0.8 mm';
  const fit = [{ rung: 'local_refine', words, accuracy: 'peak stress moved 2.1 % between passes', accuracy_pct: 2.1, faces: ['#o1.f2'], detail: '' },
    { rung: 'iterative', words: 'Used an iterative solver to fit in memory', accuracy: '', accuracy_pct: null, faces: [], detail: '' }];
  const { mesh } = mount({ ...STUDIED, fit }, undefined, { faces: FACES, host: clipboardHost(copied) });
  expect(verdictOf().caption).toBe('OK up to 5.8× this load · adapted');
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Expand Details' })); });
  expect(rowTexts(studyPanel()!).slice(-5)).toEqual(['Details', 'Mesh1.9 mm elements', 'Adapted to fit', words, 'Used an iterative solver to fit in memory']);
  const plain = colourBytes(mesh);
  act(() => { fireEvent.click(screen.getByRole('button', { name: `Select ${words}` })); });
  expect(colourBytes(mesh).slice(12, 15)).not.toEqual(plain.slice(12, 15));
  expect(colourBytes(mesh).slice(0, 12)).toEqual(plain.slice(0, 12));
  expect(await copiedPrompt(copied)).toBe(`move it\n\nFile: /models/part.glb\nReferences:\nAdapted to fit: ${words} (peak stress moved 2.1 % between passes) · /models/part.step#o1.f2`);
  // A step with no faces carries the whole part.
  cleanup();
  mount({ ...STUDIED, fit }, undefined, { faces: FACES, host: clipboardHost(copied) });
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Expand Details' })); });
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Select Used an iterative solver to fit in memory' })); });
  expect(await copiedPrompt(copied)).toBe('move it\n\nFile: /models/part.glb\nReferences:\nAdapted to fit: Used an iterative solver to fit in memory · /models/part.step#o1');
});

it('a static result keeps its Load ramp, drawn as it always was', () => {
  const { mesh } = mount(STUDIED, undefined, { faces: FACES });
  expect([own().id, own().label, own().duration]).toEqual(['fea:load-ramp', 'Load ramp', 2]);
  play(1);
  // Half the load on: half the 10x drawn.
  expect(zOf(mesh, 2)).toBeCloseTo(-0.01, 6);
  release();
  expect(zOf(mesh, 2)).toBeCloseTo(0, 6);
});

it('a harmonic result vibrates its frame through its phase, the real part then the imaginary', () => {
  const harmonic = { ...STUDIED, safety_factor: null, analysis: { type: 'harmonic' },
    series: { kind: 'frequency', unit: 'Hz', default: 0, frames: [{ value: 118, label: '118 Hz', attributes: { displacement: '_DISPLACEMENT', displacement_im: '_DISPLACEMENT_IM_F0' } }] } };
  const { mesh } = mount(harmonic, undefined, { faces: FACES, attributes: { _displacement_im_f0: vectorsUp([0, 0, 0.001, 0]) } });
  expect([own().label, own().duration]).toEqual(['Vibrate', 1]);
  // At phase 0 the real part, as baked; a quarter turn on, minus the imaginary part.
  play(0);
  expect(zOf(mesh, 2)).toBeCloseTo(0, 6);
  play(0.25);
  expect(zOf(mesh, 2)).toBeCloseTo(-0.02 - 0.01, 6);
  release();
  expect(zOf(mesh, 2)).toBeCloseTo(0, 6);
});

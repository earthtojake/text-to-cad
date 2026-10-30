import React, { forwardRef, useImperativeHandle, useRef } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';

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
// The renderer's own clip (the Load ramp) is kept to be played by hand.
vi.mock('../../../dist/renderers/glb/useGlbAnimation.js', () => ({ useGlbAnimation: (_document: any, _render: any, own: any) => { loaded.own = own; return loaded.animation; } }));
import GlbRenderer, { loadFeaView } from '../../../dist/renderers/glb/GlbRenderer.js';
import { writeFileView } from '../../../dist/renderers/kit/shell/fileView.js';
import { ViewerElementContext, ViewerHostContext } from '../../../dist/host/context.js';
import { testHost } from '../../../dist/host/testing/host.js';
import * as THREE from 'three';

// The FEA viewer is its own chunk (`GlbRenderer.lazy.test.tsx`): loaded once here, a result draws as soon as it mounts.
beforeAll(() => loadFeaView());
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }));
});
afterEach(() => { vi.restoreAllMocks(); loaded.animation = null; loaded.runtime = null; loaded.host = null; cleanup(); vi.unstubAllGlobals(); document.querySelectorAll('[data-test-navbar]').forEach(slot => slot.remove()); });

// Two triangles the way GLTFLoader hands a result over: lower-cased custom attributes, extras in userData.
// `faces`: the source face of each vertex (`_FACE`, which cadgen writes on every result); an assembly's
// vertices also carry their part (`_PART`).
function resultRoot(extras: Record<string, unknown> | null, faces: number[] = [0, 0, 0, 0]) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0]), 3));
  geometry.setIndex([0, 1, 2, 1, 3, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(16).fill(7), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0, 50, 100, 25]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array([0, 0, 0, 0, 0, 0.001, 0, 0, 0.002, 0, 0, 0.0005]), 3));
  geometry.setAttribute('_face', new BufferAttribute(new Float32Array(faces), 1));
  if (Array.isArray(extras?.parts) && extras.parts.length) geometry.setAttribute('_part', new BufferAttribute(new Float32Array([0, 0, 0, 1]), 1));
  const mesh = new Mesh(geometry);
  if (extras) Object.assign(mesh.userData, extras);
  const root = new Group();
  root.add(mesh);
  return { mesh, root };
}
// The study the result was solved for, and the checks it picked, as cadgen judged them: the stress check and a sag on the loaded face.
const STUDY = {
  material: { name: '6061-T6', yield_MPa: 276, youngs_GPa: 68.9, poisson: 0.33 },
  fixtures: [{ type: 'fixed', faces: ['bracket/face 1'] }],
  loads: [{ type: 'force', faces: ['bracket/face 2'], vector_N: [0, 0, -2500] }],
  mesh: { size_mm: 1.9205, order: 2, elements: 52271, refined_from_mm: 2.7686 },
  margin: 2,
};
const STRESS_CHECK = { kind: 'stress', label: 'Strength', value: 47.3, limit: 276, unit: 'MPa', ratio: 0.171527, close_at: 0.5, margin: 2, status: 'passes', where: { ref: 'bracket/face 1', at: [0, 0, 0] } };
const SAG_CHECK = { kind: 'displacement', label: 'Tip sag', value: 0.62, limit: 0.5, unit: 'mm', ratio: 1.24, close_at: 0.9, status: 'fails', where: { ref: 'bracket/face 2', at: [1, 0, 0] }, faces: ['bracket/face 2'] };
/** A result's safety factor and its stress check at it, judged against the margin of 2 as cadgen judges it. */
const factored = (factor: number) => ({ safety_factor: factor,
  checks: [{ ...STRESS_CHECK, ratio: Number((1 / factor).toFixed(6)), status: factor < 1 ? 'fails' : factor < 2 ? 'close' : 'passes' }] });
const RESULT = {
  generator: 'cadgen fea', name: 'part von Mises', document: 'part.step', occurrence: 'bracket', deformation_scale: 10, safety_factor: 5.83,
  fields: [
    { attribute: '_VON_MISES', name: 'von Mises stress', units: 'MPa', min: 0, max: 47.3, attribute_scale: 1 },
    { attribute: '_DISPLACEMENT', name: 'displacement', units: 'mm', min: 0, max: 0.0288, attribute_scale: 1000 },
  ],
  findings: [], checks: [STRESS_CHECK], faces: [], study: STUDY,
  // The writer's colour ramp, as every result carries it: blue -> red.
  ramp: [[0, [0.05, 0.10, 0.90]], [0.25, [0.05, 0.85, 0.95]], [0.5, [0.10, 0.85, 0.15]], [0.75, [0.98, 0.90, 0.10]], [1, [0.90, 0.08, 0.05]]],
};
// The viewer's own element, which the shell asks whose Escape it is.
function ViewerElement({ children }: { children: React.ReactNode }) {
  const element = useRef<HTMLDivElement | null>(null);
  return <ViewerElementContext.Provider value={element}><div ref={element}>{children}</div></ViewerElementContext.Provider>;
}
const colourBytes = (mesh: Mesh) => Array.from(mesh.geometry.getAttribute('color').array as Uint8Array);

function mount(extras: Record<string, unknown> | null, state?: unknown, { actions = () => {}, host = testHost(), faces = [0, 0, 0, 0], settings = { toolStack: { panels: {}, collapsed: {} } } }: { actions?: (actions: readonly any[]) => void, host?: any, faces?: number[], settings?: any } = {}) {
  const built = resultRoot(extras, faces);
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
// Where the study holds and loads the part, drawn or not: What you see's checkbox.
const markersGate = (name: string) => screen.getByRole('checkbox', { name });
const toggleMarkers = (name: string) => act(() => { fireEvent.click(markersGate(name)); });
const studyPanel = () => screen.queryByRole('region', { name: 'Study' });
const rowTexts = (panel: HTMLElement) => Array.from(panel.querySelectorAll('[data-study-row]')).map(row => row.textContent);

it('puts the field and deformation in Study, the file sidebar\'s, and on the view a colour bar that is only the scale', () => {
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
  // A section of the file sidebar, its tile named for it; one field select, Study's.
  expect(study.hasAttribute('data-sidebar-section')).toBe(true);
  expect(screen.getByRole('group', { name: 'File sidebar' }).querySelector('button[aria-label="Study"]')).toBeTruthy();
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
  expect(save.mock.calls.at(-1)![0].renderer.fea.value).toMatchObject({ field: null, scale: 0, loadScale: null });
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

it('a GLB that is not a result has no colour bar, no Study and its colours untouched', () => {
  const { mesh, container } = mount(null);
  expect(container.querySelector('[aria-label$="colour bar"]')).toBeNull();
  expect(studyPanel()).toBeNull();
  expect(screen.queryByRole('checkbox', { name: 'Loads and fixtures' })).toBeNull();
  expect(colourBytes(mesh).every(byte => byte === 7)).toBe(true);
});

it('the colour bar stands on Preview\'s playbar line, and a stored scale is held to the slider\'s range', () => {
  const stored = writeFileView({ renderer: { fea: { field: null, scale: 9999 } }, signatures: { fea: '_von_mises,_displacement:10' } });
  const { container, mesh } = mount(RESULT, stored);
  expect((container.querySelector('[aria-label$="colour bar"]')!.parentElement as HTMLElement).style.bottom).toBe('1rem');
  // The slider tops out at four times the file's own 10x.
  expect(mesh.geometry.getAttribute('position').getZ(2)).toBeCloseTo(0.06, 6);
});

// What the result's checks found stays in the file for the agent; the viewer's status is Study's verdict.
const PEAK = { check: 'fea', severity: 'error', type: 'peak', summary: 'The peak stress, 120 MPa, is above the 100 MPa this material yields at',
  description: 'The peak stress is above yield.', items: [{ text: 'the peak stress', ref: 'bracket/face 3', at: [10, 20, 30] }] };
const SOFT = { check: 'fea', severity: 'warning', type: 'bend', summary: 'The part bends visibly: 0.4 mm', description: 'It bends.', items: [{ text: 'the tip', ref: null }] };

it('a result with findings raises no alert card and puts no findings icon in the navbar', () => {
  const actions = vi.fn();
  mount({ ...RESULT, findings: [PEAK, SOFT] }, undefined, { actions });
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

// The study's faces, and the face each vertex lies on.
const STUDIED = { ...RESULT, faces: ['bracket/face 1', 'bracket/face 2'] };
// Vertices 0-2 lie on face index 0 (bracket/face 1), vertex 3 on face index 1 (bracket/face 2).
const FACES = [0, 0, 0, 1];
async function copiedPrompt(copied: string[]) {
  // The note is an editable field: written as typing would write it.
  act(() => { const field = screen.getByRole('textbox', { name: 'Describe your changes' }); field.textContent = 'move it'; fireEvent.input(field); });
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
  // In the sidebar's one scroll, in order: no foot of its own.
  expect(study.querySelector('[data-study-foot]')).toBeNull();
  expect(study.querySelector('[data-tool-panel-body] [role="combobox"][aria-label="Result field"]')).toBeTruthy();
});

it('a face both fixed and loaded is named for both, chosen from either row or picked', async () => {
  const copied: string[] = [];
  const both = { ...STUDY, loads: [{ type: 'force', faces: ['bracket/face 1'], vector_N: [0, 0, -2500] }] };
  mount({ ...STUDIED, study: both }, undefined, { faces: FACES, host: clipboardHost(copied) });
  act(() => { fireEvent.click(screen.getAllByRole('button', { name: 'Select Face 1' })[0]); });
  expect(await copiedPrompt(copied)).toBe('move it\n\nFile: /models/part.glb\nReferences:\nFixed and loaded face 1 · /models/part.step#bracket/face 1');
});

it('a result without its checks or study says so in the load\'s alert, with no Study, over the model as the file colours it', () => {
  for (const missing of ['checks', 'study']) {
    const { mesh, container } = mount({ ...STUDIED, [missing]: undefined }, undefined, { faces: FACES });
    expect(screen.getByRole('alert').textContent).toContain(`no ${missing}`);
    expect(studyPanel()).toBeNull();
    expect(container.querySelector('[aria-label$="colour bar"]')).toBeNull();
    expect(colourBytes(mesh).every(byte => byte === 7)).toBe(true);
    cleanup();
  }
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
  // Chosen in Study, its chip says what it is, as its prompt does.
  expect(screen.getByRole('region', { name: 'Quick Edit' }).textContent).toContain('Fixed face 1');
  expect(await copiedPrompt(copied)).toBe('move it\n\nFile: /models/part.glb\nReferences:\nFixed face 1 · /models/part.step#bracket/face 1');
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
  expect(await copiedPrompt(copied)).toBe('move it\n\nFile: /models/part.glb\nReferences:\n2500 N load on face 2 · /models/part.step#bracket/face 2');
});

it('a press on the result with Select picks the face under it into Quick Edit\'s chip, its card its ref and its role, and the copy key copies it', async () => {
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
  const chip = screen.getByRole('button', { name: /^Face 1/ });
  act(() => { fireEvent.click(chip); });
  const card = document.querySelector<HTMLElement>('[data-quick-edit-ref-card]')!;
  expect(Array.from(card.querySelectorAll('[data-info-row]')).map(row => row.textContent)).toEqual(['IDbracket/face 1', 'Studyfixed']);
  await act(async () => { fireEvent.keyDown(document.querySelector('[data-slot="cad-file-view"]')!, { key: 'c', metaKey: true, ctrlKey: true }); });
  expect(copied.at(-1)).toBe('/models/part.step#bracket/face 1');
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
  ...STUDIED, faces: ['part1/face 1', 'part2/face 1', 'part1/face 9'], weakest_part: 'post', weakest_part_peak_MPa: 180, safety_factor: 1.46, max_displacement_mm: 0.2,
  checks: [{ ...factored(1.46).checks[0], value: 180, part: 'post' }],
  parts: [
    { ref: 'part1', name: 'post', material: '6061-T6', yield_MPa: 276, peak_MPa: 180, safety_factor: 1.46, max_displacement_mm: 0.2 },
    { ref: 'part2', name: 'base', material: 'Steel', yield_MPa: 250, peak_MPa: 40, safety_factor: 2.5, max_displacement_mm: 0.01 },
  ],
  connections: [{ between: ['part1', 'part2'], names: ['post', 'base'], type: 'bonded', area_mm2: 100, gap_mm: 0, faces: ['part1/face 1', 'part2/face 1'] }],
};
// The Parts panel shows from six parts up: four more parts beside post and base, joined to nothing.
const SIX_PARTS = [...ASSEMBLED.parts, ...[3, 4, 5, 6].map(n => ({ ...ASSEMBLED.parts[1], ref: `part${n}`, name: `pin ${n}` }))];
function mountAssembly(copied: string[], extras: Record<string, unknown> = { parts: SIX_PARTS }) {
  return mount({ ...ASSEMBLED, ...extras }, undefined, { faces: [0, 0, 2, 1], host: clipboardHost(copied) });
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
  expect(plain(parts)).toEqual(['post6061-T6 · holds 1.4×', '↔ basebonded · 100 mm²', 'baseSteel · holds 2.5×',
    ...[3, 4, 5, 6].map(n => `pin ${n}Steel · holds 2.5×`)]);
  expect(parts.querySelector('[data-study-row="part:0"] [data-study-detail]')!.className).not.toMatch(/truncate|ellipsis|overflow-hidden|whitespace-nowrap/);
  // Opened, base lists the same joint, naming post.
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Expand base' })); });
  expect(plain(parts).slice(2, 4)).toEqual(['baseSteel · holds 2.5×', '↔ postbonded · 100 mm²']);
  // Study no longer lists parts or joints; what the parts are made of, which differ, each with its part.
  expect(study.querySelector('[data-study-row="material:name"]')!.textContent!.replace(/\u00a0/g, ' ')).toBe('6061-T6 post, Steel (5 parts)');
  expect(study.querySelector('[data-study-row^="part:"], [data-study-row^="joint:"], [data-study-row="parts"], [data-study-row="connections"]')).toBeNull();
});

it('an assembly\'s Parts and Study are two sections of the file sidebar, each with its own tile', () => {
  mountAssembly([]);
  const tiles = Array.from(screen.getByRole('group', { name: 'File sidebar' }).querySelectorAll('button')).map(tile => tile.getAttribute('aria-label'));
  expect(tiles).toEqual(expect.arrayContaining(['Parts', 'Study']));
  expect(partsPanel()!.hasAttribute('data-sidebar-section')).toBe(true);
  expect(studyPanel()!.hasAttribute('data-sidebar-section')).toBe(true);
});

it('an assembly shows Parts from six parts up', () => {
  const more = (count: number) => Array.from({ length: count }, (_, index) => ({ ...ASSEMBLED.parts[index % 2], ref: `bracket.${index + 1}`, name: `part ${index + 1}` }));
  for (const [count, shown] of [[4, false], [5, false], [6, true]] as const) {
    mountAssembly([], { parts: more(count) });
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

it('with Parts hidden, a face picked on an assembly names its part, and its chip\'s card says the part\'s material and what it holds', () => {
  const release = pressOnTheResult(() => { mountAssembly([], {}); });
  expect(partsPanel()).toBeNull();
  act(() => { fireEvent.click(screen.getByRole('button', { name: /^post · face 1/ })); });
  const card = document.querySelector<HTMLElement>('[data-quick-edit-ref-card]')!;
  const rows = Array.from(card.querySelectorAll('[data-info-row]')).map(row => row.textContent!.replace(/\u2011/g, '-').replace(/\u00a0/g, ' '));
  expect(rows).toEqual(['IDpart1/face 1', 'Studyfree', 'Part6061-T6 · holds 1.4×']);
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
  expect(await copiedPrompt(copied)).toBe("move it\n\nFile: /models/part.glb\nReferences:\nPart 'post' · /models/part.step#part1");
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
  expect(await copiedPrompt(copied)).toBe("move it\n\nFile: /models/part.glb\nReferences:\nBonded joint between 'post' and 'base' · /models/part.step#part1/face 1,part2/face 1");
});

it('a joint chosen under either of its parts is the same choice: both copies pressed, the same refs', async () => {
  const copied: string[] = [];
  mountAssembly(copied);
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Expand base' })); });
  const copies = screen.getAllByRole('button', { name: 'Select post ↔ base' });
  expect(copies).toHaveLength(2);
  act(() => { fireEvent.click(copies[1]); });
  for (const copy of screen.getAllByRole('button', { name: 'Select post ↔ base' })) expect(copy.getAttribute('aria-pressed')).toBe('true');
  expect(await copiedPrompt(copied)).toBe("move it\n\nFile: /models/part.glb\nReferences:\nBonded joint between 'post' and 'base' · /models/part.step#part1/face 1,part2/face 1");
});

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

it('What you see is the field, the deformation and the load', () => {
  mount(RESULT);
  const sliders = screen.getAllByRole('slider');
  expect(sliders.map(slider => slider.getAttribute('aria-label'))).toEqual(['Deformation scale', 'Load']);
  expect(sliders.map(slider => [slider.getAttribute('aria-valuemin'), slider.getAttribute('aria-valuemax'), slider.getAttribute('aria-valuenow')]))
    .toEqual([['0', '40', '10'], ['0.1', '3', '1']]);
  expect(resultRows().map(row => row.textContent?.replace(/\s+/g, ' ').trim())).toEqual(['Stress', 'Deformation', 'Load']);
  expect(screen.getByRole('textbox', { name: 'Deformation scale value' }).getAttribute('value')).toBe('×10.0');
  expect(screen.getByRole('textbox', { name: 'Load value' }).getAttribute('value')).toBe('×1.0');
});

it('shows each multiple to its slider\'s step, in boxes of one width that keep it as the value moves', () => {
  mount(RESULT);
  const box = (name: string) => screen.getByRole('textbox', { name: `${name} value` });
  const width = (name: string) => box(name).className.split(/\s+/).find(name => name.startsWith('w-'));
  const before = [width('Load'), width('Deformation scale')];
  // One width for both, so their sliders end together.
  expect(width('Load')).toBe(width('Deformation scale'));
  // The Load's step is 0.1: half the load is "×0.5", never "×0.500", and its box stays as it was.
  setValue('Load value', '0.5');
  expect(box('Load').getAttribute('value')).toBe('×0.5');
  setValue('Deformation scale value', '2.5');
  expect(box('Deformation scale').getAttribute('value')).toBe('×2.5');
  expect([width('Load'), width('Deformation scale')]).toEqual(before);
  // A value typed between the steps keeps its own figures: the box never shows a load that is not drawn.
  setValue('Load value', '0.55');
  expect(box('Load').getAttribute('value')).toBe('×0.550');
});

it('sizes What you see\'s value boxes to hold the whole value, its padding and its borders: a large exaggeration is never cut off', () => {
  // "×6000" read "×600C" and "×9500000" crowded the box: its width left out the 1px borders and the × glyph.
  for (const scale of [10, 6000, 42000, 9500000, 120000000, 95000000000]) {
    mount({ ...RESULT, deformation_scale: scale });
    const box = screen.getByRole('textbox', { name: 'Deformation scale value' });
    const value = box.getAttribute('value')!;
    const widths = box.className.split(/\s+/).filter(name => name.startsWith('w-'));
    expect(widths, value).toHaveLength(1);
    const [, ch, rem, px] = /^w-\[calc\((\d+)ch\+([\d.]+)rem\+(\d+)px\)\]$/.exec(widths[0]) || [];
    // A figure and the × are 1ch each with tabular figures, a point half of one; half a ch is spare.
    const needed = [...value].reduce((sum, glyph) => sum + (glyph === '.' ? 0.5 : 1), 0.5);
    expect(Number(ch), `${value}: ${widths[0]}`).toBeGreaterThanOrEqual(Math.min(Math.ceil(needed), 14));
    expect([rem, px], value).toEqual(['0.75', '2']);
    cleanup();
  }
});

it('each slider\'s thumb stands at its control\'s value, where that is on its range, not at the left end', () => {
  mount(RESULT);
  const thumb = (name: string) => screen.getByRole('slider', { name });
  const now = () => screen.getAllByRole('slider').map(slider => slider.getAttribute('aria-valuenow'));
  // ×10 on 0 to 40 is 25% along; ×1 on 0.1 to 3 is 31%.
  expect(now()).toEqual(['10', '1']);
  expect((thumb('Deformation scale').parentElement as HTMLElement).style.left).toMatch(/^calc\(25% \+ /);
  expect((thumb('Load').parentElement as HTMLElement).style.left).toMatch(/^calc\(31\.03/);
  setValue('Deformation scale value', '40');
  setValue('Load value', '2.5');
  expect(now()).toEqual(['40', '2.5']);
  expect((thumb('Deformation scale').parentElement as HTMLElement).style.left).toMatch(/^calc\(100% /);
});

it('at twice the load, the bar and the deformation are twice the solved ones, what each part holds is half, and a part flips to yields', () => {
  const parts = [{ ref: 'part1', name: 'post', material: 'Steel', safety_factor: 5.83 }, { ref: 'part2', name: 'base', material: 'Steel', safety_factor: 1.5 }];
  const pins = [3, 4, 5, 6].map(n => ({ ref: `part${n}`, name: `pin ${n}`, material: 'Steel', safety_factor: 10 }));
  const { container, mesh } = mount({ ...RESULT, parts: [...parts, ...pins], weakest_part: 'base' });
  const colours = colourBytes(mesh);
  const tip = mesh.geometry.getAttribute('position').getZ(2);
  const partDetails = () => Array.from(screen.getByRole('region', { name: 'Parts' }).querySelectorAll('[data-study-detail]')).map(detail => detail.textContent!.replace(/\u00a0/g, ' ')).slice(0, 2);
  expect(partDetails()).toEqual(['Steel · holds 5.8×', 'Steel · holds 1.5×']);
  setValue('Load value', '2');
  expect(container.querySelector('[data-fea-max]')!.textContent).toBe('94.6 MPa');
  expect(partDetails()).toEqual(['Steel · holds 2.9×', 'Steel · yields']);
  // The colours keep their place on a bar that now reads twice as high; the displacement is drawn twice as far.
  expect(colourBytes(mesh)).toEqual(colours);
  // The file baked in 10x of vertex 2's 0.002 m: 10x at the solved load, 20x at twice it.
  expect(tip).toBeCloseTo(0, 6);
  expect(mesh.geometry.getAttribute('position').getZ(2)).toBeCloseTo(0.002 * (20 - 10), 6);
});

it('draws the loads and fixtures on the model, the chosen load\'s arrows in the chosen colour, and Study\'s checkbox hides them', () => {
  const both = { ...STUDY, loads: [{ type: 'force', faces: ['bracket/face 1'], vector_N: [0, 0, -2500] }] };
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
  expect(markersGate('Loads and fixtures').getAttribute('aria-checked')).toBe('true');
  toggleMarkers('Loads and fixtures');
  expect(group.children.map(child => child.visible)).toEqual([false, false, false, false, false, false]);
  unmount();
  expect(group.parent).toBeNull();
});

it('a roller fixture reads as Slides on, after Held at, with its own glyph and marker, and is chosen as it slides', async () => {
  const copied: string[] = [];
  const rolling = { ...STUDY, fixtures: [{ type: 'fixed', faces: ['bracket/face 2'] }, { type: 'roller', faces: ['bracket/face 1'] }], loads: [] };
  const { mesh } = mount({ ...STUDIED, study: rolling }, undefined, { faces: FACES, host: clipboardHost(copied) });
  const study = studyPanel()!;
  expect(rowTexts(study).map(text => text!.replace(/\u2011/g, '-')).slice(0, 4)).toEqual(['Held at', 'Face 2', 'Slides on', 'Face 1']);
  const headings = Array.from(study.querySelectorAll('[data-study-heading]'));
  expect(headings.map(row => row.textContent)).toEqual(['Held at', 'Slides on', 'Made of']);
  // Its glyph is the fixture's cone on a plate that rolls on the face: the cone, the plate, two rollers, the face.
  const glyph = headings[1].querySelector('svg')!;
  expect(glyph.querySelectorAll('circle').length).toBe(2);
  expect(glyph.getAttribute('class')).toContain('text-muted-foreground');
  expect(headings[0].querySelector('svg circle')).toBeNull();
  // On the model, the roller's own grey cones on plates (face 2 has no whole triangle here, so no fixture cone stands on it).
  const group = mesh.children.find(child => child.name === 'fea-markers')!;
  const rollerCones = group.getObjectByName('fea-roller-cones') as THREE.InstancedMesh;
  expect(rollerCones.count).toBe(1);
  expect((group.getObjectByName('fea-fixture-cones') as THREE.InstancedMesh).count).toBe(0);
  const colour = new THREE.Color();
  rollerCones.getColorAt(0, colour);
  expect(colour.getHexString()).toBe('71717a');
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Select Face 1' })); });
  rollerCones.getColorAt(0, colour);
  expect(colour.getHexString()).toBe('ff40f2');
  expect(await copiedPrompt(copied)).toBe('move it\n\nFile: /models/part.glb\nReferences:\nSlides on face 1 · /models/part.step#bracket/face 1');
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
    mount({ ...STUDIED, ...factored(factor) }, undefined, { faces: FACES });
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
  mount({ ...STUDIED, ...factored(1.6) }, undefined, { faces: FACES });
  const bar = () => screen.getByRole('meter', { name: 'Strength: how much of its limit' });
  const fill = () => (bar().querySelector('[data-fea-verdict-fill]') as HTMLElement).style.width;
  expect(fill()).toBe('62.5%');
  expect(bar().getAttribute('aria-valuenow')).toBe('63');
  expect(bar().hasAttribute('data-over')).toBe(false);
  // The margin of 2: the tick at half the limit, said to assistive technology.
  expect((bar().querySelector('[data-fea-verdict-tick]') as HTMLElement).style.left).toBe('50%');
  expect(bar().getAttribute('aria-valuetext')).toBe('63% of its limit, your 2× margin at 50%');
  cleanup();
  mount({ ...STUDIED, ...factored(0.5) }, undefined, { faces: FACES });
  expect(fill()).toBe('100%');
  expect(bar().getAttribute('aria-valuenow')).toBe('200');
  expect(bar().hasAttribute('data-over')).toBe(true);
  expect(verdictOf().caption).toBe('OK only to 0.5× this load');
});

it('the verdict follows the load control, and can change its word', () => {
  mount({ ...STUDIED, ...factored(1.5) }, undefined, { faces: FACES });
  expect([verdictOf().status, verdictOf().caption]).toEqual(['close', 'OK up to 1.5× this load']);
  setValue('Load value', '2');
  expect([verdictOf().status, verdictOf().caption, verdictOf().rows]).toEqual(['weak', 'OK only to 0.7× this load', [['weak', 'Strength', '95 MPa, limit 276 MPa']]]);
  setValue('Load value', '0.5');
  expect([verdictOf().status, verdictOf().caption]).toEqual(['strong', 'OK up to 3.0× this load']);
});

it('an assembly\'s verdict numbers are its weakest part\'s', () => {
  mountAssembly([]);
  expect(verdictOf()).toMatchObject({ status: 'close', rows: [['close', 'Strength', '180 MPa, limit 276 MPa']] });
});

it('heads the verdict with how many checks fail and the load the weakest takes, then each check the same way, all following the load', () => {
  mount({ ...STUDIED, checks: [STRESS_CHECK, SAG_CHECK] }, undefined, { faces: FACES });
  expect(verdictOf()).toMatchObject({ status: 'weak', title: 'Fails 1 of 2 checks', caption: 'OK only to 0.8× this load',
    rows: [['weak', 'Tip sag', '0.62 mm, limit 0.5 mm'], ['strong', 'Strength', '47 MPa, limit 276 MPa']] });
  // No margin tick on a displacement: its limit is the person's.
  expect(screen.getByRole('meter', { name: 'Tip sag: how much of its limit' }).querySelector('[data-fea-verdict-tick]')).toBeNull();
  expect(screen.getByRole('meter', { name: 'Strength: how much of its limit' }).getAttribute('aria-valuenow')).toBe('17');
  setValue('Load value', '0.5');
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
    text: 'Tip sag fails: moves 0.62 mm, limit 0.5 mm (OK only to 0.8× this load) · /models/part.step#bracket/face 2' });
  // The sentence is on screen too, on its chip in Quick Edit, not only in the prompt it copies.
  expect(screen.getByRole('region', { name: 'Quick Edit' }).textContent).toContain('Tip sag fails: moves 0.62 mm, limit 0.5 mm');
  expect((await prompt(['Select Strength'])).text).toBe('Strength passes: peak 47 MPa, limit 276 MPa (OK up to 5.8× this load) · /models/part.step#bracket/face 1');
  // The material and the mesh are about the whole part, so they tint nothing.
  expect(await prompt(['Select 6061-T6'])).toEqual({ tinted: false, pressed: 'true', text: 'Made of 6061-T6 (yield 276 MPa) · /models/part.step#bracket' });
  expect((await prompt(['Expand Details', 'Select Mesh'])).text).toBe('Mesh of 1.9 mm elements, refined from 2.8 mm · /models/part.step#bracket');
});

it('one check heads the verdict in its own words, then one list: the setup, What you see, Details', () => {
  mount({ ...STUDIED, ...factored(1.5) }, undefined, { faces: FACES });
  expect(verdictOf()).toMatchObject({ status: 'close', title: 'Close to the limit', caption: 'OK up to 1.5× this load', rows: [['close', 'Strength', '47 MPa, limit 276 MPa']] });
  // The verdict leads, then one list: the setup, What you see, Details.
  const body = verdictOf().section.parentElement!.parentElement!;
  expect(body.querySelectorAll('ul[aria-label="Study"]')).toHaveLength(1);
  expect(rowTexts(studyPanel()!).map(text => text!.replace(/‑/g, '-'))).toEqual(['Held at', 'Face 1', 'Pushed', '2500 N down', 'Made of', '6061-T6', 'What you see', 'Details']);
});

// The Load ramp, the renderer's own clip, played by hand.
const zOf = (mesh: Mesh, vertex: number) => mesh.geometry.getAttribute('position').getZ(vertex);
const own = () => loaded.own[0];
const play = (seconds: number) => act(() => { own().play.apply(seconds); });
const release = () => act(() => { own().play.release(); });

it('plays its Load ramp: the load going on from none, the deformation drawn with it, and back on release', () => {
  const { mesh } = mount(STUDIED, undefined, { faces: FACES });
  expect([own().id, own().label, own().duration]).toEqual(['fea:load-ramp', 'Load ramp', 2]);
  play(1);
  // Half the load on: half the 10x drawn.
  expect(zOf(mesh, 2)).toBeCloseTo(-0.01, 6);
  release();
  expect(zOf(mesh, 2)).toBeCloseTo(0, 6);
});

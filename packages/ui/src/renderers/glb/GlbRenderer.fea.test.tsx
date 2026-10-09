import React, { forwardRef, useImperativeHandle, useRef } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { BufferAttribute, BufferGeometry, Group, Mesh } from 'three';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

// The GLB renderer's FEA surfaces under the real shell, with only what loads the file and the WebGL
// viewport replaced: a result's study, field and deformation are Select's Study panel, its colour
// bar is a reading with no controls, and a GLB that is not a result has neither.
const loaded = vi.hoisted(() => ({ root: null as any, scene: null as any, revision: 'one', animation: null as any, runtime: null as any, host: null as any }));
vi.mock('../../../dist/renderers/kit/shell/ShellViewport.js', () => ({
  default: forwardRef(function StandInViewport(props: any, ref) {
    useImperativeHandle(ref, () => ({ requestRender() {} }));
    return <div data-stand-in-viewport="">{typeof props.children === 'function' ? props.children({ hostRef: { current: loaded.host || (loaded.runtime ? { clientWidth: 800, clientHeight: 600, style: {}, addEventListener() {}, removeEventListener() {} } : null) }, runtimeRef: { current: loaded.runtime }, mountRef: { current: null }, viewerReadyTick: 1, commitScene: () => true }) : props.children}</div>;
  })
}));
vi.mock('../../../dist/renderers/glb/useGlbScene.js', () => ({
  useGlbScene: () => ({ scene: loaded.scene, revision: loaded.revision, busy: false, error: null, progress: null })
}));
vi.mock('../../../dist/renderers/glb/useGlbAnimation.js', () => ({ useGlbAnimation: () => loaded.animation }));
import GlbRenderer from '../../../dist/renderers/glb/GlbRenderer.js';
import { writeFileView } from '../../../dist/renderers/kit/shell/fileView.js';
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
function resultRoot(extras: Record<string, unknown> | null, faces: number[] | null = null) {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new BufferAttribute(new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 1, 0]), 3));
  geometry.setIndex([0, 1, 2, 1, 3, 2]);
  geometry.setAttribute('color', new BufferAttribute(new Uint8Array(16).fill(7), 4, true));
  geometry.setAttribute('_von_mises', new BufferAttribute(new Float32Array([0, 50, 100, 25]), 1));
  geometry.setAttribute('_displacement', new BufferAttribute(new Float32Array([0, 0, 0, 0, 0, 0.001, 0, 0, 0.002, 0, 0, 0.0005]), 3));
  if (faces) geometry.setAttribute('_face', new BufferAttribute(new Float32Array(faces), 1));
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

function mount(extras: Record<string, unknown> | null, state?: unknown, { actions = () => {}, host = testHost(), faces = null, settings = { toolStack: { panels: {}, collapsed: {} } } }: { actions?: (actions: readonly any[]) => void, host?: any, faces?: number[] | null, settings?: any } = {}) {
  const built = resultRoot(extras, faces);
  loaded.root = built.root;
  // One scene per file, as the hook holds it: a render is not a new result.
  loaded.scene = { document: { scene: built.root }, revision: loaded.revision };
  const slot = document.createElement('div');
  slot.setAttribute('data-test-navbar', '');
  document.body.append(slot);
  const save = vi.fn();
  const preferences = { getSnapshot: () => settings, subscribe: () => () => {}, update() {} };
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

it('puts the field and deformation in Study, under Select, and a colour bar with one plain line on the view', () => {
  const { container } = mount(RESULT);
  const bar = container.querySelector('[role="group"][aria-label="von Mises stress colour bar"]')!;
  expect(bar.querySelector('[data-fea-summary]')!.textContent).toBe('Peak stress 47 MPa · holds 5.8× this load · moves up to 0.029 mm');
  expect(bar.textContent).toContain('47.3 MPa');
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

it('the field switch recolours the mesh and changes the bar\'s line', () => {
  const { mesh, container } = mount(RESULT);
  const stress = colourBytes(mesh);
  expect(stress.slice(0, 4)).toEqual([13, 26, 230, 255]);
  act(() => { fireEvent.click(screen.getByRole('combobox', { name: 'Result field' })); });
  act(() => { fireEvent.click(screen.getByRole('option', { name: 'Displacement' })); });
  expect(colourBytes(mesh)).not.toEqual(stress);
  const bar = container.querySelector('[role="group"][aria-label="displacement colour bar"]')!;
  expect(bar.querySelector('[data-fea-summary]')!.textContent).toBe('Moves up to 0.029 mm');
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

it('the colour bar shows its whole line: it is never truncated, and the card grows to fit it', () => {
  const { container } = mount({ ...RESULT });
  const summary = container.querySelector('[data-fea-summary]') as HTMLElement;
  expect(summary.textContent).toBe('Peak stress 47 MPa · holds 5.8× this load · moves up to 0.029 mm');
  expect(summary.className).not.toMatch(/truncate|ellipsis|overflow-hidden|whitespace-nowrap/);
  const card = container.querySelector('[aria-label$="colour bar"]') as HTMLElement;
  expect(card.className).toContain('w-max');
  expect(card.className).toContain('max-w-full');
  expect(card.className).not.toMatch(/(^|\s)w-72(\s|$)/);
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

// What the result's checks found: errors first, as the card a board's are.
const PEAK = { check: 'fea', severity: 'error', type: 'peak', summary: 'The peak stress, 120 MPa, is above the 100 MPa this material yields at',
  description: 'The peak stress is above yield.', items: [{ text: 'the peak stress', ref: '#o1.f3', at: [10, 20, 30] }, { text: 'a fixed face', ref: '#o1.f1', at: [0, 0, 0] }] };
const SOFT = { check: 'fea', severity: 'warning', type: 'bend', summary: 'The part bends visibly: 0.4 mm', description: 'It bends.', items: [{ text: 'the tip', ref: null }] };
const FOUND = { ...RESULT, document: 'part.step', occurrence: 'o1' };
const alertCard = () => screen.queryByRole('alert');

it('opens the card for what must be fixed, listing errors under their heading and the rest under Suggestions', () => {
  const actions = vi.fn();
  mount({ ...FOUND, findings: [SOFT, PEAK] }, undefined, { actions });
  const card = alertCard()!;
  expect(card.textContent).toContain('1 to fix, 1 suggestion');
  expect(card.textContent).toContain('Fix before using');
  expect(card.textContent).toContain('Suggestions');
  expect(Array.from(card.querySelectorAll('[data-finding-row]')).map(row => row.textContent)).toEqual([PEAK.summary, SOFT.summary]);
  expect(card.querySelector('[data-report-issue]')).toBeNull();
  // Nothing is in the navbar while the card is up.
  expect(actions.mock.calls.flat(2).filter((action: any) => action?.label)).toEqual([]);
});

it('puts suggestions alone away, their icon in the navbar saying what is there, and brings the card back from it', () => {
  const actions = vi.fn();
  mount({ ...FOUND, findings: [SOFT] }, undefined, { actions });
  expect(alertCard()).toBeNull();
  const published = actions.mock.calls.at(-1)![0];
  expect(published.map((action: any) => action.label)).toEqual(['1 suggestion']);
  act(() => { published[0].onInvoke(); });
  expect(alertCard()!.textContent).toContain('The part bends visibly');
  expect(alertCard()!.textContent).not.toContain('Fix before using');
});

it('a GLB with no findings, or whose findings are not a list, raises no card', () => {
  mount({ ...FOUND, findings: [] });
  expect(alertCard()).toBeNull();
  cleanup();
  mount({ ...FOUND, findings: 'nope' });
  expect(alertCard()).toBeNull();
  expect(document.querySelector('[data-quick-edit-chip]')).toBeNull();
});

it('choosing a finding puts the card away, rings the places it names and carries its sentence and the part\'s face into Quick Edit', async () => {
  const copied: string[] = [];
  const host = testHost({ clipboard: { writeText: async (text: any) => { copied.push(await text); }, readText: async () => '', writeImage: async () => {} } });
  const actions = vi.fn();
  mount({ ...FOUND, findings: [PEAK, SOFT] }, undefined, { host, actions });
  expect(document.querySelector('[data-fea-finding-rings]')).toBeNull();
  act(() => { fireEvent.click(screen.getByText(PEAK.summary)); });
  expect(alertCard()).toBeNull();
  expect(actions.mock.calls.at(-1)![0].map((action: any) => action.label)).toEqual(['1 to fix, 1 suggestion']);
  expect(document.querySelector('[data-fea-finding-rings]')).toBeTruthy();
  const box = screen.getByRole('region', { name: 'Quick Edit' });
  expect(box.querySelector('[data-quick-edit-chip="references"]')!.textContent).toBe('2 refs');
  const note = screen.getByRole('textbox', { name: 'Describe your changes' });
  act(() => { fireEvent.change(note, { target: { value: 'thicken it' } }); });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy Prompt' })); });
  // The STEP the result records, beside the GLB, named by its faces, after the sentence.
  expect(copied).toEqual([`thicken it\n\nFile: /models/part.glb\nReferences:\n${PEAK.summary} · /models/part.step#o1.f1,o1.f3`]);
});

it('a finding about no face names the whole part, and a result that names no source offers no reference', async () => {
  const copied: string[] = [];
  const host = testHost({ clipboard: { writeText: async (text: any) => { copied.push(await text); }, readText: async () => '', writeImage: async () => {} } });
  const actions = vi.fn();
  mount({ ...FOUND, findings: [SOFT] }, undefined, { actions, host });
  act(() => { actions.mock.calls.at(-1)![0][0].onInvoke(); });
  act(() => { fireEvent.click(screen.getByText(SOFT.summary)); });
  expect(screen.getByRole('region', { name: 'Quick Edit' }).querySelector('[data-quick-edit-chip="references"]')!.textContent).toBe('1 ref');
  act(() => { fireEvent.change(screen.getByRole('textbox', { name: 'Describe your changes' }), { target: { value: 'thicken it' } }); });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Copy Prompt' })); });
  expect(copied).toEqual([`thicken it\n\nFile: /models/part.glb\nReferences:\n${SOFT.summary} · /models/part.step#o1`]);
  cleanup();
  mount({ ...FOUND, document: '', findings: [PEAK] });
  act(() => { fireEvent.click(screen.getByText(PEAK.summary)); });
  expect(screen.queryByRole('region', { name: 'Quick Edit' })).toBeNull();
  expect(document.querySelector('[data-fea-finding-rings]')).toBeTruthy();
});

it('lets go of a chosen finding\'s ring on Escape and when the card is brought back, with no reference to clear it through Quick Edit', () => {
  const actions = vi.fn();
  const { container } = mount({ ...FOUND, document: '', findings: [PEAK] }, undefined, { actions });
  const rings = () => document.querySelector('[data-fea-finding-rings]');
  act(() => { fireEvent.click(screen.getByText(PEAK.summary)); });
  expect(rings()).toBeTruthy();
  act(() => { fireEvent.keyDown(container.querySelector('[data-stand-in-viewport]')!, { key: 'Escape' }); });
  expect(rings()).toBeNull();
  // Chosen again, then the card comes back from its icon: nothing is chosen under it.
  expect(alertCard()).toBeNull();
  act(() => { actions.mock.calls.at(-1)![0][0].onInvoke(); });
  act(() => { fireEvent.click(screen.getByText(PEAK.summary)); });
  expect(rings()).toBeTruthy();
  act(() => { actions.mock.calls.at(-1)![0][0].onInvoke(); });
  expect(alertCard()).toBeTruthy();
  expect(rings()).toBeNull();
});

it('rings each place at the deformed position under the camera, and follows the deformation scale', () => {
  const arcs: number[][] = [];
  const context = { setTransform() {}, clearRect() {}, beginPath() {}, stroke() {}, arc: (...args: number[]) => { arcs.push(args); } } as any;
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context);
  let frame: (() => void) | null = null;
  vi.stubGlobal('requestAnimationFrame', (callback: () => void) => { frame = callback; return 1; });
  vi.stubGlobal('cancelAnimationFrame', () => {});
  const camera = new THREE.OrthographicCamera(-0.05, 0.05, 0.0375, -0.0375, 0.001, 10);
  camera.position.set(0, 0, 1);
  camera.updateMatrixWorld();
  loaded.runtime = { THREE, camera };
  mount({ ...FOUND, findings: [{ ...PEAK, items: [{ text: 'the tip', ref: '#o1.f3', at: [0, 10, 0] }] }] });
  act(() => { fireEvent.click(screen.getByText(PEAK.summary)); });
  const paint = () => { arcs.length = 0; act(() => { frame!(); }); return arcs.map(([x, y]) => [Math.round(x), Math.round(y)]); };
  // CAD (0, 10, 0) mm is glTF (0, 0, -0.01) m: the screen's centre, before the displacement moves it.
  expect(paint()).toEqual([[400, 300]]);
});

it('moves a ring when Study\'s scale changes on a result that displaces', () => {
  const arcs: number[][] = [];
  const context = { setTransform() {}, clearRect() {}, beginPath() {}, stroke() {}, arc: (...args: number[]) => { arcs.push(args); } } as any;
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context);
  let frame: (() => void) | null = null;
  vi.stubGlobal('requestAnimationFrame', (callback: () => void) => { frame = callback; return 1; });
  vi.stubGlobal('cancelAnimationFrame', () => {});
  // Looking down -x, so the displacement along z is sideways on the screen: screen x is minus z.
  const camera = new THREE.OrthographicCamera(-0.05, 0.05, 0.0375, -0.0375, 0.001, 10);
  camera.position.set(1, 0, 0);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld();
  loaded.runtime = { THREE, camera };
  // The CAD point of the third vertex before it moves: glTF (0, 1, -0.02) m.
  mount({ ...FOUND, findings: [{ ...PEAK, items: [{ text: 'the tip', ref: '#o1.f3', at: [0, 20, 1000] }] }] });
  act(() => { fireEvent.click(screen.getByText(PEAK.summary)); });
  const paint = () => { arcs.length = 0; act(() => { frame!(); }); return Math.round(arcs[0][0]); };
  // At the file's own 10x the vertex has moved 0.02 m back to z = 0, the screen's middle.
  expect(paint()).toBe(400);
  const value = screen.getByRole('textbox', { name: 'Deformation scale value' });
  act(() => { fireEvent.change(value, { target: { value: '0' } }); fireEvent.blur(value); });
  // At none it is where the part was solved: 0.02 m across, 160px.
  expect(paint()).toBe(560);
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

it('Study lists the material, the fixed faces, each load with its faces and the mesh, then the Result', () => {
  mount(STUDIED, undefined, { faces: FACES });
  const study = studyPanel()!;
  expect(study.querySelector('h3')!.textContent).toBe('Study');
  expect(study.querySelector('button[aria-label="Close study"]')).toBeTruthy();
  expect(rowTexts(study)).toEqual([
    'Material6061\u2011T6 · yield 276\u00a0MPa', 'Fixed', 'Face 1fixed', 'Loads', '2500 Ndown', 'Face 2loaded',
    'Mesh1.9\u00a0mm elements · refined from 2.8\u00a0mm', 'Result',
  ]);
  expect(study.querySelector('[role="combobox"][aria-label="Result field"]')).toBeTruthy();
  // Material's and Mesh's details wrap rather than being cut off at the one width.
  const details = Array.from(study.querySelectorAll('[data-study-detail]'));
  // ... between words only: a hyphenated name and a number with its unit never part.
  expect(details.map(detail => detail.textContent)).toEqual(['6061\u2011T6 · yield 276\u00a0MPa', '1.9\u00a0mm elements · refined from 2.8\u00a0mm']);
  for (const detail of details) expect(detail.className).not.toMatch(/truncate|whitespace-nowrap/);
  for (const detail of details) expect((detail.closest('[data-study-row]') as HTMLElement).style.height).toBe('auto');
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
  expect(rowTexts(study)).toEqual(['Result']);
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
  act(() => { fireEvent.click(screen.getByRole('button', { name: 'Select 2500 N' })); });
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

const ASSEMBLED = {
  ...STUDIED, faces: ['#o1.1.f1', '#o1.2.f1', '#o1.1.f9'], weakest_part: 'post', weakest_part_peak_MPa: 180, safety_factor: 1.46, max_displacement_mm: 0.2,
  parts: [
    { ref: '#o1.1', name: 'post', material: '6061-T6', yield_MPa: 276, peak_MPa: 180, safety_factor: 1.46, max_displacement_mm: 0.2 },
    { ref: '#o1.2', name: 'base', material: 'Steel', yield_MPa: 250, peak_MPa: 40, safety_factor: 2.5, max_displacement_mm: 0.01 },
  ],
  connections: [{ between: ['#o1.1', '#o1.2'], names: ['post', 'base'], type: 'bonded', area_mm2: 100, gap_mm: 0, faces: ['#o1.1.f1', '#o1.2.f1'] }],
};
function mountAssembly(copied: string[]) {
  const built = mount(ASSEMBLED, undefined, { faces: [0, 0, 2, 1], host: clipboardHost(copied) });
  built.mesh.geometry.setAttribute('_part', new BufferAttribute(new Float32Array([0, 0, 0, 1]), 1));
  return built;
}

it('an assembly\'s Study lists Parts and Connections rows and the colour bar names the weakest part', () => {
  mountAssembly([]);
  expect(document.querySelector('[data-study-row="part:0"]')!.textContent).toContain('post');
  expect(document.querySelector('[data-study-row="part:0"]')!.textContent!.replace(/\u2011/g, '-')).toContain('6061-T6 · holds 1.4×');
  // The detail wraps between words rather than being cut off.
  expect(document.querySelector('[data-study-row="part:0"] [data-study-detail]')!.className).not.toMatch(/truncate|ellipsis|overflow-hidden|whitespace-nowrap/);
  expect(document.querySelector('[data-study-row="joint:0"]')!.textContent).toContain('post ↔ base');
  expect(document.querySelector('[data-study-row="joint:0"]')!.textContent!.replace(/\u00a0/g, ' ')).toContain('bonded · 100 mm²');
  expect(document.querySelector('[data-fea-summary]')!.textContent).toBe('Weakest: post · peak stress 180 MPa · holds 1.4× this load · the assembly moves up to 0.029 mm');
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

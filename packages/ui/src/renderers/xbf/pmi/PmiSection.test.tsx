import React from 'react';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import PmiSection from '../../../../dist/renderers/xbf/pmi/PmiSection.js';
import { useXbfPmi } from '../../../../dist/renderers/xbf/pmi/useXbfPmi.js';
import { usePmiViewApplied } from '../../../../dist/renderers/xbf/pmi/usePmiView.js';
import { presentXbfTree } from '../../../../dist/renderers/xbf/xbfTree.js';
import { createViewSettingsStore } from '../../../../dist/renderers/kit/view-settings/viewSettingsStore.js';
import FileSidebar from '../../../../dist/renderers/kit/tools/FileSidebar.js';

const restores: (() => void)[] = [];
function override(target: object, key: string, descriptor: PropertyDescriptor) {
  const previous = Object.getOwnPropertyDescriptor(target, key);
  Object.defineProperty(target, key, { configurable: true, ...descriptor });
  restores.push(() => previous ? Object.defineProperty(target, key, previous) : delete (target as any)[key]);
}
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  // A menu's and a select's content, which jsdom cannot lay out or point at.
  override(Element.prototype, 'scrollIntoView', { value() {} });
  for (const name of ['setPointerCapture', 'releasePointerCapture']) override(Element.prototype, name, { value() {} });
  override(Element.prototype, 'hasPointerCapture', { value: () => false });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); while (restores.length) restores.pop()!(); });
const section = (overrides: Record<string, unknown>) => ({ changes: [], pending: [], hiddenKeys: [], constructions: new Map(), editable: false,
  selectedEntry: null, selectedKey: '', hover: () => {}, select: () => {}, toggleHidden: () => {}, edit: () => {}, focusDatum: () => {}, ...overrides });
const datum = (part: number, letter: string, face: string) => ({ key: `${part}:${letter}`, id: letter, kind: 'datum', part, status: 'ok', supported: true,
  datum: { letter }, glyph: 'datum', callout: { text: `Datum ${letter}` }, featureIds: [face], refs: [] });
const position = (part: number, datums: string[], face: string) => ({ key: `${part}:hole-pos`, id: 'hole-pos', kind: 'geometric_tolerance', part, status: 'ok',
  supported: true, glyph: 'position', tolerance: { characteristic: 'position', value: 0.1, unit: 'mm', zone: 'diameter', datums },
  callout: { text: `Position ⌀0.1 | ${datums.join(' | ')}`, title: 'Position', diameter: true, value: '0.1' }, featureIds: [face], refs: [] });

it('opens a selected callout even when a different geometry face remains picked', () => {
  const a = datum(0, 'A', 'face-a'), b = datum(0, 'B', 'face-b');
  render(<PmiSection pmi={section({ entries: [a, b], selectedEntry: b, selectedKey: b.key }) as any} picked={[]} moving={false} selectedFeatureIds={['face-a']} />);
  expect(screen.getByRole('button', { name: 'Datum B', exact: true })).toBeTruthy();
  expect(screen.getByText('Letter')).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Datum A', exact: true })).toBeNull();
});

it('lists two parts\' datum A apart, and a position offers its own part\'s datums alone', () => {
  const errors = vi.spyOn(console, 'error').mockImplementation(() => {});
  const pegs = position(1, ['B'], 'i1/face/2');
  const entries = [datum(0, 'A', 'i0/face/5'), datum(1, 'A', 'i1/face/1'), datum(1, 'B', 'i1/face/3'), pegs];
  render(<PmiSection pmi={section({ entries }) as any} picked={[]} moving={false} />);
  expect(screen.getAllByRole('button', { name: 'Datum A', exact: true })).toHaveLength(2);
  cleanup();
  render(<PmiSection pmi={section({ entries, editable: true, selectedEntry: pegs, selectedKey: pegs.key }) as any} picked={[]} moving={false} />);
  expect([...document.querySelectorAll('[data-pmi-datum-choice]')].map(choice => choice.getAttribute('data-pmi-datum-choice'))).toEqual(['A', 'B']);
  expect(errors.mock.calls.flat().join(' ')).not.toMatch(/same key/);
});

it('picks a related annotation from a datum\'s values with the whole list shown', () => {
  const a = datum(0, 'A', 'face-a'), uses = position(0, ['A'], 'face-b');
  function Harness() {
    const [key, setKey] = React.useState(a.key);
    const entries = [a, uses];
    return <PmiSection pmi={section({ entries, selectedKey: key, selectedEntry: entries.find(entry => entry.key === key), select: setKey }) as any}
      picked={[]} moving={false} />;
  }
  render(<Harness />);
  // The datum picked: the list follows its face, and its values say what uses it.
  expect(screen.queryByRole('button', { name: 'Position ⌀0.1 | A', exact: true })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Position ⌀0.1 | A', exact: true }));
  expect(screen.getByRole('button', { name: 'Position ⌀0.1 | A', exact: true }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('button', { name: 'Datum A', exact: true })).toBeTruthy();
});

const basicFromLeft = (overrides: Record<string, unknown> = {}) => ({ key: '0:hole-from-left', id: 'hole-from-left', kind: 'dimension', part: 0, status: 'ok',
  supported: true, glyph: 'dimension', statusText: '', featureIds: ['i0/face/9'], refs: [], callout: { text: '44 basic' },
  dimension: { type: 'distance', basic: true, nominal: 44, unit: 'mm', source: 'geometry', tolerance: null }, ...overrides });

it('says a nominal another system\'s file gives as the file\'s, and one the engine measured as measured', () => {
  const measured = basicFromLeft();
  render(<PmiSection pmi={section({ entries: [measured], selectedEntry: measured, selectedKey: measured.key }) as any} picked={[]} moving={false} />);
  expect(screen.getByText(', measured')).toBeTruthy();
  cleanup();
  const given = basicFromLeft({ dimension: { ...basicFromLeft().dimension, source: 'file' } });
  render(<PmiSection pmi={section({ entries: [given], selectedEntry: given, selectedKey: given.key }) as any} picked={[]} moving={false} />);
  expect(screen.getByText(', from the file')).toBeTruthy();
  expect(screen.queryByText(', measured')).toBeNull();
  expect(document.querySelector('[title="Measured on the geometry by the engine"]')).toBeNull();
});

// ---- the MBD panel, over the engine's v4 plate: its views, notes, coverage and annotations ----------
// The plate's served document (`pmi_plate/v4`), its part on a scene that knows no geometry: what is
// drawn is drawn where its code (or a view) placed it.
const FIXTURES = join(dirname(createRequire(import.meta.url).resolve('@text-to-cad/core/lib/xbf/xbfDocument.js')), '__fixtures__');
const V4 = JSON.parse(readFileSync(join(FIXTURES, 'pmi_plate', 'v4', 'structure.json'), 'utf8'));
const V4_BOTTOM = 'plate/f:edit_plate.body_make_box1.5;M:edit_plate.body';
const PLATE = { min: [-50, -30, -5], max: [50, 30, 5] };
const EIGHTH_Z = [Math.SQRT1_2, Math.SQRT1_2, 0, 0, -Math.SQRT1_2, Math.SQRT1_2, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const BEFORE = { position: [100, -100, 100], target: [0, 0, 0], up: [0, 0, 1] };
let live: any;
const NOWHERE = () => ({ camera: null, clip: null });
function Mbd({ structure, viewer, store, fit, picked = [], here = NOWHERE }: any) {
  const scene = React.useMemo(() => ({ structure, elementGeometry: () => null, describeElement: () => null, selectionBounds: () => PLATE }), [structure]);
  const tree = React.useMemo(() => presentXbfTree(structure), [structure]);
  const [selectedKey, select] = React.useState('');
  const pmi = useXbfPmi({ scene, tree, bounds: PLATE, moving: false, editable: true, selectedKey, onSelect: select, here });
  usePmiViewApplied({ applied: pmi.view, viewer: () => viewer, store, fit });
  live = pmi;
  return <PmiSection pmi={pmi} picked={picked} moving={false} />;
}
function openMbd(edit = (structure: any) => structure, { sidebar = false, ...props }: Record<string, unknown> = {}) {
  const viewer = { getPerspective: vi.fn(() => BEFORE), setPerspective: vi.fn(() => true) };
  const store = createViewSettingsStore({ mode: 'solid' });
  const fit = vi.fn((at: any) => ({ position: at.direction.map((c: number) => c * 200), target: [0, 0, 0], up: at.up }));
  const mbd = <Mbd structure={edit(structuredClone(V4))} viewer={viewer} store={store} fit={fit} {...props} />;
  // In the file sidebar, as the renderer shows it: its head holds New.
  render(sidebar ? <FileSidebar layout={{ panels: {}, collapsed: {} }} onLayoutChange={() => {}}>{mbd}</FileSidebar> : mbd);
  return { viewer, store, fit };
}
const drawnKeys = () => live.items.map((item: any) => item.key);
const headings = () => screen.getAllByRole('heading', { level: 2 }).map(heading => heading.textContent);
const rowsOf = (title: string) => within(screen.getByRole('region', { name: title })).queryAllByRole('listitem').map(row => row.textContent);
const ALL_DRAWN = ['0:A', '0:thickness', '0:hole-diameter', '0:hole-from-front', '0:hole-from-left', '0:top-flatness', '0:hole-position', '0:hole-profile', '0:mask'];

it('groups views, notes, coverage and annotations under static headings', () => {
  // A view "A" beside the datum A: a view and an annotation may share a key, and are kept apart.
  openMbd(structure => ({ ...structure, pmi_views: [...structure.pmi_views, { ...structure.pmi_views[1], name: 'A', shows: ['A'] }] }));
  expect(headings()).toEqual(['Views', 'Notes', 'Coverage', 'Annotations']);
  // Nothing folds: every group is open, its heading no button.
  expect(screen.queryByRole('button', { name: 'Views' })).toBeNull();
  expect(rowsOf('Views')).toEqual(['A-A4 annotations', 'isoAll', 'A1 annotation']);
  expect(rowsOf('Notes')).toEqual(['1. Unless otherwise noted, all surfaces profile 0.5 to A', '2. Break all sharp edges 0.2 max', '3. Mask these features before coating with primer']);
  // The flag note its flag, the general profile its profile, a general note none.
  expect([...document.querySelectorAll('[data-pmi-note]')].map(row => row.querySelector('[data-pmi-glyph]')?.getAttribute('data-pmi-glyph') || ''))
    .toEqual(['surface_profile', '', 'flag']);
  expect(within(screen.getByRole('region', { name: 'Coverage' })).getByText('Every face has a requirement')).toBeTruthy();
  // The annotations as before, but the notes: limits stacked in words as the callout says them.
  expect([...screen.getByRole('region', { name: 'Annotations' }).querySelectorAll('[data-pmi-pick]')].map(row => row.getAttribute('aria-label')))
    .toEqual(['Datum A', '9.8–10.2', '⌀10.0 +0.1/0', '30 basic', '50 basic', 'Flatness 0.05', 'Position ⌀0.1 | A', 'Surface profile 0.2 | A']);
  // A flag note picked lights its faces, and lets go when picked again.
  const mask = () => screen.getByRole('button', { name: 'Note 3: Mask these features before coating with primer', exact: true });
  fireEvent.click(mask());
  expect(mask().getAttribute('aria-pressed')).toBe('true');
  expect(live.highlight.selected).toEqual(['i0/face/7']);
  fireEvent.click(mask());
  expect(live.highlight.selected).toEqual([]);
  // View "A" picked leaves datum A unpicked, and datum A picked leaves view "A" applied.
  fireEvent.click(screen.getByRole('button', { name: 'A', exact: true }));
  expect(screen.getByRole('button', { name: 'A', exact: true }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('button', { name: 'Datum A', exact: true }).getAttribute('aria-pressed')).toBe('false');
  fireEvent.click(screen.getByRole('button', { name: 'Datum A', exact: true }));
  expect(screen.getByRole('button', { name: 'Datum A', exact: true }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('button', { name: 'A', exact: true }).getAttribute('aria-pressed')).toBe('true');
  expect(drawnKeys()).toEqual(['0:A']);
});

it("two parts' views of one name each say their part, as their notes do", () => {
  // A second part, the lid, placed beside the plate and given an iso view of its own.
  openMbd(structure => ({ ...structure,
    prototypes: [...structure.prototypes, { ...structure.prototypes[0], index: 1, name: 'lid' }],
    instances: [...structure.instances, { ...structure.instances[0], prototype: 1, path: 'plate/lid' }],
    tree: { ...structure.tree, children: [...structure.tree.children, { name: 'lid', prototype: 1, instance: 1 }] },
    pmi_views: [...structure.pmi_views, { ...structure.pmi_views[1], part: 1 }] }));
  expect(rowsOf('Views')).toEqual(['A-A4 annotationsplate', 'isoAllplate', 'isoAlllid']);
  cleanup();
  // One part's views say none.
  openMbd();
  expect(rowsOf('Views')).toEqual(['A-A4 annotations', 'isoAll']);
});

it('says there is no PMI yet only where a document has none at all, views included', () => {
  // Views alone: listed, and no word of there being nothing.
  openMbd(structure => ({ ...structure, pmi: [], pmi_coverage: [] }));
  expect(headings()).toEqual(['Views']);
  expect(screen.queryByText(/No PMI yet/)).toBeNull();
  cleanup();
  openMbd(structure => ({ ...structure, pmi: [], pmi_views: [], pmi_coverage: [] }));
  expect(screen.getByText("No PMI yet: add some from a face's menu.")).toBeTruthy();
});

it("a view's row applies its camera, section and PMI, and a second pick leaves it", () => {
  const { viewer, store, fit } = openMbd();
  expect(drawnKeys()).toEqual(ALL_DRAWN);
  const row = () => screen.getByRole('button', { name: 'A-A', exact: true });
  fireEvent.click(row());
  expect(row().getAttribute('aria-pressed')).toBe('true');
  // Seen down its camera, fitted to its part where it stands, through the viewer's own camera.
  expect(fit).toHaveBeenLastCalledWith(expect.objectContaining({ key: '0:A-A', direction: [0, -1, 0], up: [0, 0, 1], bounds: PLATE }));
  expect(viewer.setPerspective).toHaveBeenLastCalledWith({ position: [0, -200, 0], target: [0, 0, 0], up: [0, 0, 1] });
  // Cut as its section says, the Clip's own settings; only what it shows drawn, at its own placements.
  expect(store.getSnapshot().display.clip).toEqual({ enabled: true, axis: 'y', at: 0, invert: true, partColors: true });
  expect(drawnKeys()).toEqual(['0:hole-diameter', '0:hole-position', '0:hole-profile', '0:mask']);
  expect(live.constructions.get('0:hole-diameter').label).toEqual([20, 0, 10]);
  // Picked again: the camera, the Clip and the PMI as they were.
  fireEvent.click(row());
  expect(row().getAttribute('aria-pressed')).toBe('false');
  expect(viewer.setPerspective).toHaveBeenLastCalledWith(BEFORE);
  expect(store.getSnapshot().display.clip).toBeUndefined();
  expect(drawnKeys()).toEqual(ALL_DRAWN);
  expect(live.constructions.get('0:hole-diameter').label).toEqual([20, 15, 5]);
});

it('the coverage checkbox lights the faces with no requirement', () => {
  // Test-owned coverage: the bottom uncovered, a datum nothing names.
  openMbd(structure => ({ ...structure, pmi_coverage: [{ part: 0, uncovered: [V4_BOTTOM],
    conflicts: [{ kind: 'unused_datum', ids: ['B'], problem: 'datum B is named by no tolerance' }] }] }));
  const coverage = within(screen.getByRole('region', { name: 'Coverage' }));
  expect(coverage.getByText('1 face has no requirement')).toBeTruthy();
  const conflict = coverage.getByRole('status');
  expect(conflict.textContent).toBe('B: datum B is named by no tolerance');
  expect(conflict.className).toMatch(/text-amber-500/);
  // Off, it lights nothing, and the section still says what it found.
  const show = screen.getByRole('checkbox', { name: 'Show faces with no requirement' });
  expect(show.getAttribute('aria-checked')).toBe('false');
  expect(live.highlight.selected).toEqual([]);
  fireEvent.click(show);
  expect(show.getAttribute('aria-checked')).toBe('true');
  expect(live.highlight.selected).toEqual(['i0/face/5']);
  fireEvent.click(show);
  expect(live.highlight.selected).toEqual([]);
});

it('coverage asks what the requirements leave open, with the answer the engine suggests', () => {
  // Test-owned: the engine's words, drawn as given; a question, never a warning.
  openMbd(structure => ({ ...structure, pmi_coverage: [{ part: 0, uncovered: [], conflicts: [],
    suggestions: [{ kind: 'hole', faces: [V4_BOTTOM], question: 'What is the 9 mm hole for?',
      answer: 'dimensional_size("hole-1-size", ...)', why: "9 mm is ISO 273's medium clearance hole for M8" }] }] }));
  const coverage = within(screen.getByRole('region', { name: 'Coverage' }));
  expect(coverage.getByText('What is the 9 mm hole for?')).toBeTruthy();
  const answer = coverage.getByText('dimensional_size("hole-1-size", ...)');
  expect(answer.tagName).toBe('CODE');
  expect(coverage.queryByRole('status')).toBeNull();
  expect(answer.closest('[data-pmi-suggestion]')?.getAttribute('data-pmi-suggestion')).toBe('hole');
});

it("a view whose section is off the placement's axes says so and applies its camera alone", () => {
  // The plate placed an eighth turn about z: the section's y is no world axis there.
  const { viewer, store, fit } = openMbd(structure => ({ ...structure, instances: structure.instances.map((instance: any) => ({ ...instance, matrix: EIGHTH_Z })) }));
  const row = screen.getByRole('button', { name: "A-A: Its section is not on this placement's axes", exact: true });
  expect(screen.getByText("Its section is not on this placement's axes")).toBeTruthy();
  fireEvent.click(row);
  const [{ direction }] = fit.mock.lastCall as any;
  expect(direction.map((c: number) => Number(c.toFixed(9)))).toEqual([Number(Math.SQRT1_2.toFixed(9)), -Number(Math.SQRT1_2.toFixed(9)), 0]);
  expect(viewer.setPerspective).toHaveBeenCalledTimes(1);
  expect(store.getSnapshot().display.clip).toBeUndefined();
  expect(drawnKeys()).toEqual(['0:hole-diameter', '0:hole-position', '0:hole-profile', '0:mask']);
});

it('a flag note naming annotations alone is listed with its flag, drawn nowhere, and its pick lights what they are on', () => {
  openMbd(structure => ({ ...structure, pmi: structure.pmi.map((item: any) => (item.id === 'mask' ? { ...item, refs: [], presentation: null } : item)) }));
  expect(drawnKeys()).not.toContain('0:mask');
  expect(document.querySelector('[data-pmi-note="mask"] [data-pmi-glyph]')?.getAttribute('data-pmi-glyph')).toBe('flag');
  // Drawn nowhere, it has no eye.
  expect(document.querySelector('[data-pmi-note="mask"] [data-pmi-visibility]')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Note 3: Mask these features before coating with primer', exact: true }));
  expect(live.highlight.selected).toEqual(['i0/face/7']);
});

// ---- New: what a model-based definition adds, each the call it asks the code for -------------------
const V4_HOLE = 'plate/f:edit_plate.cut.1;M:edit_plate.body';
const HOLE_FACE = { id: 'i0/face/7', part: 0, ref: V4_HOLE, surface: { type: 'cylinder', axis: [0, 0, 1], origin: [0, 0, 0], radius: 5 } };
// A new annotation's request, of the names its call takes from cadgen.ap242.
const ADD = (...names: string[]) => `Add this PMI to the annotate(...) call of the model's part "plate" (from cadgen.ap242 import ${['annotate', ...names].join(', ')})`;
const requests = () => live.changeChips.map((chip: any) => chip.request);
const form = () => document.querySelector<HTMLElement>('[data-pmi-new]')!;
async function openNew(user: ReturnType<typeof userEvent.setup>, edit?: (structure: any) => any, props: Record<string, unknown> = {}) {
  openMbd(edit, { sidebar: true, ...props });
  await user.click(screen.getByRole('button', { name: 'PMI', exact: true }));
}
async function choose(user: ReturnType<typeof userEvent.setup>, kind: string) {
  await user.click(screen.getByRole('button', { name: 'New PMI', exact: true }));
  await user.click(document.querySelector<HTMLElement>(`[data-pmi-new-kind="${kind}"]`)!);
  expect(form().getAttribute('data-pmi-new')).toBe(kind);
}
const add = (user: ReturnType<typeof userEvent.setup>) => user.click(within(form()).getByRole('button', { name: 'Add to Quick Edit' }));

it('New offers, with nothing picked on a part of its own, a note and a view from here; a profile needs faces, and the part has its general profile', async () => {
  const user = userEvent.setup();
  await openNew(user);
  await user.click(screen.getByRole('button', { name: 'New PMI', exact: true }));
  const item = (kind: string) => document.querySelector(`[data-pmi-new-kind="${kind}"]`)!;
  expect(['profile', 'note', 'general_profile', 'view'].map(kind => [item(kind).hasAttribute('data-disabled'), item(kind).textContent]))
    .toEqual([[true, 'Surface profilePick faces of one part'], [false, 'Note'], [true, 'General profileIts part has one'], [false, 'View from here']]);
});

it('a surface profile on the faces picked, to its part\'s datums, and a general profile where its part has none', async () => {
  const user = userEvent.setup();
  await openNew(user, structure => ({ ...structure, pmi: structure.pmi.filter((item: any) => item.id !== 'general') }), { picked: [HOLE_FACE] });
  await choose(user, 'profile');
  // A value is the person's to give: until then, nothing to add.
  expect((within(form()).getByRole('button', { name: 'Add to Quick Edit' }) as HTMLButtonElement).disabled).toBe(true);
  await user.type(within(form()).getByRole('textbox', { name: 'Tolerance' }), '0.1{Enter}');
  await user.click(within(form()).getByRole('button', { name: 'A', exact: true }));
  await add(user);
  await choose(user, 'general_profile');
  await user.type(within(form()).getByRole('textbox', { name: 'Tolerance' }), '0.5{Enter}');
  await add(user);
  expect(requests()).toEqual([`${ADD('surface_profile_tolerance')}:\nsurface_profile_tolerance("profile", "${V4_HOLE}", 0.1, datums=["A"])`, `${ADD('general_profile')}:\ngeneral_profile("general", 0.5)`]);
  // Asked for, the part has one.
  await user.click(screen.getByRole('button', { name: 'New PMI', exact: true }));
  expect(document.querySelector('[data-pmi-new-kind="general_profile"]')!.hasAttribute('data-disabled')).toBe(true);
});

it("a note's words are the person's own, typed, and none given asks for nothing", async () => {
  const user = userEvent.setup();
  await openNew(user);
  await choose(user, 'note');
  expect(within(form()).getByText('A general note, on no face.')).toBeTruthy();
  expect((within(form()).getByRole('button', { name: 'Add to Quick Edit' }) as HTMLButtonElement).disabled).toBe(true);
  await user.type(within(form()).getByRole('textbox', { name: 'Note text' }), 'Deburr all holes{Enter}');
  await add(user);
  expect(requests()).toEqual([`${ADD('note')}:\nnote("note", "Deburr all holes")`]);
});

it('a view from here is the camera and the Clip now, in its part\'s frame, showing what is drawn; its name the person\'s to give', async () => {
  const user = userEvent.setup();
  let clip: any = { axis: 'y', at: 0, invert: true };
  await openNew(user, undefined, { here: () => ({ camera: { position: [0, -170, 0], target: [0, 0, 0], up: [0, 0, 1] }, clip }) });
  await choose(user, 'view');
  const name = within(form()).getByRole('textbox', { name: 'View name' }) as HTMLInputElement;
  expect(name.value).toBe('view');
  await user.clear(name);
  await user.type(name, 'front-cut{Enter}');
  await add(user);
  clip = null;
  await choose(user, 'view');
  await add(user);
  const shows = 'shows=["A", "thickness", "hole-diameter", "hole-from-front", "hole-from-left", "top-flatness", "hole-position", "hole-profile", "mask"]';
  expect(requests()).toEqual([
    `${ADD('camera', 'section', 'view')}:\nview("front-cut", camera=camera((0, -1, 0), (0, 0, 1)), ${shows}, section=section("y", 0, invert=True))`,
    `${ADD('camera', 'view')}:\nview("view", camera=camera((0, -1, 0), (0, 0, 1)), ${shows})`]);
  expect(live.changeChips.map((chip: any) => chip.label)).toEqual(['Add front-cut', 'Add view']);
});

it("a view from here is refused where its part's placement turns the Clip off the part's axes", async () => {
  const user = userEvent.setup();
  await openNew(user, structure => ({ ...structure, instances: structure.instances.map((instance: any) => ({ ...instance, matrix: EIGHTH_Z })) }),
    { here: () => ({ camera: { position: [0, -170, 0], target: [0, 0, 0], up: [0, 0, 1] }, clip: { axis: 'y', at: 0, invert: false } }) });
  await choose(user, 'view');
  expect(within(form()).getByText("Its section is not on this placement's axes")).toBeTruthy();
  expect((within(form()).getByRole('button', { name: 'Add to Quick Edit' }) as HTMLButtonElement).disabled).toBe(true);
});

it("a limits dimension's tolerance field reads back as its limits, and limits typed are asked for as limits()", async () => {
  const user = userEvent.setup();
  openMbd();
  fireEvent.click(screen.getByRole('button', { name: '9.8–10.2', exact: true }));
  const field = screen.getByRole('textbox', { name: 'Tolerance' }) as HTMLInputElement;
  expect(field.value).toBe('9.8–10.2');
  // Committed as it reads: nothing wrong, nothing asked.
  fireEvent.focus(field);
  fireEvent.blur(field);
  expect(screen.queryByRole('alert')).toBeNull();
  expect(live.changes).toEqual([]);
  await user.clear(field);
  await user.type(field, '9.9 to 10.2{Enter}');
  expect(requests()).toEqual([expect.stringMatching(/^Change the PMI "thickness" .*: tolerance=limits\(9\.9, 10\.2\)\. .*tolerance=limits\(9\.9, 10\.2\)/s)]);
});

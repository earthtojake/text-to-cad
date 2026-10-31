import React, { useState } from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FileSidebar from '../../../dist/renderers/kit/tools/FileSidebar.js';
import XbfPositionSection, { useXbfPose } from '../../../dist/renderers/xbf/XbfPositionSection.js';
import XbfModelTree from '../../../dist/renderers/xbf/XbfModelTree.js';
import { MeasureIcon as XbfMeasureIcon, SelectIcon as XbfSelectIcon, SelectModeMenu as XbfSelectModeMenu, XBF_SELECT_DEFAULT, xbfSelectModes } from '../../../dist/renderers/xbf/XbfSelectionModes.js';
import { presentXbfTree, xbfPickFrontier } from '../../../dist/renderers/xbf/xbfTree.js';
import { useXbfSelectionChips, xbfMassText, xbfMeasurementRows } from '../../../dist/renderers/xbf/xbfChips.js';
import { selectGeometryMode, treeShape } from '../../../dist/renderers/xbf/xbfSelectionFilter.js';
import { xbfModelMenu, xbfPartMenu } from '../../../dist/renderers/xbf/xbfMenus.js';
import { assemblyPartMenuEntries } from '../../../dist/renderers/xbf/xbfMenuItems.js';
import { selectRenderer } from '../../../dist/file-viewer/registry.js';
import { createXbfRenderer } from '../../../dist/renderers/xbf/index.js';
import QuickEdit from '../../../dist/renderers/kit/tools/quick-edit/QuickEdit.js';
import { ViewerHostContext } from '../../../dist/host/context.js';
import { testHost } from '../../../dist/host/testing/host.js';

// An engine document's panels are the ones a STEP's renderer had: the same Model tree over the same
// assembly, the same selection filter, the same Position section, the same chips. While that
// renderer was there the two were mounted over one fixture and their controls compared; the
// controls it drew are written down here, so the xbf cannot grow one a STEP's did not have. The
// viewport is the browser's.

Object.assign(globalThis, { React });
const restores: (() => void)[] = [];
function override(target: object, key: string, descriptor: PropertyDescriptor) {
  const previous = Object.getOwnPropertyDescriptor(target, key);
  Object.defineProperty(target, key, { configurable: true, ...descriptor });
  restores.push(() => previous ? Object.defineProperty(target, key, previous) : delete (target as any)[key]);
}
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  override(HTMLElement.prototype, 'clientHeight', { get(this: HTMLElement) { return this.hasAttribute('data-file-sidebar-room') ? 600 : 0; } });
  override(Element.prototype, 'scrollIntoView', { value() {} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); while (restores.length) restores.pop()!(); });

// One assembly: a hinge of a base and two arms of one part, and a pin beside it, as the engine serves it.
const structure = {
  name: 'fixture', version: '1-1', units: 'mm',
  prototypes: [
    { index: 0, key: 'k-base', name: 'base', color: null, faceNames: {}, edgeNames: {}, faceColors: {} },
    { index: 1, key: 'k-arm', name: 'arm', color: null, faceNames: { 4: 'f:arm.top' }, edgeNames: {}, faceColors: {} },
    { index: 2, key: 'k-pin', name: 'pin', color: null, faceNames: {}, edgeNames: {}, faceColors: {} },
  ],
  instances: [
    { prototype: 0, path: 'fixture/hinge/base', matrix: [], color: null },
    { prototype: 1, path: 'fixture/hinge/arm_1', matrix: [], color: null },
    { prototype: 1, path: 'fixture/hinge/arm_2', matrix: [], color: null },
    { prototype: 2, path: 'fixture/pin', matrix: [], color: null },
  ],
  tree: { name: 'fixture', children: [
    { name: 'hinge', children: [{ name: 'base', prototype: 0, instance: 0 }, { name: 'arm_1', prototype: 1, instance: 1 }, { name: 'arm_2', prototype: 1, instance: 2 }] },
    { name: 'pin', prototype: 2, instance: 3 },
  ] },
};

it("the tree is a STEP's: the document's wrapper is no row, repeated parts fold, a collapsed assembly is picked as a unit", () => {
  const tree = presentXbfTree(structure);
  expect(tree.roots.map((node: any) => [node.kind, node.label, node.selectionId])).toEqual([['assembly', 'hinge', 'n0.0'], ['part', 'pin', 'i3']]);
  expect(tree.roots[0].children.map((node: any) => node.label)).toEqual(['base', 'arm (2)']);
  expect(tree.roots[0].children[1].memberSelectionIds).toEqual(['i1', 'i2']);
  // A press on an arm takes the hinge while it is shut, the arm once it is open.
  expect(xbfPickFrontier(tree, 'i1', new Set())).toBe('n0.0');
  expect(xbfPickFrontier(tree, 'i1', new Set(['n0.0']))).toBe('i1');
  expect(presentXbfTree(null).roots).toEqual([]);
});

// The controls a tree draws, in order: its rows' names and their actions.
const controls = () => [...document.querySelectorAll('[aria-label="Modeling tree"] button, [aria-label="Modeling tree"] [data-disclosure-locked]')]
  .map(element => element.getAttribute('aria-label') || `locked:${(element as HTMLElement).dataset.disclosureLocked}`);
const heading = () => [...document.querySelectorAll('section[data-tool-panel][aria-label="Model tree"] input, section[data-tool-panel][aria-label="Model tree"] header button')]
  .map(element => element.getAttribute('aria-label'));

function Tree({ mode }: { mode: string }) {
  const [layout, setLayout] = useState<any>({ panels: {}, collapsed: {} });
  const [expanded, setExpanded] = useState<string[]>([]);
  const toggle = (id: string) => setExpanded(current => current.includes(id) ? current.filter(value => value !== id) : [...current, id]);
  const partControls = { isAssemblyView: true, expandedTreeNodeIds: expanded, onToggleTreeNode: toggle, onFocusTreeNode: () => {}, hiddenPartIds: [] };
  return <FileSidebar layout={layout} onLayoutChange={(patch: any) => setLayout((current: any) => ({ ...current, ...patch }))}>
    <XbfModelTree tree={presentXbfTree(structure)} active mode={mode} partControls={partControls} />
  </FileSidebar>;
}

it("the Model tree's controls are a STEP's under every shape Select's filter gives it", () => {
  const view = render(<Tree mode="all" />);
  fireEvent.click(screen.getByRole('button', { name: 'Model tree' }));
  const states = [heading(), controls()];
  fireEvent.click(screen.getByRole('button', { name: 'Expand hinge' }));
  fireEvent.click(screen.getByRole('button', { name: 'Expand arm (2)' }));
  states.push(controls());
  for (const mode of ['parts', 'faces']) { view.rerender(<Tree mode={mode} />); states.push(controls()); }
  // The heading's filter; the tree shut; the tree open; and under Select's Parts and Faces, its
  // open rows' disclosure locked open.
  const hinge = ['Select hinge', 'Isolate hinge', 'Hide hinge'], pin = ['Select pin', 'Isolate pin', 'Hide pin'];
  const open = (disclosure: (row: string) => string) => [disclosure('hinge'), ...hinge, 'Select base', 'Isolate base', 'Hide base',
    disclosure('arm (2)'), 'Select arm (2)', 'Select arm_1', 'Isolate arm_1', 'Hide arm_1', 'Select arm_2', 'Isolate arm_2', 'Hide arm_2', ...pin];
  expect(states).toEqual([['Filter model'], ['Expand hinge', ...hinge, ...pin], open(row => `Collapse ${row}`), open(() => 'locked:open'), open(() => 'locked:open')]);
});

it("Select's menu is a STEP's single choice: All when a file opens, or one kind alone", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  expect([...XBF_SELECT_DEFAULT]).toEqual(['parts', 'faces', 'edges', 'position', 'annotation', 'measurement']);
  // The modes themselves, for every kind of file: Parts in an assembly, Position where it has joints.
  const ids = (assembly: boolean, posable: boolean) => xbfSelectModes({ assembly, posable }).map(({ id }: { id: string }) => id);
  expect([ids(false, false), ids(true, false), ids(false, true), ids(true, true)]).toEqual([['all', 'faces', 'edges'],
    ['all', 'parts', 'faces', 'edges'], ['all', 'faces', 'edges', 'position'], ['all', 'parts', 'faces', 'edges', 'position']]);
  // The menu as a person reads it: its trigger, its heading, each mode with its glyph and whether it
  // is chosen, then the grouping options -- under All, and under each mode chosen in turn.
  // A mode's own glyph: a mode glyph's name, else the icon's classes (not the chosen row's check).
  const glyphOf = (item: Element) => item.querySelector('svg[data-mode-glyph]')?.getAttribute('data-mode-glyph')
    ?? [...item.querySelectorAll('svg')].map(icon => icon.getAttribute('class') || '').find(name => !name.includes('lucide-check'));
  const read = () => {
    const menu = document.querySelector<HTMLElement>('[role=menu]')!;
    return {
      trigger: [...document.querySelectorAll('[data-select-filter-trigger]')].map(node => `${node.getAttribute('aria-label')}:${node.getAttribute('data-select-filter-trigger')}`),
      label: menu.querySelector('[data-slot=dropdown-menu-label]')?.textContent,
      modes: within(menu).getAllByRole('menuitemradio').map(item => `${item.getAttribute('data-select-filter')}:${item.textContent}:${item.getAttribute('aria-checked')}:${glyphOf(item)}`),
      groups: within(menu).queryAllByRole('menuitemcheckbox').map(item => `${item.textContent}:${item.getAttribute('aria-checked')}`),
    };
  };
  const seen: { xbf: ReturnType<typeof read>[] } = { xbf: [] };
  const changes: { xbf: (readonly string[])[] } = { xbf: [] };
  function Harness() {
    const [value, setValue] = useState<readonly string[]>(XBF_SELECT_DEFAULT);
    return <XbfSelectModeMenu value={value} onChange={(next: readonly string[]) => { changes.xbf.push(next); setValue(next); }} assembly posable
      connected={{ edgeChain: true, tangentFaces: false }} onConnectedChange={() => {}} />;
  }
  render(<Harness />);
  for (const mode of ['parts', 'faces', 'edges', 'position', 'all']) {
    await user.click(document.querySelector<HTMLElement>('[data-select-filter-trigger]')!);
    seen.xbf.push(read());
    await user.click(document.querySelector<HTMLElement>(`[data-select-filter="${mode}"]`)!);
  }
  cleanup();
  // All, opening: Parts, Faces, Edges and Position each alone, and both groupings, which All's faces and edges use.
  expect(seen.xbf[0]).toEqual({ trigger: ['Selection filter: everything:all'], label: 'Pick',
    modes: ['all:All:true:select', 'parts:Parts:false:parts', 'faces:Faces:false:faces', 'edges:Edges:false:edges', 'position:Position:false:lucide lucide-spline rotate-90 size-3.5'],
    groups: ['Group edges:true', 'Group faces:false'] });
  expect(seen.xbf.map(menu => menu.trigger[0])).toEqual(['Selection filter: everything:all', 'Selection filter: Parts:parts',
    'Selection filter: Faces:faces', 'Selection filter: Edges:edges', 'Selection filter: Position:position']);
  expect(changes.xbf).toEqual([['parts'], ['faces'], ['edges'], ['position'], [...XBF_SELECT_DEFAULT]]);
  // The strip's buttons are a STEP's: the pointer and the ruler, badged with the mode chosen alone, none for All.
  const icons = (Select: any, Measure: any) => {
    const { container } = render(<>{['all', 'parts', 'faces', 'edges', 'position'].map(mode => <Select key={mode} mode={mode} />)}
      {['all', 'vertex', 'edge', 'face'].map(mode => <Measure key={mode} mode={mode} />)}</>);
    const found = [...container.querySelectorAll('svg[data-tool-icon-base]')].map(icon =>
      `${icon.getAttribute('data-tool-icon-base')}:${icon.querySelector('[data-tool-icon-badge]')?.getAttribute('data-tool-icon-badge') ?? ''}`);
    cleanup();
    return found;
  };
  expect(icons(XbfSelectIcon, XbfMeasureIcon)).toEqual(['select:', 'select:parts', 'select:faces', 'select:edges', 'select:position',
    'measure:', 'measure:points', 'measure:edges', 'measure:faces']);
  // The geometry ticked is picked as one mode, which shapes the tree.
  expect(['all', 'parts', 'topology', 'none'].map(mode => treeShape(mode))).toEqual(['all', 'parts', 'faces', 'all']);
  expect(selectGeometryMode(['faces', 'edges'])).toBe('topology');
});

// An engine document's Position over a hinge's mechanism: one revolute pair with one named configuration.
const I = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const hingeKinematics = {
  schema: 'cadgen.kinematics/2', name: 'rig', ground: 0, loop: null,
  links: [{ name: 'base', instances: [0], matrix: I }, { name: 'arm', instances: [1], matrix: I }],
  pairs: [{ label: 'hinge', type: 'revolute', links: [0, 1], frames: [I, I], limits: [[-180, 180]], units: ['deg'] }],
  asBuilt: { hinge: 0 }, configurations: { open: { hinge: 90 } },
};

// The section over the renderer's own pose state (`useXbfPose`).
function XbfPosition({ kinematics = hingeKinematics, onPose = () => {} }: { kinematics?: any, onPose?: (values: any) => void }) {
  const [layout, setLayout] = useState<any>({ panels: {}, collapsed: {} });
  const pose = useXbfPose(kinematics);
  onPose(pose.values);
  return <FileSidebar layout={layout} onLayoutChange={(patch: any) => setLayout((current: any) => ({ ...current, ...patch }))}>
    <XbfPositionSection kinematics={kinematics} values={pose.values} couplings={pose.couplings} preset={pose.preset}
      changed={pose.applied} onValues={pose.setValues} onPreset={pose.choosePreset} onReset={pose.reset} />
  </FileSidebar>;
}

// What the Position section shows, in order: its heading's controls, then its body's.
function positionControls() {
  const panel = screen.getByRole('region', { name: 'Position controls' });
  const head = panel.querySelector<HTMLElement>('[data-sidebar-head]')!;
  return {
    head: [within(head).getByRole('heading').textContent, ...[...head.querySelectorAll('button')].map(button => `${button.getAttribute('aria-label')}:${(button as HTMLButtonElement).disabled}`)],
    body: [...panel.querySelectorAll('[data-tool-panel-body] button, [data-tool-panel-body] input, [data-tool-panel-body] [role=slider]')]
      .map(element => `${element.getAttribute('role') || element.tagName.toLowerCase()}:${element.getAttribute('aria-label')}:${(element as HTMLInputElement).value ?? ''}`)
  };
}

it("Position is a STEP's -- its heading, its Pose row, a named slider and value per joint -- through a configuration and back", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  render(<XbfPosition />);
  fireEvent.click(screen.getByRole('button', { name: 'Position' }));
  const states: unknown[] = [positionControls()];
  const panel = screen.getByRole('region', { name: 'Position controls' });
  await user.click(within(panel).getByRole('button', { name: /^Pose: / }));
  const menu = document.querySelector<HTMLElement>('[role=menu][aria-label="Pose"]')!;
  states.push(within(menu).getAllByRole('menuitemradio').map(item => `${item.textContent}:${item.getAttribute('aria-checked')}`));
  await user.click(within(menu).getByRole('menuitemradio', { name: 'open' }));
  states.push(positionControls());
  const value = within(panel).getByLabelText('hinge slider value') as HTMLInputElement;
  await user.clear(value);
  await user.type(value, '25{Enter}');
  states.push(positionControls());
  await user.click(within(panel.querySelector<HTMLElement>('[data-sidebar-head]')!).getByRole('button', { name: 'Reset position' }));
  states.push(positionControls());
  // The heading (Reset is off at the opening pose), the Pose row, then the joint's slider and value.
  const shown = (pose: string, value: string, atOpening: boolean) => ({ head: ['Position', `Reset position:${atOpening}`, 'Close position:false'],
    body: [`button:Pose: ${pose}:`, 'slider:hinge:', `input:hinge slider value:${value}`] });
  expect(states).toEqual([shown('Default', '0.00°', true), ['Default:true', 'open:false'], shown('open', '90.0°', false),
    shown('Custom', '25.0°', false), shown('Default', '0.00°', true)]);
});

it("Position's pose is what the file's view keeps of it, and a new mount of the same mechanism takes it back", () => {
  let latest: any = null;
  function Probe({ restore = null }: { restore?: any }) {
    const pose = useXbfPose(hingeKinematics);
    latest = pose;
    React.useLayoutEffect(() => { if (restore) pose.restore(restore); }, []);
    return null;
  }
  const first = render(<Probe />);
  expect(latest.saved).toEqual({ preset: '__default__', given: null, couplings: null });
  act(() => latest.choosePreset('open'));
  expect(latest.saved).toEqual({ preset: 'open', given: null, couplings: null });
  act(() => latest.setValues({ hinge: [25] }));
  const saved = latest.saved;
  expect([saved.preset, saved.given]).toEqual(['__none__', { hinge: [25] }]);
  first.unmount();
  // A reload: the pose set by hand comes back, Custom, as it was left.
  render(<Probe restore={saved} />);
  expect([latest.values, latest.preset, latest.applied]).toEqual([{ hinge: [25] }, '__none__', true]);
  cleanup();
  // A named configuration comes back as the configuration.
  render(<Probe restore={{ preset: 'open', given: null, couplings: null }} />);
  expect([latest.values, latest.preset]).toEqual([{ hinge: [90] }, 'open']);
});

it('Position drives a cylindrical pair by both its values, and says what it cannot pose', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const onPose = vi.fn();
  const rig = {
    ...hingeKinematics,
    links: [...hingeKinematics.links, { name: 'sleeve', instances: [2], matrix: I }, { name: 'wheel', instances: [3], matrix: I }, { name: 'leg', instances: [4], matrix: I }],
    pairs: [
      ...hingeKinematics.pairs,
      { label: 'slide', type: 'cylindrical', links: [0, 2], frames: [I, I], limits: [[-180, 180], [0, 50]], units: ['deg', 'mm'] },
      { label: 'spin', type: 'revolute', links: [0, 3], frames: [I, I], limits: [[null, null]], units: ['deg'] },
      { label: 'knee', type: 'revolute', links: [0, 4], frames: [I, I], limits: [[0, 90]], units: ['deg'] },
      { label: 'shin', type: 'revolute', links: [0, 4], frames: [I, I], limits: [[0, 90]], units: ['deg'] },
    ],
    asBuilt: { hinge: 0, slide: [0, 10], spin: 0, knee: 0, shin: 0 }, configurations: {}, loop: ['knee', 'shin'],
  };
  render(<XbfPosition kinematics={rig} onPose={onPose} />);
  fireEvent.click(screen.getByRole('button', { name: 'Position' }));
  const panel = screen.getByRole('region', { name: 'Position controls' });
  expect(within(panel).getAllByRole('slider').map(thumb => [thumb.getAttribute('aria-label'), thumb.getAttribute('aria-valuemin'), thumb.getAttribute('aria-valuemax')]))
    .toEqual([['hinge', '-180', '180'], ['slide angle', '-180', '180'], ['slide position', '0', '50'], ['spin', '-180', '180']]);
  const position = within(panel).getByLabelText('slide position slider value') as HTMLInputElement;
  await user.clear(position);
  await user.type(position, '30{Enter}');
  expect(onPose.mock.lastCall![0]).toMatchObject({ hinge: [0], slide: [0, 30] });
  // A loop's pairs, which have no pose without a solver, are said, not drawn.
  expect(within(panel).getByText(/knee cannot be posed: pairs knee, shin close a loop/)).toBeTruthy();
});

// The spec's index finger: three knuckles from straight, one coupling curling them all, and a
// configuration naming it.
const KNUCKLES: [string, number][] = [['index_mcp_flexion', 90], ['index_pip', 100], ['index_dip', 70]];
const JOINTS = KNUCKLES.map(([label]) => label);
const fingerKinematics = {
  ...hingeKinematics,
  links: ['base', 'proximal', 'middle', 'distal'].map((name, at) => ({ name, instances: [at], matrix: I })),
  pairs: KNUCKLES.map(([label, top], at) => ({
    label, type: 'revolute', links: [at, at + 1], frames: [I, I], limits: [[0, top]], units: ['deg'] })),
  asBuilt: Object.fromEntries(JOINTS.map(label => [label, 0])), configurations: { fist: Object.fromEntries(KNUCKLES) },
  couplings: { index_curl: { range: [0, 1], terms: KNUCKLES.map(([label, ratio]) => [label, 0, ratio]) } },
};
// The joints' values in the knuckles' order.
const pose = (...values: number[]) => Object.fromEntries(JOINTS.map((label, at) => [label, [values[at]]]));
const sliders = (panel: HTMLElement) => within(panel).getAllByRole('slider').map(thumb =>
  [thumb.getAttribute('aria-label'), thumb.getAttribute('aria-valuemin'), thumb.getAttribute('aria-valuemax')]);
const valueOf = (panel: HTMLElement, label: string) => (within(panel).getByLabelText(`${label} slider value`) as HTMLInputElement).value;

async function setValue(user: ReturnType<typeof userEvent.setup>, panel: HTMLElement, label: string, text: string) {
  const field = within(panel).getByLabelText(`${label} slider value`) as HTMLInputElement;
  await user.clear(field);
  await user.type(field, `${text}{Enter}`);
}

async function choose(user: ReturnType<typeof userEvent.setup>, panel: HTMLElement, name: string) {
  await user.click(within(panel).getByRole('button', { name: /^Pose: / }));
  await user.click(within(document.querySelector<HTMLElement>('[role=menu][aria-label="Pose"]')!).getByRole('menuitemradio', { name }));
}

it("Position shows a slider per coupling under the Pose row and none for its joints: they move only through it", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const onPose = vi.fn();
  render(<XbfPosition kinematics={fingerKinematics} onPose={onPose} />);
  fireEvent.click(screen.getByRole('button', { name: 'Position' }));
  const panel = screen.getByRole('region', { name: 'Position controls' });
  // Under the Pose row: the coupling, 0 as built over its range; no joint of it has a slider.
  expect(sliders(panel)).toEqual([['index_curl', '0', '1']]);
  expect(within(panel).queryByLabelText('index_pip slider value')).toBeNull();
  expect(valueOf(panel, 'index_curl')).toBe('0.00');
  await setValue(user, panel, 'index_curl', '0.6');
  expect(onPose.mock.lastCall![0]).toEqual(pose(54, 60, 42));
  // A configuration puts it where that configuration stands on it; the coupling again moves the
  // joints from there; Reset puts it back at 0.
  await choose(user, panel, 'fist');
  expect(valueOf(panel, 'index_curl')).toBe('1.00');
  expect(onPose.mock.lastCall![0]).toEqual(pose(90, 100, 70));
  await setValue(user, panel, 'index_curl', '0.2');
  expect(onPose.mock.lastCall![0]).toEqual(pose(18, 20, 14));
  await user.click(within(panel.querySelector<HTMLElement>('[data-sidebar-head]')!).getByRole('button', { name: 'Reset position' }));
  expect(valueOf(panel, 'index_curl')).toBe('0.00');
  expect(onPose.mock.lastCall![0]).toEqual(pose(0, 0, 0));
});

it("a face's and an edge's card rows are a STEP's for the same measurements", () => {
  const cases = [
    ['face', { surface: 'cylinder', radius: 2, area: 50 }, [['Diameter Ø', 4, 'mm'], ['Radius R', 2, 'mm'], ['Area', 50, 'mm²']]],
    ['face', { surface: 'plane', area: 12 }, [['Area', 12, 'mm²']]],
    ['edge', { curve: 'circle', radius: 3, sweepRadians: Math.PI, length: 3 * Math.PI },
      [['Diameter Ø', 6, 'mm'], ['Radius R', 3, 'mm'], ['Arc length', 3 * Math.PI, 'mm'], ['Sweep angle', 180, '°']]],
    ['edge', { curve: 'line', length: 7 }, [['Length', 7, 'mm']]],
  ] as const;
  for (const [kind, facts, rows] of cases) expect(xbfMeasurementRows(kind, facts)).toEqual(rows);
});

function Chips({ ids }: { ids: string[] }) {
  const tree = presentXbfTree(structure);
  const scene = {
    structure,
    describePart: (id: string) => ({ name: id }),
    describeElement: (id: string) => {
      const [, instance, kind, ordinal] = /^i(\d+)\/(face|edge)\/(\d+)$/.exec(id) || [];
      return instance ? { id, kind, ordinal: Number(ordinal), instance: Number(instance), key: 'k', name: kind === 'face' && ordinal === '4' ? 'f:arm.top' : '', path: structure.instances[Number(instance)].path } : null;
    },
    measureParts: () => ({ size: [10, 20, 30], volume: 600 }),
  };
  const { chips } = useXbfSelectionChips({ scene, tree, resource: { kind: 'workspace-file', path: '/models/fixture.xbf' }, selectedIds: ids,
    facts: new Map([['i1/face/4', { surface: 'plane', area: 12 }]]), onRemove: () => {}, onHover: () => {} });
  return <ul>{chips.map((chip: any) => <li key={chip.key}>{`${chip.label}|${chip.glyph}|${JSON.stringify(chip.compact || null)}`}</li>)}</ul>;
}

it("Quick Edit's chips name a selection as a STEP's do: a part or subassembly its own chip, faces and edges a chip per kind per part", () => {
  render(<Chips ids={['n0.0', 'i1/face/4', 'i1/face/5', 'i3/edge/2']} />);
  expect(screen.getAllByRole('listitem').map(item => item.textContent)).toEqual([
    'hinge|solid|null',
    'arm_1 · 2 faces|face|{"name":"arm_1","kind":"face","count":2}',
    'pin · edge 2|edge|{"name":"pin","kind":"edge","number":"2"}',
  ]);
});

// A STEP of one part whose label holds spaces, as the engine serves it: a face it names, the rest by number.
const BRACKET = 'L bracket 80 x 60 x 6 mm';
const bracket = {
  name: BRACKET, version: '1-1', units: 'mm',
  prototypes: [{ index: 0, key: 'k-bracket', name: BRACKET, color: null, faceNames: { 7: 'f:bracket_body.body_bcndnk~ba6e1714f88b' }, edgeNames: {}, faceColors: {} }],
  instances: [{ prototype: 0, path: `${BRACKET}/${BRACKET}`, matrix: [], color: null }],
  tree: { name: BRACKET, children: [{ name: BRACKET, prototype: 0, instance: 0 }] },
};

function StepQuickEdit({ ids }: { ids: string[] }) {
  const tree = presentXbfTree(bracket);
  const scene = {
    structure: bracket,
    describePart: (id: string) => ({ name: id }),
    describeElement: (id: string) => {
      const [, kind, ordinal] = /^i0\/(face|edge)\/(\d+)$/.exec(id) || [];
      return kind ? { id, kind, ordinal: Number(ordinal), instance: 0, key: 'k-bracket', path: `${BRACKET}/${BRACKET}`,
        name: (bracket.prototypes[0] as any)[`${kind}Names`][ordinal] || '' } : null;
    },
    measureParts: () => null,
  };
  const resource = { kind: 'workspace-file', path: '/models/STEP/bracket.step' };
  const { references, chips } = useXbfSelectionChips({ scene, tree, resource, selectedIds: ids, facts: new Map(), onRemove: () => {}, onHover: () => {} });
  return <ViewerHostContext.Provider value={testHost()}><div data-slot="cad-file-view">
    <QuickEdit resource={resource} references={references} chips={chips} />
  </div></ViewerHostContext.Provider>;
}

it("a face picked on a STEP's page opens Quick Edit with its reference, named or not, as on an .xbf's", () => {
  const box = () => screen.queryByRole('region', { name: 'Quick Edit' });
  const { rerender } = render(<StepQuickEdit ids={[]} />);
  expect(box()).toBeNull();
  // A named face, a face by its number, the part: each is a reference, which opens the box with its chip,
  // named by the part (the one part: a face's chip shows its kind and number, its name the part's).
  for (const [id, shown] of [['i0/face/7', 'face 7'], ['i0/face/3', 'face 3'], ['i0', BRACKET.slice(0, 15).trimEnd()]]) {
    rerender(<StepQuickEdit ids={[id]} />);
    expect(box(), id).not.toBeNull();
    const chip = box()!.querySelector('[data-quick-edit-ref] button')!;
    expect([chip.getAttribute('aria-label')!.startsWith(BRACKET), chip.textContent!.startsWith(shown)], id).toEqual([true, true]);
  }
});

function Card({ id, measured }: { id: string, measured: object }) {
  const tree = presentXbfTree(structure);
  const scene = { structure, describePart: (part: string) => ({ name: part }), describeElement: () => null, measureParts: () => measured };
  const { chips } = useXbfSelectionChips({ scene, tree, resource: null, selectedIds: [id], facts: new Map(), onRemove: () => {}, onHover: () => {} });
  return <div>{chips[0].card}</div>;
}

it("a part's card weighs it by its material, and an assembly's sums its parts", () => {
  expect(xbfMassText({ volume: 1000, mass: 1000e-9 * 7870, unweighed: 0 })).toBe('0.00787 kg');
  expect(xbfMassText({ volume: 1000, mass: 12.3456, unweighed: 0 })).toBe('12.35 kg');
  expect(xbfMassText({ volume: 1000, mass: null, unweighed: 1 })).toBe('no material');
  render(<Card id="i3" measured={{ size: [10, 20, 30], volume: 600, mass: null, unweighed: 1 }} />);
  expect(screen.getByText('Mass')).toBeTruthy();
  expect(screen.getByText('no material')).toBeTruthy();
  cleanup();
  render(<Card id="n0.0" measured={{ size: [10, 20, 30], volume: 6000, mass: 1.234, unweighed: 1 }} />);
  expect(screen.getByText('1.234 kg · 1 without material')).toBeTruthy();
});

it("the menus are a STEP's: a part's offers Copy Reference, Select, Isolate, Hide others, Hide, the tree's expansion and the framing", () => {
  const tree = presentXbfTree(structure);
  const part = xbfPartMenu({ tree, nodeId: 'i3', assembly: true, hiddenIds: [], isolatedIds: [], selectedNodeIds: ['i3'], expandedIds: [],
    copyText: '/models/fixture.xbf#pin', zoomSelectionAvailable: true });
  expect(assemblyPartMenuEntries(part).map((entry: any) => `${entry.separatorBefore ? '| ' : ''}${entry.label.props.children}${entry.disabled ? ' (off)' : ''}`)).toEqual([
    'Copy Reference', '| Deselect', 'Isolate', '| Hide others', 'Hide', '| Expand', 'Collapse (off)', 'Expand all', 'Collapse all (off)', '| Zoom to fit', 'Zoom to selection']);
  const model = xbfModelMenu({ tree, assembly: true, expandedIds: [], hiddenCount: 1, zoomSelectionAvailable: false });
  expect([model.showShowAll, model.showExpandCollapse, model.copyText]).toEqual([true, true, '']);
});

it('an .xbf and a STEP have the engine document renderer, prepared from the catalog entry', async () => {
  let disposed = 0;
  const client = { resolveEntry: async (path: string) => ({ file: path, kind: 'xbf' }), createRenderSession: () => ({ dispose: () => { disposed += 1; } }) } as never;
  const xbf = createXbfRenderer({ client });
  const file = (path: string) => ({ path, name: path, kind: 'file', size: 1, extension: path.split('.').at(-1), mediaType: 'cad' });
  expect(xbf.id).toBe('xbf');
  for (const path of ['arm.xbf', 'arm.step', 'ARM.STP']) expect(selectRenderer([xbf], file(path) as never)).toBe(xbf);
  const prepared = await xbf.prepare({ file: file('arm.xbf'), source: {}, signal: new AbortController().signal } as never);
  prepared.dispose?.();
  expect(disposed).toBe(1);
});

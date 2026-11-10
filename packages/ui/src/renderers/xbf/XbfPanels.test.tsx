import React, { useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FlatPanel from '../../../dist/renderers/kit/shell/FlatPanel.js';
import XbfPositionSection, { useXbfPose } from '../../../dist/renderers/xbf/XbfPositionSection.js';
import XbfModelTree from '../../../dist/renderers/xbf/XbfModelTree.js';
import { MeasureIcon as XbfMeasureIcon, SelectIcon as XbfSelectIcon, SelectMenu as XbfSelectMenu, XBF_SELECT_DEFAULT, xbfSelectBadge, xbfSelectExtras,
  xbfSelectKinds } from '../../../dist/renderers/xbf/XbfSelectionModes.js';
import { measureBadge } from '../../../dist/renderers/kit/tools/measure/MeasureFilterMenu.js';
import { ControlUsageProvider } from '../../../dist/usage/controls.js';
import { MEASURE_FILTER_DEFAULT } from '../../../dist/renderers/kit/tools/measure/measureFilter.js';
import { presentXbfTree, xbfPickFrontier } from '../../../dist/renderers/xbf/xbfTree.js';
import { useXbfSelectionChips, xbfDescriber, xbfMassText, xbfMeasurementRows, xbfTipper } from '../../../dist/renderers/xbf/xbfChips.js';
import { nextSelectionIds, selectGeometryMode, tangentChain, treeShape, withTangentChains, xbfGeometryPicks } from '../../../dist/renderers/xbf/xbfSelectionFilter.js';
import { NO_EXPANSION, openRows, personsRows, shutOpenedBy, toggleRow } from '../../../dist/renderers/xbf/xbfExpansion.js';
import { xbfModelMenu, xbfPartMenu, xbfTangentSources, xbfTopologyMenu } from '../../../dist/renderers/xbf/xbfMenus.js';
import { assemblyPartMenuEntries, viewportMenuEntries } from '../../../dist/renderers/xbf/xbfMenuItems.js';
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
  override(Element.prototype, 'scrollIntoView', { value() {} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); while (restores.length) restores.pop()!(); });

// A section as the shell draws it: a tab of the view's panel, open.
function InPanel({ tab, children }: { tab: string, children: React.ReactNode }) {
  return <FlatPanel mode="docked" open onClose={() => {}} label="Model panel" searchLabel="Search the model"
    sections={children} tab={tab} onTabChange={() => {}} width={240} maxWidth={480} onWidthChange={() => {}} focusSearch={0} />;
}

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
// What heads the tree: the panel's search, which searches it.
const heading = () => [...document.querySelectorAll('[data-flat-panel-head] input')].map(element => element.getAttribute('aria-label'));

function Tree({ mode }: { mode: string }) {
  const [expanded, setExpanded] = useState<string[]>([]);
  const toggle = (id: string) => setExpanded(current => current.includes(id) ? current.filter(value => value !== id) : [...current, id]);
  const partControls = { isAssemblyView: true, expandedTreeNodeIds: expanded, onToggleTreeNode: toggle, onFocusTreeNode: () => {}, hiddenPartIds: [] };
  return <InPanel tab="tree"><XbfModelTree tree={presentXbfTree(structure)} active mode={mode} partControls={partControls} /></InPanel>;
}

it("the Model tree's controls are a STEP's under every shape Select's filter gives it", () => {
  const view = render(<Tree mode="all" />);
  const states = [heading(), controls()];
  fireEvent.click(screen.getByRole('button', { name: 'Expand hinge' }));
  fireEvent.click(screen.getByRole('button', { name: 'Expand arm (2)' }));
  states.push(controls());
  for (const mode of ['parts', 'faces']) { view.rerender(<Tree mode={mode} />); states.push(controls()); }
  // The panel's search; the tree shut; the tree open; and under Select's Parts and Faces, its
  // open rows' disclosure locked open.
  const hinge = ['Select hinge', 'Isolate hinge', 'Hide hinge'], pin = ['Select pin', 'Isolate pin', 'Hide pin'];
  const open = (disclosure: (row: string) => string) => [disclosure('hinge'), ...hinge, 'Select base', 'Isolate base', 'Hide base',
    disclosure('arm (2)'), 'Select arm (2)', 'Select arm_1', 'Isolate arm_1', 'Hide arm_1', 'Select arm_2', 'Isolate arm_2', 'Hide arm_2', ...pin];
  expect(states).toEqual([['Search the model'], ['Expand hinge', ...hinge, ...pin], open(row => `Collapse ${row}`), open(() => 'locked:open'), open(() => 'locked:open')]);
});

// The tree as its host drives it (`XbfRenderer.jsx`): what is open and what is selected are the host's,
// a press on a row selects as the host's `pickNode` does, and `pickInView` is a pick on the model.
const fixtureTree = presentXbfTree(structure);
let pickInView: (ids: string[]) => void = () => {};
let hostSelection: string[] = [];
function HostedTree() {
  const [expanded, setExpanded] = useState<string[]>([]);
  const [chosen, setChosen] = useState<string[]>([]);
  pickInView = ids => setChosen(ids);
  hostSelection = chosen;
  const partControls = { isAssemblyView: true, expandedTreeNodeIds: expanded, hiddenPartIds: [], onFocusTreeNode: () => {},
    onToggleTreeNode: (id: string) => setExpanded(now => now.includes(id) ? now.filter(item => item !== id) : [...now, id]),
    onSelectTreeNode: (id: string | string[], { multiSelect = false } = {}) => setChosen(now => nextSelectionIds(now, [id].flat(), multiSelect)) };
  return <InPanel tab="tree"><XbfModelTree tree={fixtureTree} active selectedIds={chosen} partControls={partControls} /></InPanel>;
}
// The rows as a person reads them: each name, "+" or "-" while its chevron says it is open or shut, "*" while it is lit.
const treeRows = () => [...document.querySelectorAll('[aria-label="Modeling tree"] li[data-virtual-row]')].map(row => {
  const chevron = row.querySelector('button[aria-expanded]'), name = row.querySelector('button[aria-pressed]');
  return `${chevron ? (chevron.getAttribute('aria-expanded') === 'true' ? '- ' : '+ ') : ''}${name!.textContent}${name!.getAttribute('aria-pressed') === 'true' ? ' *' : ''}`;
}).join(', ');

it("a Model tree row's chevron opens and shuts it, whatever opened it, and a press on a row selects it and opens nothing", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  render(<HostedTree />);
  const seen: string[] = [];
  const read = (step: string) => seen.push(`${step}: ${treeRows()} | ${hostSelection.join(' ')}`);
  const name = (row: string) => screen.getByRole('button', { name: `Select ${row}` });
  const chevron = (row: string) => name(row).closest('li')!.querySelector<HTMLElement>('button[aria-expanded]')!;
  read('open');
  // An assembly: its name selects it, shut; its chevron opens and shuts it and leaves the selection.
  await user.click(name('hinge')); read('hinge pressed');
  await user.click(chevron('hinge')); read('hinge chevron');
  // A folded row: its name selects every part under it, which it holds, lit and shut; its chevron opens and shuts it.
  await user.click(name('arm (2)')); read('arm (2) pressed');
  await user.click(chevron('arm (2)')); read('arm (2) chevron');
  await user.click(chevron('arm (2)')); read('arm (2) chevron again');
  // The keyboard: Enter and Space on a chevron open and shut its row; Enter on a name selects it and opens nothing.
  chevron('arm (2)').focus();
  await user.keyboard('{Enter}'); read('chevron Enter');
  await user.keyboard(' '); read('chevron Space');
  name('base').focus();
  await user.keyboard('{Enter}'); read('name Enter');
  // A pick on the model opens the rows over what it picked; the chevron shuts them again, and the reveal does not
  // reopen them; the next pick leaves the shape the person left.
  act(() => pickInView(['i2'])); read('arm_2 picked');
  await user.click(chevron('arm (2)')); read('arm (2) shut over the pick');
  act(() => pickInView(['i3'])); read('pin picked');
  expect(seen).toEqual([
    'open: + hinge, pin | ',
    'hinge pressed: + hinge *, pin | n0.0',
    'hinge chevron: - hinge *, base, + arm (2), pin | n0.0',
    'arm (2) pressed: - hinge, base, + arm (2) *, pin | i1 i2',
    'arm (2) chevron: - hinge, base, - arm (2) *, arm_1 *, arm_2 *, pin | i1 i2',
    'arm (2) chevron again: - hinge, base, + arm (2) *, pin | i1 i2',
    'chevron Enter: - hinge, base, - arm (2) *, arm_1 *, arm_2 *, pin | i1 i2',
    'chevron Space: - hinge, base, + arm (2) *, pin | i1 i2',
    'name Enter: - hinge, base *, + arm (2), pin | i0',
    'arm_2 picked: - hinge, base, - arm (2), arm_1, arm_2 *, pin | i2',
    'arm (2) shut over the pick: - hinge, base, + arm (2), pin | i2',
    'pin picked: - hinge, base, + arm (2), pin * | i3',
  ]);
});

// The tree with the host's whole say over what is open (`XbfRenderer.jsx` over `xbfExpansion.js`): a person's
// chevron or key, a pick's reveal and an isolation each open rows as theirs, leaving isolation shuts what it
// opened, and the file's view keeps the person's rows alone.
let hostIsolation: { exit(): void, persisted(): string[] } = { exit() {}, persisted: () => [] };
function ExpandingHost() {
  const [expansion, setExpansion] = useState(NO_EXPANSION);
  const [chosen, setChosen] = useState<string[]>([]);
  const [isolated, setIsolated] = useState<string[]>([]);
  pickInView = ids => setChosen(ids);
  hostSelection = chosen;
  hostIsolation = { exit: () => { setExpansion((now: any) => shutOpenedBy(now, 'isolation')); setIsolated([]); }, persisted: () => personsRows(expansion) };
  const partControls = { isAssemblyView: true, expandedTreeNodeIds: expansion.open, hiddenPartIds: [], focusedNodeIds: isolated,
    onFocusTreeNode: (ids: string | string[]) => { const targets = [ids].flat(); setChosen([]); setIsolated(targets); setExpansion((now: any) => openRows(now, targets, 'isolation')); },
    onToggleTreeNode: (id: string) => setExpansion((now: any) => toggleRow(now, id)),
    onRevealTreeNodes: (ids: string[], reason: string) => setExpansion((now: any) => openRows(now, ids, reason)),
    onSelectTreeNode: (id: string | string[], { multiSelect = false } = {}) => setChosen(now => nextSelectionIds(now, [id].flat(), multiSelect)) };
  return <InPanel tab="tree"><XbfModelTree tree={fixtureTree} active selectedIds={chosen} partControls={partControls} /></InPanel>;
}
const nameOf = (row: string) => screen.getByRole('button', { name: `Select ${row}` });
// A row's id in the host's open rows: an assembly's selection id, a folded row's own.
const openIdOf = (label: string): string | undefined => {
  const find = (nodes: any[]): string | undefined => { for (const node of nodes) { if (node.label === label) return node.selectionId || node.id; const hit = find(node.children || []); if (hit) return hit; } };
  return find(fixtureTree.roots);
};
const chevronOf = (row: string) => nameOf(row).closest('li')!.querySelector<HTMLElement>('button[aria-expanded]')!;

it("a row isolating opened shuts again as the isolation ends, a double-clicked folded row too; a row open before stays open", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  render(<ExpandingHost />);
  const seen: string[] = [];
  const read = (step: string) => seen.push(`${step}: ${treeRows()}`);
  await user.click(chevronOf('hinge'));
  read('hinge opened');
  // A double-click on a folded row isolates its parts, and the tree opens the row to bring them into view.
  await user.dblClick(nameOf('arm (2)')); read('arm (2) isolated');
  act(() => hostIsolation.exit()); read('isolation left');
  // Opened by hand before, it stays open after.
  await user.click(chevronOf('arm (2)'));
  await user.dblClick(nameOf('arm (2)'));
  act(() => hostIsolation.exit()); read('opened first, isolated, left');
  // An assembly shut before it is isolated is shut again after, and the person's rows under it are theirs.
  await user.click(chevronOf('hinge'));
  await user.dblClick(nameOf('hinge'));
  read('hinge isolated');
  act(() => hostIsolation.exit()); read('hinge left');
  expect(seen).toEqual([
    'hinge opened: - hinge, base, + arm (2), pin',
    'arm (2) isolated: - hinge, base, - arm (2), arm_1, arm_2, pin',
    'isolation left: - hinge, base, + arm (2), pin',
    'opened first, isolated, left: - hinge, base, - arm (2), arm_1, arm_2, pin',
    'hinge isolated: - hinge, base, - arm (2), arm_1, arm_2, pin',
    'hinge left: + hinge, pin',
  ]);
});

it("the file's view keeps the rows the person opened, never the rows a pick's reveal opened, which are theirs once they press them", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  render(<ExpandingHost />);
  await user.click(chevronOf('hinge'));
  // A pick of arm_2 on the model opens arm (2) to show it: kept for the page, not with the file.
  act(() => pickInView(['i2']));
  expect([treeRows(), hostIsolation.persisted()]).toEqual(['- hinge, base, - arm (2), arm_1, arm_2 *, pin', [openIdOf('hinge')]]);
  // Its chevron shut and opened again: the person's now, and kept.
  await user.click(chevronOf('arm (2)'));
  await user.click(chevronOf('arm (2)'));
  expect(hostIsolation.persisted()).toEqual([openIdOf('hinge'), openIdOf('arm (2)')]);
});

it("a second plain press on the one selected folded row lets its parts go; Shift adds and takes each away as before", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  render(<ExpandingHost />);
  await user.click(chevronOf('hinge'));
  await user.click(nameOf('arm (2)'));
  const first = [treeRows(), hostSelection.join(' ')];
  await user.click(nameOf('arm (2)'));
  const again = [treeRows(), hostSelection.join(' ')];
  // Shift: the parts added, then taken away, each as before; with base selected first it stays.
  await user.click(nameOf('base'));
  await user.keyboard('{Shift>}');
  await user.click(nameOf('arm (2)'));
  const added = hostSelection.join(' ');
  await user.click(nameOf('arm (2)'));
  await user.keyboard('{/Shift}');
  expect([first, again, added, hostSelection.join(' ')]).toEqual([
    ['- hinge, base, + arm (2) *, pin', 'i1 i2'], ['- hinge, base, + arm (2), pin', ''], 'i0 i1 i2', 'i0']);
});

it("the rows walk by the keyboard, as the tree pattern has it: Up, Down, Home, End, Right open and into, Left up and shut", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  render(<ExpandingHost />);
  const seen: string[] = [];
  const at = () => document.activeElement?.getAttribute('aria-label') ?? '';
  const step = async (key: string) => { await user.keyboard(key); seen.push(`${key} ${at()} | ${treeRows()}`); };
  nameOf('hinge').focus();
  for (const key of ['{ArrowRight}', '{ArrowRight}', '{ArrowDown}', '{ArrowRight}', '{ArrowRight}', '{ArrowDown}', '{ArrowLeft}', '{ArrowLeft}',
    '{ArrowLeft}', '{End}', '{ArrowUp}', '{Home}', '{ArrowUp}', '{Enter}']) await step(key);
  const shut = '- hinge, base, + arm (2), pin', open = '- hinge, base, - arm (2), arm_1, arm_2, pin';
  expect(seen).toEqual([
    `{ArrowRight} Select hinge | ${shut}`,
    `{ArrowRight} Select base | ${shut}`,
    `{ArrowDown} Select arm (2) | ${shut}`,
    `{ArrowRight} Select arm (2) | ${open}`,
    `{ArrowRight} Select arm_1 | ${open}`,
    `{ArrowDown} Select arm_2 | ${open}`,
    `{ArrowLeft} Select arm (2) | ${open}`,
    `{ArrowLeft} Select arm (2) | ${shut}`,
    `{ArrowLeft} Select hinge | ${shut}`,
    `{End} Select pin | ${shut}`,
    `{ArrowUp} Select arm (2) | ${shut}`,
    `{Home} Select hinge | ${shut}`,
    `{ArrowUp} Select hinge | ${shut}`,
    '{Enter} Select hinge | - hinge *, base, + arm (2), pin',
  ]);
  // A row's arrows are the tree's at its ends and on a part too, never let through to the view's orbit;
  // any other key is (`fireEvent` answers false for a key whose default was prevented).
  expect([fireEvent.keyDown(nameOf('hinge'), { key: 'ArrowUp' }), fireEvent.keyDown(nameOf('pin'), { key: 'ArrowDown' }),
    fireEvent.keyDown(nameOf('pin'), { key: 'ArrowRight' }), fireEvent.keyDown(nameOf('pin'), { key: 'x' })]).toEqual([false, false, false, true]);
});

// Select's Filter as a person reads and ticks it (jsdom has no geometry for a submenu's pointer grace area:
// the keyboard ticks, the same handler). Opens the chevron's menu and its Filter row, once.
const filterMenu = (user: ReturnType<typeof userEvent.setup>, name = 'select') => {
  const read = () => {
    const sub = document.querySelector<HTMLElement>('[data-slot=dropdown-menu-sub-content][aria-label="Filter"]')!;
    return {
      trigger: [...document.querySelectorAll(`[data-${name}-filter-trigger]`)].map(node => `${node.getAttribute('aria-label')}:${node.getAttribute(`data-${name}-filter-trigger`)}`)[0],
      row: document.querySelector(`[data-${name}-filter-row]`)?.getAttribute('aria-label'),
      order: [...sub.querySelectorAll(`[data-${name}-filter], [role=separator]`)].map(item => item.getAttribute(`data-${name}-filter`) ?? 'rule'),
      boxes: within(sub).getAllByRole('menuitemcheckbox').map(item => `${item.textContent}:${item.getAttribute('aria-checked')}`),
      // The glyph rule: a box is its name alone, in every file.
      glyphs: sub.querySelectorAll(`[data-${name}-filter] svg:not(.lucide-check):not(.lucide-minus)`).length,
    };
  };
  return {
    read,
    async open() {
      await user.click(document.querySelector<HTMLElement>(`[data-${name}-filter-trigger]`)!);
      await user.click(await waitFor(() => document.querySelector<HTMLElement>(`[data-${name}-filter-row]`)!));
      await waitFor(() => expect(document.querySelector('[data-slot=dropdown-menu-sub-content][aria-label="Filter"]')).not.toBeNull());
    },
    async tick(id: string) {
      document.querySelector<HTMLElement>(`[data-${name}-filter="${id}"]`)!.focus();
      await user.keyboard('{Enter}');
      // Ticking leaves the submenu up.
      expect(document.querySelector('[data-slot=dropdown-menu-sub-content][aria-label="Filter"]')).not.toBeNull();
    },
  };
};

it("Select's menu is one row, Filter: All, a rule, the kinds a click takes, then Position, each ticked on its own", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  expect([...XBF_SELECT_DEFAULT]).toEqual(['parts', 'faces', 'edges', 'position', 'annotation', 'measurement']);
  // The boxes themselves, for every kind of file: Parts in an assembly, Position (no kind) where it has joints.
  const ids = (assembly: boolean, posable: boolean) => [xbfSelectKinds({ assembly }), xbfSelectExtras({ posable })].map(items => items.map(({ id }: { id: string }) => id));
  expect([ids(false, false), ids(true, true)]).toEqual([[['faces', 'edges', 'annotation', 'measurement'], []],
    [['parts', 'faces', 'edges', 'annotation', 'measurement'], ['position']]]);
  const changes: (readonly string[])[] = [];
  function Harness() {
    const [value, setValue] = useState<readonly string[]>(XBF_SELECT_DEFAULT);
    return <XbfSelectMenu value={value} onChange={(next: readonly string[]) => { changes.push(next); setValue(next); }} assembly posable />;
  }
  const reported: { control: string, count: number }[] = [];
  render(<ControlUsageProvider report={(counts: { control: string, count: number }[]) => reported.push(...counts)}><Harness /></ControlUsageProvider>);
  const menu = filterMenu(user);
  await menu.open();
  // One row, every box ticked as a file opens; no Selection tool section without a tool to choose.
  expect([document.querySelectorAll('[data-select-filter-row]').length, document.querySelectorAll('[data-slot=dropdown-menu-label]').length]).toEqual([1, 0]);
  expect(menu.read()).toEqual({ trigger: 'Filter: everything:all', row: 'Filter: All',
    order: ['all', 'rule', 'parts', 'faces', 'edges', 'annotation', 'measurement', 'rule', 'position'],
    boxes: ['All:true', 'Parts:true', 'Faces:true', 'Edges:true', 'Annotations:true', 'Measurements:true', 'Position:true'], glyphs: 0 });
  // All unticks every kind and leaves Position: the knobs alone, as the earlier Position mode.
  await menu.tick('all');
  expect(menu.read()).toMatchObject({ trigger: 'Filter: Position:position', row: 'Filter: None' });
  await menu.tick('faces');
  expect(menu.read()).toMatchObject({ trigger: 'Filter: Faces, Position:faces position', row: 'Filter: Faces',
    boxes: ['All:mixed', 'Parts:false', 'Faces:true', 'Edges:false', 'Annotations:false', 'Measurements:false', 'Position:true'] });
  await menu.tick('position');
  await menu.tick('edges');
  expect(menu.read()).toMatchObject({ trigger: 'Filter: Faces, Edges:faces edges', row: 'Filter: 2 of 5' });
  // All with a dash ticks every kind, Position as it was; ticked, the filter is the opening one, exactly.
  await menu.tick('all');
  await menu.tick('position');
  expect(menu.read()).toMatchObject({ trigger: 'Filter: everything:all', row: 'Filter: All' });
  expect(changes).toEqual([['position'], ['faces', 'position'], ['faces'], ['faces', 'edges'],
    ['parts', 'faces', 'edges', 'annotation', 'measurement'], [...XBF_SELECT_DEFAULT]]);
  // Unticking every box: nothing at all.
  for (const id of ['all', 'position']) await menu.tick(id);
  expect(menu.read()).toMatchObject({ trigger: 'Filter: nothing:none', row: 'Filter: None' });
  await user.keyboard('{Escape}');
  cleanup();
  // Each press on a box is counted by its name, the earlier menu's where it had one.
  expect(Object.fromEntries(reported.map(({ control, count }) => [control, count]))).toEqual({ select_filter_all: 3,
    select_filter_faces: 1, select_filter_edges: 1, select_filter_position: 3 });
});

it("each of the earlier single choices is its kind ticked alone, picking as it did; every mix picks through the same booleans", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  // The earlier modes' filters (Automatic, Parts, Faces, Edges, Position), each reached by ticks from the opening filter.
  const EARLIER = { all: [...XBF_SELECT_DEFAULT], parts: ['parts'], faces: ['faces'], edges: ['edges'], position: ['position'] };
  for (const [mode, kinds] of Object.entries(EARLIER)) {
    let value: readonly string[] = XBF_SELECT_DEFAULT;
    function Harness() {
      const [state, setState] = useState<readonly string[]>(XBF_SELECT_DEFAULT);
      value = state;
      return <XbfSelectMenu value={state} onChange={setState} assembly posable />;
    }
    render(<Harness />);
    const menu = filterMenu(user);
    await menu.open();
    if (mode !== 'all') {
      await menu.tick('all');
      if (mode !== 'position') { await menu.tick(mode); await menu.tick('position'); }
    }
    expect([mode, value]).toEqual([mode, kinds]);
    cleanup();
  }
  // What each picks, the earlier renderer's own reading of its filter, and its badge on Select's button.
  const read = (filter: readonly string[], assembly = true) => ({ ...xbfGeometryPicks(filter, { assembly }),
    badge: xbfSelectBadge(filter, { assembly, posable: true }) });
  const geometry = (mode: string, shape: string, faces: boolean, edges: boolean, parts: boolean, badge: string) =>
    ({ mode, shape, options: { faces, edges, parts }, badge });
  expect(read(EARLIER.all)).toEqual(geometry('all', 'all', true, true, true, 'all'));
  expect(read(EARLIER.parts)).toEqual(geometry('parts', 'parts', false, false, true, 'parts'));
  expect(read(EARLIER.faces)).toEqual(geometry('faces', 'faces', true, false, false, 'faces'));
  expect(read(EARLIER.edges)).toEqual(geometry('edges', 'edges', false, true, false, 'edges'));
  expect(read(EARLIER.position)).toEqual(geometry('none', 'all', false, false, false, 'position'));
  // A part file has no Parts box: its Automatic is its faces and edges, as it was.
  expect(read(EARLIER.all, false)).toEqual(geometry('topology', 'faces', true, true, false, 'all'));
  // The mixes no single choice could make: the knobs beside one kind, two kinds, nothing at all.
  expect(read(['faces', 'position'])).toEqual(geometry('faces', 'faces', true, false, false, 'faces'));
  expect(read(['faces', 'edges'])).toEqual(geometry('topology', 'faces', true, true, false, 'filter'));
  expect(read(['parts', 'faces'])).toEqual(geometry('all', 'all', true, false, true, 'filter'));
  expect(read(['parts', 'edges', 'measurement'])).toEqual(geometry('all', 'all', false, true, true, 'filter'));
  expect(read([])).toEqual(geometry('none', 'all', false, false, false, 'filter'));
  // The strip's buttons: the pointer and the ruler, badged with a kind's glyph alone, the funnel for a mix, none for All.
  const icons = (Select: any, Measure: any) => {
    const { container } = render(<>{['all', 'parts', 'faces', 'edges', 'position', 'filter'].map(mode => <Select key={mode} mode={mode} />)}
      {[MEASURE_FILTER_DEFAULT, ['vertex'], ['edge'], ['face'], ['vertex', 'face'], []].map(filter => <Measure key={filter.join()} mode={measureBadge(filter)} />)}</>);
    const found = [...container.querySelectorAll('svg[data-tool-icon-base]')].map(icon =>
      `${icon.getAttribute('data-tool-icon-base')}:${icon.querySelector('[data-tool-icon-badge]')?.getAttribute('data-tool-icon-badge') ?? ''}`);
    cleanup();
    return found;
  };
  expect(icons(XbfSelectIcon, XbfMeasureIcon)).toEqual(['select:', 'select:parts', 'select:faces', 'select:edges', 'select:position', 'select:filter',
    'measure:', 'measure:points', 'measure:edges', 'measure:faces', 'measure:filter', 'measure:filter']);
  expect(['all', 'parts', 'topology', 'none'].map(mode => treeShape(mode))).toEqual(['all', 'parts', 'faces', 'all']);
  expect(selectGeometryMode(['faces', 'edges'])).toBe('topology');
});

it("Select and Box select are two tools in the Selection tool section at the top of Select's menu, apart from what they pick", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const toolChange = vi.fn(), change = vi.fn();
  function Harness() {
    const [tool, setTool] = useState<'select' | 'box'>('select');
    const [value, setValue] = useState<readonly string[]>(['faces']);
    return <>
      <XbfSelectMenu value={value} onChange={(next: readonly string[]) => { setValue(next); change(next); }} assembly={false} posable={false}
        tool={tool} onToolChange={(next: 'select' | 'box') => { setTool(next); toolChange(next); }} />
      <XbfSelectIcon tool={tool} mode="faces" aria-hidden="true" />
    </>;
  }
  const open = () => user.click(document.querySelector<HTMLElement>('[data-select-filter-trigger]')!);
  const tools = () => [...document.querySelectorAll('[data-select-tool]')].map(item => `${item.textContent}:${item.getAttribute('aria-checked')}`);
  const badge = () => [...document.querySelectorAll('svg[data-tool-icon-base]')].map(icon =>
    `${icon.getAttribute('data-tool-icon-base')}:${icon.querySelector('[data-tool-icon-badge]')?.getAttribute('data-tool-icon-badge') ?? ''}`);
  render(<Harness />);
  expect(badge()).toEqual(['select:faces']);
  await open();
  // The tools first, each with its glyph, then a rule, then the Filter row, what a pick takes.
  const menu = document.querySelector<HTMLElement>('[role=menu]')!;
  expect(tools()).toEqual(['Select:true', 'Box select:false']);
  expect(menu.querySelector('[data-select-tool="box"] svg[data-mode-glyph]')?.getAttribute('data-mode-glyph')).toBe('boxSelect');
  const order = [...menu.querySelectorAll('[data-select-tool], [role=separator], [data-select-filter-row]')]
    .map(item => item.getAttribute('data-select-tool') ?? item.getAttribute('data-select-filter-row') ?? 'rule');
  expect(order).toEqual(['select', 'box', 'rule', 'filter']);
  expect(menu.querySelector('[data-select-filter-row]')?.getAttribute('aria-label')).toBe('Filter: Faces');
  expect([...menu.querySelectorAll('[data-slot=dropdown-menu-label]')].map(label => label.textContent)).toEqual(['Selection tool']);
  await user.click(document.querySelector<HTMLElement>('[data-select-tool="box"]')!);
  // Choosing a tool puts the menu away and leaves what is picked as it was; the strip's button is Box select's, badged the same.
  expect([toolChange.mock.calls, change.mock.calls, !!document.querySelector('[role=menu]')]).toEqual([[['box']], [], false]);
  expect(badge()).toEqual(['boxSelect:faces']);
  await open();
  expect(tools()).toEqual(['Select:false', 'Box select:true']);
  cleanup();
  // Without a tool to choose, the menu has no Selection tool section.
  render(<XbfSelectMenu value={['faces']} onChange={() => {}} assembly={false} posable={false} />);
  await open();
  expect(document.querySelectorAll('[data-select-tool]').length).toBe(0);
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
  const pose = useXbfPose(kinematics);
  onPose(pose.values);
  return <InPanel tab="position">
    <XbfPositionSection kinematics={kinematics} values={pose.values} couplings={pose.couplings} preset={pose.preset}
      onValues={pose.setValues} onPreset={pose.choosePreset} onReset={pose.reset} />
  </InPanel>;
}

// What the Position tab shows, in order: its name and its head's controls, then its body's.
const positionTab = () => document.querySelector<HTMLElement>('[data-flat-panel-section="position"]')!;
function positionControls() {
  const panel = positionTab();
  return {
    head: [document.querySelector('[data-flat-panel-tab="position"] [data-flat-panel-tab-name]')!.textContent,
      `Reset position:${(panel.querySelector('[data-pose-reset]') as HTMLButtonElement).disabled}`],
    body: [...panel.querySelectorAll('[data-tool-panel-body] button, [data-tool-panel-body] input, [data-tool-panel-body] [role=slider]')]
      .map(element => `${element.getAttribute('role') || element.tagName.toLowerCase()}:${element.getAttribute('aria-label')}:${(element as HTMLInputElement).value ?? ''}`)
  };
}

it("Position is a STEP's -- its heading, its Pose row with Reset on it, a named slider and value per joint -- through a configuration and back", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  render(<XbfPosition />);
  const states: unknown[] = [positionControls()];
  const panel = positionTab();
  expect(within(panel).getByRole('button', { name: 'Reset position' }).closest('[data-pose-row]')).toBe(within(panel).getByRole('button', { name: /^Pose: / }).closest('[data-pose-row]'));
  await user.click(within(panel).getByRole('button', { name: /^Pose: / }));
  const menu = document.querySelector<HTMLElement>('[role=menu][aria-label="Pose"]')!;
  states.push(within(menu).getAllByRole('menuitemradio').map(item => `${item.textContent}:${item.getAttribute('aria-checked')}`));
  await user.click(within(menu).getByRole('menuitemradio', { name: 'open' }));
  states.push(positionControls());
  const value = within(panel).getByLabelText('hinge slider value') as HTMLInputElement;
  await user.clear(value);
  await user.type(value, '25{Enter}');
  states.push(positionControls());
  await user.click(within(panel).getByRole('button', { name: 'Reset position' }));
  states.push(positionControls());
  // The tab (Reset, in the Pose row, is off at the opening pose), the Pose row, then the joint's value on its name's line, its slider under it.
  const shown = (pose: string, value: string, atOpening: boolean) => ({ head: ['Position', `Reset position:${atOpening}`],
    body: [`button:Pose: ${pose}:`, 'button:Reset position:', `input:hinge slider value:${value}`, 'slider:hinge:'] });
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
  const panel = positionTab();
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
  const panel = positionTab();
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
  await user.click(within(panel).getByRole('button', { name: 'Reset position' }));
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

// A pick as the Selected pane and its chip's card read it, over a scene that measures what it is asked.
const describedAs = (measured: object) => xbfDescriber({ scene: { structure, describePart: (part: string) => ({ name: part }), describeElement: () => null,
  measureParts: () => measured } as any, tree: presentXbfTree(structure) });
const fact = (item: any, label: string) => item.facts.find((row: any) => row.label === label)?.value;

it("a part's description weighs it by its material and says where it sits; a subassembly's sums its parts and lists them", () => {
  expect(xbfMassText({ volume: 1000, mass: 1000e-9 * 7870, unweighed: 0 })).toBe('0.00787 kg');
  expect(xbfMassText({ volume: 1000, mass: 12.3456, unweighed: 0 })).toBe('12.35 kg');
  expect(xbfMassText({ volume: 1000, mass: null, unweighed: 1 })).toBe('no material');
  const base = describedAs({ size: [10, 20, 30], volume: 600, mass: null, unweighed: 1 })('i0');
  expect([base.title, base.what, base.tip, base.ref, fact(base, 'Size'), fact(base, 'Mass'), base.related]).toEqual(['base', 'hinge', 'hinge', 'base', '10 × 20 × 30 mm', 'no material', null]);
  const hinge = describedAs({ size: [10, 20, 30], volume: 6000, mass: 1.234, unweighed: 1 })('n0.0');
  expect([hinge.title, fact(hinge, 'Parts'), fact(hinge, 'Mass')]).toEqual(['hinge', '3', '1.234 kg · 1 without material']);
  // Its children, a row each that picks it, a folded run of one part's copies said part by part.
  expect([hinge.related.title, hinge.related.rows.map((row: any) => [row.pick, row.label])]).toEqual(['Parts', [['i0', 'base'], ['i1', 'arm_1'], ['i2', 'arm_2']]]);
  // Its chip's card is the same description.
  function Chips() {
    const scene = { structure, describePart: (part: string) => ({ name: part }), describeElement: () => null, measureParts: () => null };
    const tree = presentXbfTree(structure);
    const { chips } = useXbfSelectionChips({ scene, tree, resource: null, selectedIds: ['n0.0'], facts: new Map(), onRemove: () => {}, onHover: () => {},
      describe: xbfDescriber({ scene: scene as any, tree }) });
    return <p>{chips[0].detail.related.rows.length}</p>;
  }
  render(<Chips />);
  expect(screen.getByText('3')).toBeTruthy();
});

it("the hover tip's words for an engine document are its tree's names, measuring nothing", () => {
  const measureParts = vi.fn(() => null);
  const tip = xbfTipper({ scene: { structure, describePart: (part: string) => ({ name: part }), describeElement: () => null, measureParts } as any,
    tree: presentXbfTree(structure) });
  expect([tip('i0'), tip('n0.0'), tip('i3'), tip('i99')]).toEqual(['base · hinge', 'hinge', 'pin', '']);
  expect(measureParts).not.toHaveBeenCalled();
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

it("the view's menu offers Select tangent faces over a face or while faces are selected, tangent edges likewise, each adding the chain to the selection", () => {
  const tree = presentXbfTree(structure);
  const words = (entries: any[]) => entries.map((entry: any) => `${entry.separatorBefore ? '| ' : ''}${typeof entry.label === 'string' ? entry.label : entry.label.props.children}`);
  const actions = { onSelectTangentFaces: vi.fn(), onSelectTangentEdges: vi.fn() };
  // The view's menu as `XbfRenderer` asks for it: the menu under the press, with what the actions take from.
  const over = (menu: any, pressed: string, selectedElementIds: string[]) =>
    viewportMenuEntries({ ...menu, ...xbfTangentSources({ pressed, selectedElementIds }) }, { actions });
  const face = (selectedElementIds: string[]) => xbfTopologyMenu({ elementId: 'i0/face/2', label: 'Face 2', selectedElementIds, copyText: 'ref', zoomSelectionAvailable: false });
  const edge = (selectedElementIds: string[]) => xbfTopologyMenu({ elementId: 'i0/edge/7', label: 'Edge 7', selectedElementIds, copyText: 'ref', zoomSelectionAvailable: true });
  const space = xbfModelMenu({ tree, assembly: true, expandedIds: [], hiddenCount: 0, zoomSelectionAvailable: true });
  // Over a face, nothing selected: its tangent faces, in the pick group, and no tangent edges.
  const onFace = over(face([]), 'i0/face/2', []);
  expect(words(onFace)).toEqual(['Copy Reference', '| Select', 'Select tangent faces', '| Zoom to fit', 'Zoom to selection']);
  onFace.find((entry: any) => entry.id === 'select-tangent-faces').onSelect();
  expect(actions.onSelectTangentFaces.mock.calls[0][0]).toMatchObject({ tangentFaceIds: ['i0/face/2'], tangentEdgeIds: [] });
  // Over an edge while a face is selected: both, the edge's from the edge pressed, the faces' from the face selected.
  const onEdge = over(edge(['i0/face/2']), 'i0/edge/7', ['i0/face/2']);
  expect(words(onEdge)).toEqual(['Copy Reference', '| Select', 'Select tangent faces', 'Select tangent edges', '| Zoom to fit', 'Zoom to selection']);
  onEdge.find((entry: any) => entry.id === 'select-tangent-edges').onSelect();
  expect(actions.onSelectTangentEdges.mock.calls[0][0]).toMatchObject({ tangentFaceIds: ['i0/face/2'], tangentEdgeIds: ['i0/edge/7'] });
  // Over empty space while edges are selected: tangent edges open the menu; with nothing of either selected, neither shows.
  expect(words(over(space, '', ['i0/edge/7', 'i0/edge/9'])).slice(0, 2)).toEqual(['Select tangent edges', '| Expand all']);
  expect(words(over(space, '', [])).some(word => word.includes('tangent'))).toBe(false);
  expect(words(over(xbfPartMenu({ tree, nodeId: 'i3', assembly: true, hiddenIds: [], isolatedIds: [], selectedNodeIds: [], expandedIds: [],
    copyText: 'ref', zoomSelectionAvailable: false }), '', [])).some(word => word.includes('tangent'))).toBe(false);
  // Running one adds each chain, as its part's groups say, after what was selected; a face its groups say nothing of is itself alone.
  const groups = { faces: { 1: 0, 2: 5, 3: 5, 4: 5 }, edges: { 7: 2, 8: 2, 9: 3 } };
  const element = (id: string) => { const [instance, kind, ordinal] = id.slice(1).split('/'); return { id, kind, instance: Number(instance), ordinal: Number(ordinal) }; };
  expect(tangentChain(element('i0/face/2'), groups)).toEqual(['i0/face/2', 'i0/face/3', 'i0/face/4']);
  expect(tangentChain(element('i1/edge/8'), groups)).toEqual(['i1/edge/7', 'i1/edge/8']);
  expect(tangentChain(element('i0/face/6'), groups)).toEqual(['i0/face/6']);
  expect(tangentChain(element('i0/face/2'), null)).toEqual(['i0/face/2']);
  expect(withTangentChains(['i3', 'i0/face/3'], [tangentChain(element('i0/face/2'), groups), tangentChain(element('i0/edge/9'), groups)]))
    .toEqual(['i3', 'i0/face/3', 'i0/face/2', 'i0/face/4', 'i0/edge/9']);
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

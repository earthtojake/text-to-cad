import React, { useState } from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ModelingTreeView from '../../../../../dist/renderers/step/components/workbench/ModelingTree.js';
import { SelectModeMenu } from '../../../../../dist/renderers/step/components/workbench/SelectionModes.js';
import { useModelTools } from '../../../../../dist/renderers/step/components/workbench/ModelTools.js';
import { buildPositionSection } from '../../../../../dist/renderers/step/components/workbench/MotionControlsSection.js';
import { PositionToolIcon, positionValuesAreDefault } from '../../../../../dist/renderers/kit/inspector/kinematicsControls.js';
import FloatingToolBar from '../../../../../dist/renderers/kit/tools/FloatingToolBar.js';
import ToolPanel from '../../../../../dist/renderers/kit/tools/ToolPanel.js';
import ToolStack from '../../../../../dist/renderers/kit/tools/ToolStack.js';
import { TOOL_PANEL_WIDTH } from '../../../../../dist/renderers/kit/tools/toolStackLayout.js';
import { ViewerMobileContext } from '../../../../../dist/file-viewer/responsive.js';

// The STEP renderer's panels in the tool stack — Select's Features and its mode, the kept effects
// (Explode, Clip), Position — each where it is decided, under the stack that holds them. The
// viewport that picks and draws is the browser suite's (`StepRenderer.browser.test.mjs`).

// jsdom lays nothing out: the stack's column is given a height, and a panel its own style's size.
const STACK_HEIGHT = 600;
const restores: (() => void)[] = [];
function override(target: object, key: string, descriptor: PropertyDescriptor) {
  const previous = Object.getOwnPropertyDescriptor(target, key);
  Object.defineProperty(target, key, { configurable: true, ...descriptor });
  restores.push(() => previous ? Object.defineProperty(target, key, previous) : delete (target as any)[key]);
}
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  override(HTMLElement.prototype, 'clientHeight', { get(this: HTMLElement) { return this.hasAttribute('data-cad-tool-stack') ? STACK_HEIGHT : 0; } });
  override(Element.prototype, 'scrollIntoView', { value() {} });
  for (const name of ['setPointerCapture', 'releasePointerCapture']) override(Element.prototype, name, { value() {} });
  override(Element.prototype, 'hasPointerCapture', { value: () => false });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); while (restores.length) restores.pop()!(); });

// The committed two-part fixture's shape: an assembly of a base and an arm, one recognised feature each.
const tree = [{ id: 'body:1', kind: 'body', label: 'Box', faces: [1, 2], edges: [1], complete: true, children: [] }];
const descriptor = { components: { c: { surf: 'components/c.surf' } }, occurrences: [{ id: 'o1.1', component: 'c', name: 'base' }, { id: 'o1.2', component: 'c', name: 'arm' }] };
const partNode = (id: string, name: string) => ({ id, nodeType: 'part', name, leafPartIds: [id], children: [] });
const stepRoot = { id: 'document', nodeType: 'assembly', name: 'fixture', children: [partNode('o1.1', 'base'), partNode('o1.2', 'arm')] };
const modeling = { descriptor, results: { c: { tree } }, error: null, retryFailed: vi.fn() };

const rows = () => [...document.querySelectorAll('[aria-label="Modeling tree"] button')].map(button => button.getAttribute('aria-label'))
  .filter(label => /^(?:Select|Expand|Collapse) /.test(label || ''));
const locks = () => [...document.querySelectorAll<HTMLElement>('[aria-label="Modeling tree"] [data-disclosure-locked]')].map(mark => mark.dataset.disclosureLocked);
// The Features panel, on screen or closed (`hidden`, still mounted).
const features = () => document.querySelector<HTMLElement>('section[data-tool-panel][aria-label="Features"]')!;
const shown = () => [...document.querySelectorAll<HTMLElement>('[data-cad-tool-stack] section[data-tool-panel]')].filter(node => !node.hidden).map(node => node.getAttribute('aria-label'));

/** The layout a host keeps, applying what the stack writes back. */
function useLayout(initial: any = { panels: {}, collapsed: {}, closed: {} }) {
  const [layout, setLayout] = useState<any>(initial);
  return [layout, (patch: any) => setLayout((current: any) => ({ ...current, ...(typeof patch === 'function' ? patch(current) : patch) }))] as const;
}
function Features({ mode = 'all', initialLayout = undefined as any, mobile = false }) {
  const [layout, change] = useLayout(initialLayout);
  const [expanded, setExpanded] = useState<string[]>([]);
  // The shell hands the stack the viewer's layout, as it hands every panel (`RendererShell.jsx`).
  return <ViewerMobileContext.Provider value={mobile}><ToolStack layout={layout} onLayoutChange={change} mobile={mobile}>
    <ModelingTreeView modeling={modeling} stepRoot={stepRoot} active mode={mode} references={[]} onLoadTopology={() => {}}
      modeMenu={<SelectModeMenu mode={mode} assembly onModeChange={() => {}} connected={{ edgeChain: true, tangentFaces: true }} onConnectedChange={() => {}} />}
      partControls={{ isAssemblyView: true, expandedTreeNodeIds: expanded,
        onToggleTreeNode: (id: string) => setExpanded(current => current.includes(id) ? current.filter(value => value !== id) : [...current, id]) }} />
    <output data-layout={JSON.stringify(layout)} />
  </ToolStack></ViewerMobileContext.Provider>;
}
const storedLayout = () => JSON.parse(document.querySelector('[data-layout]')!.getAttribute('data-layout')!);

it("Select's mode button sits in the Features filter row beside its X, and each mode holds the tree: Parts a row per part, Faces everything open, locked; All the person's own tree again", () => {
  const view = render(<Features />);
  expect([...features().querySelectorAll('[data-slot=tree-filter] button')].map(button => button.getAttribute('aria-label')))
    .toEqual(['Select mode: All', 'Close features']);
  // All: the tree is the person's own — open the base.
  expect(rows()).toEqual(['Expand base', 'Select base', 'Expand arm', 'Select arm']);
  fireEvent.click(screen.getByRole('button', { name: 'Expand base' }));
  expect(rows()).toEqual(['Collapse base', 'Select base', 'Select Box', 'Expand arm', 'Select arm']);
  expect(locks()).toEqual([]);
  // Parts: every part a row, none open, and no disclosure to press.
  view.rerender(<Features mode="parts" />);
  expect(screen.getByRole('button', { name: 'Select mode: Parts' })).toBeTruthy();
  expect(rows()).toEqual(['Select base', 'Select arm']);
  expect(locks()).toEqual(['shut', 'shut']);
  // Faces (and Edges): everything open, down to the features, and locked.
  view.rerender(<Features mode="faces" />);
  expect(rows()).toEqual(['Select base', 'Select Box', 'Select arm', 'Select Box']);
  expect(locks()).toEqual(['open', 'open']);
  view.rerender(<Features mode="edges" />);
  expect(locks()).toEqual(['open', 'open']);
  // All: the tree the person left — the base open, the arm shut — and unlocked.
  view.rerender(<Features mode="all" />);
  expect(rows()).toEqual(['Collapse base', 'Select base', 'Select Box', 'Expand arm', 'Select arm']);
  expect(locks()).toEqual([]);
});

it("Features closes by the X at its filter row's end, kept mounted with its filter and expansion; the mode menu and the X step aside while the box has focus", async () => {
  const user = userEvent.setup();
  render(<Features />);
  const search = screen.getByRole('textbox', { name: 'Filter model' }) as HTMLInputElement;
  expect(search.getAttribute('placeholder')).toBe('Filter…');
  // The trailing controls (the mode menu, the X) yield to a focused box (`tree-filter.jsx`).
  expect(features().querySelector('[data-tree-filter-trailing]')!.className).toContain('group-has-[input:focus]/filter:hidden');
  expect(within(features()).queryByRole('button', { name: /^(?:Collapse|Expand) features$/ })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Expand base' }));
  await user.click(search);
  await user.keyboard('ba');
  expect(within(features()).getByRole('status').textContent).toMatch(/match/);
  fireEvent.click(within(features()).getByRole('button', { name: 'Close features' }));
  expect(shown()).toEqual([]);
  expect(features().hasAttribute('data-closed')).toBe(true);
  expect(storedLayout().closed).toEqual({ tree: true });
  // Still mounted: the box keeps what was typed.
  expect((screen.getByRole('textbox', { name: 'Filter model', hidden: true }) as HTMLInputElement).value).toBe('ba');
});

it("on a phone Features starts closed, and opened takes the whole column; on desktop it is open, half the column, and the person's to size by its corner", () => {
  const phone = render(<Features mobile />);
  expect(shown()).toEqual([]);
  expect(features().hasAttribute('data-closed')).toBe(true);
  phone.unmount();
  // Opened on a phone (Select's press writes this: `RendererShell.jsx`), it takes the whole column.
  const opened = render(<Features mobile initialLayout={{ panels: {}, collapsed: {}, closed: { tree: false } }} />);
  expect(shown()).toEqual(['Features']);
  expect(features().style.maxHeight).toBe(`${STACK_HEIGHT}px`);
  opened.unmount();
  render(<Features />);
  expect(shown()).toEqual(['Features']);
  expect([...features().querySelectorAll('[role=separator]')].map(handle => handle.getAttribute('aria-label'))).toEqual(['Resize features']);
  expect(features().style.maxHeight).toBe(`${STACK_HEIGHT / 2}px`);
});

// ---- the kept effects: Explode and Clip ---------------------------------------------------------

const neutral = () => ({ exploded: { enabled: false, amount: 0 }, clip: { enabled: false, axis: 'x', offsets: { x: 1, y: 1, z: 1 }, invert: false } });
const part = (id: string) => ({ id, bounds: { min: [0, 0, 0], max: [10, 10, 10] } });
let viewSettings = neutral();
/** Select, Measure, Explode and Clip on a strip over a stack, and the Display settings they write — as the STEP surface composes them. */
function Workbench({ measure = null as any, extraPanels = null as React.ReactNode }) {
  const [view, setView] = useState(neutral);
  const [selectedTool, setTool] = useState('references');
  const [layout, change] = useLayout();
  viewSettings = view;
  const store = { patch: (patch: any) => setView(current => ({
    exploded: { ...current.exploded, ...patch.exploded },
    clip: { ...current.clip, ...patch.clip, offsets: { ...current.clip.offsets, ...patch.clip?.offsets } } })) };
  const modelTools = useModelTools({ modelKey: 'fixture', view, features: { sections: ['exploded', 'clip'] }, store,
    mesh: { parts: [part('a'), part('b')], bounds: { min: [0, 0, 0], max: [10, 10, 10] } }, disabled: false, selectedTool, onSelect: setTool, measure });
  const own = (id: string, label: string) => ({ id, label, active: selectedTool === id, icon: <span>{label[0]}</span>, onSelect: () => setTool(id) });
  return <>
    <FloatingToolBar tools={[own('references', 'Select'), own('measure', 'Measure'), ...modelTools.tools]} />
    <ToolStack layout={layout} onLayoutChange={change}>{extraPanels}{modelTools.panels}</ToolStack>
  </>;
}
const tool = (name: string) => within(screen.getByRole('group', { name: 'Interaction tools' })).getByRole('button', { name });
const pressed = () => within(screen.getByRole('group', { name: 'Interaction tools' })).getAllByRole('button')
  .filter(button => button.getAttribute('aria-pressed') === 'true').map(button => button.getAttribute('aria-label'));
const region = (name: string) => screen.queryByRole('region', { name });
const slider = (name: string) => screen.getByRole('slider', { name });

it('Explode and Clip open neutral, stack under the strip one width, are headed by their name, amount and X, and a second press or the X takes an applied effect away without resetting the other', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  render(<Workbench />);
  await user.click(tool('Explode'));
  expect(pressed()).toEqual(['Explode']);
  expect(screen.getByRole('group', { name: 'Interaction tools' }).querySelector('[role=separator]')).toBeNull();
  expect(slider('Explode amount').getAttribute('aria-valuenow')).toBe('0');
  expect(viewSettings.exploded.enabled).toBe(false);
  fireEvent.keyDown(slider('Explode amount'), { key: 'End' });
  expect(viewSettings.exploded).toEqual({ enabled: true, amount: 1 });
  await user.click(tool('Clip'));
  expect(pressed()).toEqual(['Explode', 'Clip']);
  const clip = region('Clip controls')!;
  expect(viewSettings.clip.enabled).toBe(false);
  // The body is the axis and ONE slider: no typed value, no Flip. Changing the axis stays neutral.
  expect(within(clip).queryByLabelText('Clip amount value')).toBeNull();
  expect(within(clip).queryByRole('checkbox', { name: 'Flip' })).toBeNull();
  for (const axis of ['Y', 'Z', 'X']) {
    await user.click(within(clip).getByRole('combobox', { name: 'Clip axis' }));
    await user.click(screen.getByRole('option', { name: axis }));
    expect(within(clip).getByRole('combobox', { name: 'Clip axis' }).textContent).toBe(axis);
    expect(['aria-valuemin', 'aria-valuemax', 'aria-valuenow'].map(name => slider('Clip amount').getAttribute(name))).toEqual(['0', '100', '0']);
    expect(viewSettings.clip.enabled).toBe(false);
  }
  fireEvent.keyDown(slider('Clip amount'), { key: 'ArrowRight' });
  expect(viewSettings.clip.enabled).toBe(true);
  fireEvent.keyDown(slider('Clip amount'), { key: 'Home' });
  expect(viewSettings.clip.enabled).toBe(false);
  fireEvent.keyDown(slider('Clip amount'), { key: 'PageUp' });
  expect(viewSettings.clip.enabled).toBe(true);
  // Neither folds: a heading of its name and its amount, and the X; each a fixed panel the one width.
  for (const [name, label] of [['Explode', 'Explode controls'], ['Clip', 'Clip controls']]) {
    const heading = region(label)!.querySelector<HTMLElement>('[data-tool-panel-heading]')!;
    expect(within(heading).getByRole('heading').textContent).toBe(name);
    expect(heading.textContent).toMatch(new RegExp(`^${name}\\d+%$`));
    expect([...heading.querySelectorAll('button')].map(button => button.getAttribute('aria-label'))).toEqual([`Close ${name.toLowerCase()} controls`]);
    expect([region(label)!.getAttribute('data-tool-panel'), region(label)!.style.width]).toEqual(['fixed', `${TOOL_PANEL_WIDTH}px`]);
  }
  // Select is the tool again; both applied effects keep their panels, in the order they were taken up.
  await user.click(tool('Select'));
  expect(pressed()).toEqual(['Select', 'Explode', 'Clip']);
  expect(shown()).toEqual(['Explode controls', 'Clip controls']);
  // A second press on an applied Clip removes it; Explode keeps its amount.
  await user.click(tool('Clip'));
  expect(region('Clip controls')).toBeNull();
  expect(pressed()).toEqual(['Select', 'Explode']);
  expect(viewSettings.clip.enabled).toBe(false);
  expect(slider('Explode amount').getAttribute('aria-valuenow')).toBe('100');
  await user.click(within(region('Explode controls')!).getByRole('button', { name: 'Close explode controls' }));
  expect(region('Explode controls')).toBeNull();
  expect(viewSettings.exploded.enabled).toBe(false);
  // A neutral Clip is the tool in hand, not an effect kept beside Select; reopening starts neutral.
  await user.click(tool('Clip'));
  expect(pressed()).toEqual(['Clip']);
  expect([viewSettings.clip.enabled, viewSettings.clip.invert]).toEqual([false, false]);
  await user.click(tool('Clip'));
  expect(region('Clip controls')).toBeNull();
  expect(pressed()).toEqual(['Select']);
  await user.click(tool('Explode'));
  await user.click(tool('Explode'));
  expect(region('Explode controls')).toBeNull();
  expect(pressed()).toEqual(['Select']);
});

it('a neutral effect leaves with the next tool, an applied one stays until cleared, and a panel whose value passes through neutral under a held pointer stays until it lets go', async () => {
  const user = userEvent.setup();
  render(<Workbench />);
  await user.click(tool('Clip'));
  expect(pressed()).toEqual(['Clip']);
  await user.click(tool('Select'));
  expect(region('Clip controls')).toBeNull();
  await user.click(tool('Explode'));
  expect(viewSettings.exploded.amount).toBe(0);
  await user.click(tool('Measure'));
  expect(region('Explode controls')).toBeNull();
  // Applied, both stay under another tool.
  await user.click(tool('Explode'));
  fireEvent.keyDown(slider('Explode amount'), { key: 'End' });
  await user.click(tool('Clip'));
  fireEvent.keyDown(slider('Clip amount'), { key: 'PageUp' });
  await user.click(tool('Measure'));
  expect(shown()).toEqual(['Explode controls', 'Clip controls']);
  // Back to zero from the keyboard, the cut is gone and so is its panel.
  fireEvent.keyDown(slider('Clip amount'), { key: 'Home' });
  expect(region('Clip controls')).toBeNull();
  // A press held in a kept panel while its value passes through zero keeps the panel under the pointer...
  const heading = () => region('Explode controls')!.querySelector('[data-tool-panel-heading]')!;
  fireEvent.pointerDown(heading());
  fireEvent.keyDown(slider('Explode amount'), { key: 'Home' });
  expect(viewSettings.exploded.amount).toBe(0);
  expect(region('Explode controls')).not.toBeNull();
  fireEvent.keyDown(slider('Explode amount'), { key: 'PageUp' });
  act(() => { window.dispatchEvent(new Event('pointerup')); });
  expect(region('Explode controls')).not.toBeNull();
  // ...and let go at zero, it goes.
  fireEvent.pointerDown(heading());
  fireEvent.keyDown(slider('Explode amount'), { key: 'Home' });
  expect(region('Explode controls')).not.toBeNull();
  act(() => { window.dispatchEvent(new Event('pointerup')); });
  expect(region('Explode controls')).toBeNull();
});

it('a short viewer: the tree gives way first, then the details panels, a kept effect never; the column is bounded by the stack and scrolls rather than cutting a panel', () => {
  const measure = { shown: true, controls: <p>0 measurements</p>, onRemove() {} };
  render(<Workbench measure={measure} extraPanels={<ModelingTreeView modeling={modeling} stepRoot={stepRoot} active references={[]} onLoadTopology={() => {}}
    selectionDetails={{ content: <p>Part o1.2</p> }} partControls={{ isAssemblyView: true, expandedTreeNodeIds: [] }} />} />);
  fireEvent.click(tool('Explode'));
  fireEvent.keyDown(slider('Explode amount'), { key: 'PageUp' });
  fireEvent.click(tool('Clip'));
  fireEvent.keyDown(slider('Clip amount'), { key: 'PageUp' });
  expect(shown()).toEqual(['Features', 'Reference details', 'Measure controls', 'Explode controls', 'Clip controls']);
  // How each gives way (`ToolPanel.jsx`'s fit): the tree first, then the details, the kept effects never.
  expect(Object.fromEntries([...document.querySelectorAll<HTMLElement>('[data-cad-tool-stack] section[data-tool-panel]')]
    .map(panel => [panel.getAttribute('aria-label'), panel.getAttribute('data-tool-panel')]))).toEqual({
    Features: 'tree', 'Reference details': 'details', 'Measure controls': 'details', 'Explode controls': 'fixed', 'Clip controls': 'fixed' });
  // The panels' column is exactly the stack's height, inside the stack's own scroll region.
  const column = features().parentElement!;
  expect(column.style.maxHeight).toBe(`${STACK_HEIGHT}px`);
  expect(column.closest('[data-tool-stack-scroller]')).not.toBeNull();
});

// ---- Position ------------------------------------------------------------------------------------

const hinge = { url: '/hinge.step.json', articulation: { schemaVersion: 2,
  controls: [{ id: 'hinge', label: 'hinge', unit: 'deg', min: -180, max: 180, default: 0 }],
  joints: [], carries: {}, handles: [], poses: { open: { hinge: 90 } }, opening: { hinge: 0 } } };
/** STEP's Position panel as the tool stack draws it (`StepPanels.js`) over a pose runtime, and the strip's Position icon. */
function Position({ onClose }: { onClose(): void }) {
  const [values, setValues] = useState<Record<string, number>>({ hinge: 0 });
  const [activePose, setActivePose] = useState('');
  const runtime = { definition: hinge, parameterValues: values, activePose,
    onApplyPose: (name: string) => { setActivePose(name); setValues({ hinge: (hinge.articulation.poses as any)[name].hinge }); },
    onResetMotion: () => { setActivePose(''); setValues({ hinge: 0 }); },
    onParameterChange: (id: string, value: number) => { setActivePose(''); setValues(current => ({ ...current, [id]: value })); } };
  const position = buildPositionSection({ poseRuntime: runtime })!;
  return <>
    <button type="button" aria-label="Position"><PositionToolIcon custom={!positionValuesAreDefault(values, hinge.articulation.opening)} /></button>
    <ToolPanel id="position" title={position.title} actions={position.actions} label="Position controls" fit="details" resizable
      collapsible={false} onClose={onClose} closeLabel="Close position">{position.content}</ToolPanel>
  </>;
}

it("Position is headed with its Reset and its X, offers Default beside a named pose, names every joint's slider, and marks its tool while posed", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const onClose = vi.fn();
  render(<Position onClose={onClose} />);
  const panel = screen.getByRole('region', { name: 'Position controls' });
  const heading = panel.querySelector<HTMLElement>('[data-tool-panel-heading]')!;
  expect(within(heading).getByRole('heading').textContent).toBe('Position');
  // It does not fold: Reset, then the X.
  expect([...heading.querySelectorAll('button')].map(button => button.getAttribute('aria-label'))).toEqual(['Reset', 'Close position']);
  const preset = within(panel).getByRole('combobox', { name: 'Pose' });
  const value = within(panel).getByLabelText('hinge slider value') as HTMLInputElement;
  expect(preset.textContent).toBe('Default');
  expect(panel.querySelector('[data-position-header]')!.textContent).toContain('Pose');
  expect(within(panel).getAllByRole('slider').filter(thumb => !thumb.getAttribute('aria-label'))).toEqual([]);
  expect(within(panel).getByRole('slider', { name: 'hinge' })).toBeTruthy();
  await user.click(preset);
  expect(screen.getAllByRole('option').map(option => option.textContent)).toEqual(['Default', 'open']);
  await user.click(screen.getByRole('option', { name: 'open' }));
  expect([value.value, preset.textContent]).toEqual(['90.0°', 'open']);
  await user.click(preset);
  await user.click(screen.getByRole('option', { name: 'Default' }));
  expect([value.value, preset.textContent]).toEqual(['0.00°', 'Default']);
  // Posed off its default, the strip's Position icon carries a dot; Reset takes it away.
  const custom = () => screen.getByRole('button', { name: 'Position' }).querySelector('[data-position-custom]');
  expect(custom()).toBeNull();
  await user.clear(value);
  await user.type(value, '25{Enter}');
  expect(preset.textContent).toBe('Custom');
  expect(custom()).not.toBeNull();
  await user.click(within(heading).getByRole('button', { name: 'Reset' }));
  expect([value.value, preset.textContent]).toEqual(['0.00°', 'Default']);
  expect(custom()).toBeNull();
  await user.click(within(heading).getByRole('button', { name: 'Close position' }));
  expect(onClose).toHaveBeenCalledOnce();
});


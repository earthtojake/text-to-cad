import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { resolveViewSettings } from '@text-to-cad/core/common/viewSettings.js';
import { createViewSettingsStore } from './viewSettingsStore.js';
import { DisplaySettingsSection } from '../../../../dist/renderers/kit/view-settings/DisplaySettingsSection.js';
import { CrossSectionControls, ExplodeControls, clipSummary } from '../../../../dist/renderers/step/components/workbench/ModelViewControls.js';
import { FileSheetSettingsSection } from '../../../../dist/renderers/kit/inspector/FileSheet.js';

Object.assign(globalThis, { React });
beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });
let current: any;
function Harness({ initial = { mode: 'solid' } }: { initial?: any }) {
  const [store] = React.useState(() => createViewSettingsStore(initial));
  const { display: settings, scene } = React.useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  current = settings;
  return <DisplaySettingsSection viewSettings={settings} resolvedView={scene.view}
    onViewSettingsPatch={store.patch} onGroupEnabledChange={store.setEnabled}
    onViewReset={store.reset} onModeChange={store.selectPreset}
    clipBounds={{ min: [0, 0, 0], max: [100, 100, 100] }} />;
}

it('a deliberate click on a shut plus after hovering cannot shut it again', async () => {
  const user = userEvent.setup();
  function Gate() {
    const [enabled, setEnabled] = React.useState(false);
    return <FileSheetSettingsSection gated title="Grid" open={enabled} onOpenChange={setEnabled}>Grid settings</FileSheetSettingsSection>;
  }
  render(<Gate />);
  const plus = screen.getByRole('button', { name: 'Enable Grid' });
  await user.hover(plus);
  await new Promise(resolve => setTimeout(resolve, 200));
  await user.click(plus);
  expect(screen.getByText('Grid settings')).toBeTruthy();
});

it.each(['Edges', 'Grid / Axes'])('Render remains a preset when the pointer rests on disabled %s', title => {
  vi.useFakeTimers();
  render(<Harness initial={{ mode: 'render' }} />);
  const heading = screen.getByRole('heading', { name: title, exact: true });
  fireEvent.pointerEnter(heading, { pointerType: 'mouse' });
  act(() => vi.advanceTimersByTime(1000));
  expect(current).toEqual({ mode: 'render' });
  expect(screen.getByRole('combobox', { name: 'Mode', exact: true }).textContent).toBe('Render');
  expect(screen.getByRole('button', { name: `Enable ${title}` }).getAttribute('aria-expanded')).toBe('false');
});

it('opens individual features by click or keyboard; only the minus disables and clears edits', async () => {
  const user = userEvent.setup();
  render(<Harness />);
  const floor = screen.getByRole('button', { name: 'Floor', exact: true });
  expect(floor.getAttribute('aria-expanded')).toBe('false');
  await user.click(floor);
  expect(screen.getByRole('button', { name: 'Disable Floor' }).getAttribute('aria-expanded')).toBe('true');
  const heading = screen.getByRole('heading', { name: 'Floor' });
  const header = heading.parentElement!;
  fireEvent.pointerLeave(header);
  expect(screen.getByRole('button', { name: 'Floor color' })).toBeTruthy();
  expect(screen.queryByRole('checkbox', { name: 'Floor' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Floor', exact: true }).getAttribute('aria-expanded')).toBe('true');
  expect(header.className).not.toContain('hover:');
  await user.click(screen.getByRole('button', { name: 'Floor', exact: true }));
  expect(current.floor.enabled).toBe(true);
  await user.click(screen.getByRole('button', { name: 'Floor color' }));
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Color opacity' }), { target: { value: '80' } });
  expect(current.floor.opacity).toBe(0.8);
  await user.keyboard('{Escape}');
  await user.click(screen.getByRole('button', { name: 'Disable Floor' }));
  expect(current.floor).toEqual({ enabled: false });
  expect(current.lighting).toBeUndefined();
  expect(current.background).toBeUndefined();
  expect(screen.queryByRole('button', { name: 'Floor color' })).toBeNull();
  screen.getByRole('button', { name: 'Floor', exact: true }).focus(); await user.keyboard('{Enter}');
  expect(resolveViewSettings(current).floor.opacity).toBe(0.6);
  expect(screen.getByRole('button', { name: 'Disable Floor' }).getAttribute('aria-expanded')).toBe('true');
});

it('does not enable a section when the pointer only passes across it', async () => {
  const enabled = vi.fn();
  render(<FileSheetSettingsSection gated title="Feature" open={false} onOpenChange={enabled}>Controls</FileSheetSettingsSection>);
  const header = screen.getByRole('button', { name: 'Feature' }).parentElement!;
  fireEvent.pointerEnter(header, { pointerType: 'mouse' });
  fireEvent.pointerLeave(header);
  await new Promise(resolve => setTimeout(resolve, 180));
  expect(enabled).not.toHaveBeenCalled();
});

it('Reset disables tools and restores the preset; transparency stays in the color picker', async () => {
  const user = userEvent.setup();
  render(<Harness initial={{ mode: 'render', background: { color: '#abcdef', opacity: 0.4 }, exploded: { enabled: true, amount: 0.5 } }} />);
  const mode = screen.getByRole('region', { name: 'Display', exact: true });
  expect(within(mode).getByRole('combobox', { name: 'Mode' }).textContent).toBe('Custom');
  // Projection shares the first row with Mode.
  expect(within(mode).getByRole('combobox', { name: 'Projection' })).toBeTruthy();
  expect(within(mode).queryByRole('slider')).toBeNull();
  const background = screen.getByRole('button', { name: 'Background color' });
  const preview = background.querySelector('[data-color-preview]') as HTMLElement;
  expect(preview.style.opacity).toBe('0.4');
  expect(preview.parentElement!.style.backgroundImage).toContain('conic-gradient');
  expect(screen.queryByRole('checkbox', { name: 'Transparent' })).toBeNull();
  await user.click(background);
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Color opacity' }), { target: { value: '0' } });
  expect(current.background.opacity).toBe(0);
  await user.keyboard('{Escape}');
  await user.click(screen.getByRole('button', { name: 'Reset', exact: true }));
  expect(current).toEqual({ mode: 'render' });
  expect(within(mode).getByRole('combobox', { name: 'Mode' }).textContent).toBe('Render');
});

it('keeps one section order in every preset, Display first', () => {
  const headings = ['Display', 'Surfaces', 'Edges', 'Grid / Axes', 'Lighting', 'Background', 'Floor'];
  for (const mode of ['solid', 'render', 'wireframe']) {
    render(<Harness initial={{ mode }} />);
    expect(screen.getAllByRole('heading').map(node => node.textContent)).toEqual(headings);
    cleanup();
  }
});

// Explode and Cross-section remain independent STEP tools, with their own stack panels.
function Tools() {
  const [store] = React.useState(() => createViewSettingsStore({ mode: 'solid' }));
  const { display: settings } = React.useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  current = settings;
  return <>
    <button type="button" onClick={() => store.setEnabled('exploded', !resolveViewSettings(settings).exploded.enabled)}>Explode</button>
    <button type="button" onClick={() => store.setEnabled('clip', !resolveViewSettings(settings).clip.enabled)}>Cross-section</button>
    <ExplodeControls viewSettings={settings} onViewSettingsPatch={store.patch} />
    <output aria-label="Clip summary">{clipSummary(settings)}</output>
    <CrossSectionControls viewSettings={settings} onViewSettingsPatch={store.patch} bounds={{ min: [0, 0, 0], max: [100, 100, 100] }} />
  </>;
}

it('Display has no Explode or Cross-section: they are STEP tools of their own', () => {
  render(<Harness />);
  for (const name of ['Explode', 'Clip', 'Cross-section']) expect(screen.queryByRole('heading', { name })).toBeNull();
  expect(screen.queryByRole('slider', { name: 'Explode amount' })).toBeNull();
  expect(screen.queryByRole('textbox', { name: /^Cross-section [XYZ] position$/ })).toBeNull();
});

it('Explode turns on at half, its slider sets the amount, zero removes it, and it restarts at half', async () => {
  const user = userEvent.setup();
  render(<Tools />);
  await user.click(screen.getByRole('button', { name: 'Explode' }));
  const amount = () => screen.getByRole('slider', { name: 'Explode amount' });
  expect(amount().getAttribute('aria-valuenow')).toBe('50');
  amount().focus();
  await user.keyboard('{ArrowRight}');
  expect(current.exploded).toEqual({ enabled: true, amount: 0.51 });
  await user.keyboard('{Home}');
  expect(current.exploded).toEqual({ enabled: false, amount: 0 });
  await user.click(screen.getByRole('button', { name: 'Explode' }));
  expect(amount().getAttribute('aria-valuenow')).toBe('50');
});

it('Cross-section turns on at an X centre cut; its body is the axis dropdown and one slider: the slider sets the amount, zero removes it, the dropdown moves the cut', async () => {
  const user = userEvent.setup();
  render(<Tools />);
  await user.click(screen.getByRole('button', { name: 'Cross-section' }));
  expect(resolveViewSettings(current).clip.offsets.x).toBe(0.5);
  // One slider and nothing else: no typed value, no Flip.
  expect(screen.queryByRole('textbox', { name: 'Clip amount value' })).toBeNull();
  expect(screen.queryByRole('checkbox', { name: 'Flip' })).toBeNull();
  const amount = () => screen.getByRole('slider', { name: 'Clip amount' });
  expect(amount().getAttribute('aria-valuenow')).toBe('50');
  // The axis is a compact dropdown left of the slider, in the one row of the body.
  const axis = screen.getByRole('combobox', { name: 'Clip axis' });
  expect(axis.textContent).toBe('X');
  expect(axis.closest('[data-slot="slider"]')).toBeNull();
  expect(amount().closest('[data-slot="slider"]')!.parentElement!.contains(axis)).toBe(true);
  expect(axis.compareDocumentPosition(amount()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getByRole('status', { name: 'Clip summary' }).textContent).toBe('50%');
  amount().focus();
  await user.keyboard('{End}');
  expect(resolveViewSettings(current).clip.offsets.x).toBe(0);
  expect(screen.getByRole('status', { name: 'Clip summary' }).textContent).toBe('100%');
  fireEvent.keyDown(axis, { key: 'ArrowDown' });
  fireEvent.click(screen.getByRole('option', { name: 'Y', exact: true }));
  expect(resolveViewSettings(current).clip.axis).toBe('y');
  expect(resolveViewSettings(current).clip.offsets.y).toBe(0);
  // The dropdown hands focus back to its trigger as it closes; take it to the slider after that.
  await waitFor(() => expect(screen.queryByRole('listbox')).toBeNull());
  await act(async () => {});
  amount().focus();
  await user.keyboard('{Home}');
  expect(resolveViewSettings(current).clip.enabled).toBe(false);
  expect(resolveViewSettings(current).clip.invert).toBe(false);
});

it('disables and restores Grid / Axes together while keeping colors independent', async () => {
  const user = userEvent.setup();
  render(<Harness initial={{ mode: 'solid', grid: { color: '#abcdef' }, axes: { color: '#123456' } }} />);
  await user.click(screen.getByRole('button', { name: 'Disable Grid / Axes' }));
  expect(current.grid).toEqual({ enabled: false });
  expect(current.axes).toEqual({ enabled: false });
  expect(screen.queryByRole('button', { name: 'Grid color' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Axis color' })).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Enable Grid / Axes' }));
  // Solid draws neither; turned on by hand they are the quiet grid and axes.
  expect(resolveViewSettings(current).grid).toEqual({ ...resolveViewSettings({ mode: 'solid' }).grid, enabled: true });
  expect(resolveViewSettings(current).axes).toEqual({ ...resolveViewSettings({ mode: 'solid' }).axes, enabled: true });
});

it('enabling Background does not expose or enable Lighting or Floor', () => {
  render(<Harness initial={{ mode: 'solid', background: { enabled: true } }} />);
  expect(screen.getByRole('button', { name: 'Background color' })).toBeTruthy();
  expect(screen.queryByRole('textbox', { name: 'Exposure value' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Floor color' })).toBeNull();
  expect(resolveViewSettings(current).lighting.enabled).toBe(false);
  expect(resolveViewSettings(current).floor.enabled).toBe(false);
});

it('the Projection value ends in an ellipsis when its column is narrow, with its icon beside it', () => {
  render(<Harness initial={{ mode: 'solid', camera: { enabled: true, projection: 'orthographic' } }} />);
  const trigger = screen.getByRole('combobox', { name: 'Projection' });
  const value = within(trigger).getByText('Orthographic');
  expect(value.classList.contains('truncate')).toBe(true);
  expect(value.parentElement!.querySelector('svg')).not.toBeNull();
});

it('Explode and Clip report their value at their step\'s precision, never float noise', () => {
  // 0.28 × 100 is 28.000000000000004, and 1 − 0.7 is 0.30000000000000004: a screen reader would read both.
  render(<ExplodeControls viewSettings={{ exploded: { enabled: true, amount: 0.28 } }} onViewSettingsPatch={() => {}} />);
  expect(screen.getByRole('slider', { name: 'Explode amount' }).getAttribute('aria-valuenow')).toBe('28');
  cleanup();
  render(<CrossSectionControls viewSettings={{ clip: { enabled: true, axis: 'x', offsets: { x: 0.7, y: 1, z: 1 }, invert: false } }}
    onViewSettingsPatch={() => {}} bounds={{ min: [0, 0, 0], max: [100, 100, 100] }} />);
  expect(screen.getByRole('slider', { name: 'Clip amount' }).getAttribute('aria-valuenow')).toBe('30');
});

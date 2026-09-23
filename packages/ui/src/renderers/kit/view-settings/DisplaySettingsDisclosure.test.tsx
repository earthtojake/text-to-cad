import React from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { resolveViewSettings } from '@hardcore/core/common/viewSettings.js';
import { createViewSettingsStore } from './viewSettingsStore.js';
import { CrossSectionControls, DisplaySettingsSection, ExplodeControls } from '../../../../dist/renderers/kit/view-settings/DisplaySettingsSection.js';
import { FileSheetGatedSection } from '../../../../dist/renderers/kit/inspector/FileSheet.js';

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

it('a deliberate click on a shut chevron after hovering cannot shut it again', async () => {
  const user = userEvent.setup();
  function Gate() {
    const [enabled, setEnabled] = React.useState(false);
    return <FileSheetGatedSection title="Grid" enabled={enabled} onEnabledChange={setEnabled}>Grid settings</FileSheetGatedSection>;
  }
  render(<Gate />);
  const chevron = screen.getByRole('button', { name: 'Enable Grid' });
  await user.hover(chevron);
  await new Promise(resolve => setTimeout(resolve, 200));
  await user.click(chevron);
  expect(screen.getByText('Grid settings')).toBeTruthy();
});

it.each(['Edges', 'Grid & axes'])('Render remains a preset when the pointer rests on disabled %s', title => {
  vi.useFakeTimers();
  render(<Harness initial={{ mode: 'render' }} />);
  const heading = screen.getByRole('heading', { name: title, exact: true });
  fireEvent.pointerEnter(heading, { pointerType: 'mouse' });
  act(() => vi.advanceTimersByTime(1000));
  expect(current).toEqual({ mode: 'render' });
  expect(screen.getByRole('combobox', { name: 'Mode', exact: true }).textContent).toBe('Render');
  expect(screen.getByRole('button', { name: `Enable ${title}` }).getAttribute('aria-expanded')).toBe('false');
});

it('opens feature sections by click or keyboard and only the open chevron disables them', async () => {
  const user = userEvent.setup();
  render(<Harness />);
  const environment = screen.getByRole('button', { name: 'Environment', exact: true });
  expect(environment.getAttribute('aria-expanded')).toBe('false');
  await user.click(environment);
  expect(screen.getByRole('button', { name: 'Disable Environment' }).getAttribute('aria-expanded')).toBe('true');
  const heading = screen.getByRole('heading', { name: 'Environment' });
  const header = heading.parentElement!;
  fireEvent.pointerLeave(header);
  expect(screen.getByRole('button', { name: 'Floor color' })).toBeTruthy();
  expect(screen.queryByRole('checkbox', { name: 'Environment' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Environment', exact: true })).toBeNull();
  expect(header.className).not.toContain('hover:');
  await user.click(heading);
  expect(current.floor.enabled).toBe(true);
  await user.click(screen.getByRole('button', { name: 'Floor color' }));
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Color opacity' }), { target: { value: '80' } });
  expect(current.floor.opacity).toBe(0.8);
  await user.keyboard('{Escape}');
  await user.click(screen.getByRole('button', { name: 'Disable Environment' }));
  // One gate: lighting, background and floor go off together.
  expect(current.floor).toEqual({ enabled: false });
  expect(current.lighting).toEqual({ enabled: false });
  expect(current.background).toEqual({ enabled: false });
  expect(screen.queryByRole('button', { name: 'Floor color' })).toBeNull();
  screen.getByRole('button', { name: 'Environment', exact: true }).focus(); await user.keyboard('{Enter}');
  expect(resolveViewSettings(current).floor.opacity).toBe(0.6);
  expect(screen.getByRole('button', { name: 'Disable Environment' }).getAttribute('aria-expanded')).toBe('true');
});

it('does not enable a section when the pointer only passes across it', async () => {
  const enabled = vi.fn();
  render(<FileSheetGatedSection title="Feature" enabled={false} onEnabledChange={enabled}>Controls</FileSheetGatedSection>);
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
  // Projection is the view cube's toggle, not a Display control.
  expect(within(mode).queryByRole('combobox', { name: 'Projection' })).toBeNull();
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
  const headings = ['Display', 'Edges', 'Grid & axes', 'Environment'];
  for (const mode of ['solid', 'render', 'wireframe']) {
    render(<Harness initial={{ mode }} />);
    expect(screen.getAllByRole('heading').map(node => node.textContent)).toEqual(headings);
    cleanup();
  }
});

// Explode and Cross-section are toolbar toggles; these are their panels' controls.
function Tools() {
  const [store] = React.useState(() => createViewSettingsStore({ mode: 'solid' }));
  const { display: settings } = React.useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  current = settings;
  return <>
    <button type="button" onClick={() => store.setEnabled('exploded', !resolveViewSettings(settings).exploded.enabled)}>Explode</button>
    <button type="button" onClick={() => store.setEnabled('clip', !resolveViewSettings(settings).clip.enabled)}>Cross-section</button>
    <ExplodeControls viewSettings={settings} onViewSettingsPatch={store.patch} />
    <CrossSectionControls viewSettings={settings} onViewSettingsPatch={store.patch} bounds={{ min: [0, 0, 0], max: [100, 100, 100] }} />
  </>;
}

it('Display has no Explode or Cross-section: they are the toolbar\'s', () => {
  render(<Harness />);
  for (const name of ['Explode', 'Clip', 'Cross-section']) expect(screen.queryByRole('heading', { name })).toBeNull();
  expect(screen.queryByRole('textbox', { name: 'Explode value' })).toBeNull();
  expect(screen.queryByRole('textbox', { name: /^Cross-section [XYZ] position$/ })).toBeNull();
});

it('Explode turns on at half, stays on at zero, and restarts at half', async () => {
  const user = userEvent.setup();
  render(<Tools />);
  await user.click(screen.getByRole('button', { name: 'Explode' }));
  const input = screen.getByRole('textbox', { name: 'Explode value' });
  expect((input as HTMLInputElement).value).toBe('50%');
  for (const amount of ['50', '0', '75']) {
    fireEvent.change(input, { target: { value: amount } }); fireEvent.blur(input);
    expect(current.exploded).toEqual({ enabled: true, amount: Number(amount) / 100 });
  }
  await user.click(screen.getByRole('button', { name: 'Explode' }));
  expect(current.exploded).toEqual({ enabled: false });
  await user.click(screen.getByRole('button', { name: 'Explode' }));
  expect((screen.getByRole('textbox', { name: 'Explode value' }) as HTMLInputElement).value).toBe('50%');
});

it('Cross-section turns on at an X centre cut, and Flip reverses it', async () => {
  const user = userEvent.setup();
  render(<Tools />);
  await user.click(screen.getByRole('button', { name: 'Cross-section' }));
  expect(resolveViewSettings(current).clip.offsets.x).toBe(0.5);
  const x = screen.getByRole('textbox', { name: 'Cross-section X position' });
  expect((x as HTMLInputElement).value).toBe('50.00 mm');
  fireEvent.change(x, { target: { value: '35' } }); fireEvent.blur(x);
  expect(resolveViewSettings(current).clip.offsets.x).toBeCloseTo(0.35);
  await user.click(screen.getByRole('checkbox', { name: 'Flip' }));
  expect(resolveViewSettings(current).clip.invert).toBe(true);
  await user.click(screen.getByRole('button', { name: 'Cross-section' }));
  expect(resolveViewSettings(current).clip.enabled).toBe(false);
});

it('turns Grid and Axes on and off together, under one section', async () => {
  const user = userEvent.setup();
  render(<Harness />);
  expect(screen.getByRole('button', { name: 'Grid color' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Axis color' })).toBeTruthy();
  await user.click(screen.getByRole('button', { name: 'Disable Grid & axes' }));
  expect(current.grid).toEqual({ enabled: false });
  expect(current.axes).toEqual({ enabled: false });
  expect(screen.queryByRole('button', { name: 'Grid color' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Axis color' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Environment', exact: true })).toBeTruthy();
});

it('an edit inside a combined section turns on the group it belongs to', () => {
  // Only the background is on, so Environment is open and shows Lighting while lighting is off.
  render(<Harness initial={{ mode: 'solid', background: { enabled: true } }} />);
  const exposure = screen.getByRole('textbox', { name: 'Exposure value' });
  fireEvent.change(exposure, { target: { value: '1.5' } }); fireEvent.blur(exposure);
  expect(resolveViewSettings(current).lighting.enabled).toBe(true);
  expect(resolveViewSettings(current).lighting.exposure).toBe(1.5);
});

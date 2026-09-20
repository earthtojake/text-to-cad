import React from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { resolveViewSettings } from '@hardcore/core/common/viewSettings.js';
import { createViewSettingsStore } from '../../workbench/viewSettingsStore.js';
import { DisplaySettingsSection } from '../../../../../dist/renderers/cad/components/workbench/DisplaySettingsTab.js';
import { FileSheetGatedSection } from '../../../../../dist/renderers/cad/components/workbench/FileSheet.js';

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

it('a deliberate plus click after hovering cannot become a minus click', async () => {
  const user = userEvent.setup();
  function Gate() {
    const [enabled, setEnabled] = React.useState(false);
    return <FileSheetGatedSection title="Clip" enabled={enabled} onEnabledChange={setEnabled}>Clip settings</FileSheetGatedSection>;
  }
  render(<Gate />);
  const plus = screen.getByRole('button', { name: 'Enable Clip' });
  await user.hover(plus);
  await new Promise(resolve => setTimeout(resolve, 200));
  await user.click(plus);
  expect(screen.getByText('Clip settings')).toBeTruthy();
});

it.each(['Explode', 'Clip', 'Edges', 'Grid', 'Axes'])('Render remains a preset when the pointer rests on disabled %s', title => {
  vi.useFakeTimers();
  render(<Harness initial={{ mode: 'render' }} />);
  const heading = screen.getByRole('heading', { name: title, exact: true });
  fireEvent.pointerEnter(heading, { pointerType: 'mouse' });
  act(() => vi.advanceTimersByTime(1000));
  expect(current).toEqual({ mode: 'render' });
  expect(screen.getByRole('combobox', { name: 'Mode', exact: true }).textContent).toBe('Render');
  expect(screen.getByRole('button', { name: `Enable ${title}` }).getAttribute('aria-expanded')).toBe('false');
});

it('opens feature sections by click or keyboard and only the minus disables them', async () => {
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
  expect(screen.queryByRole('button', { name: 'Floor', exact: true })).toBeNull();
  expect(header.className).not.toContain('hover:');
  await user.click(heading);
  expect(current.floor.enabled).toBe(true);
  await user.click(screen.getByRole('button', { name: 'Floor color' }));
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Color opacity' }), { target: { value: '80' } });
  expect(current.floor.opacity).toBe(0.8);
  await user.keyboard('{Escape}');
  await user.click(screen.getByRole('button', { name: 'Disable Floor' }));
  expect(current.floor).toEqual({ enabled: false });
  expect(screen.queryByRole('button', { name: 'Floor color' })).toBeNull();
  screen.getByRole('button', { name: 'Floor', exact: true }).focus(); await user.keyboard('{Enter}');
  expect(resolveViewSettings(current).floor.opacity).toBe(0.6);
  expect(screen.getByRole('button', { name: 'Disable Floor' }).getAttribute('aria-expanded')).toBe('true');
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
  const mode = screen.getByRole('region', { name: 'Mode', exact: true });
  expect(within(mode).getByRole('combobox', { name: 'Mode' }).textContent).toBe('Custom');
  expect(within(mode).getByRole('combobox', { name: 'Projection' }).querySelector('svg')).toBeTruthy();
  expect(within(mode).queryByRole('slider')).toBeNull();
  expect(within(screen.getByRole('region', { name: 'Explode', exact: true })).getByRole('textbox', { name: 'Explode value' })).toBeTruthy();
  const background = screen.getByRole('button', { name: 'Background color' });
  const preview = background.querySelector('[data-color-preview]') as HTMLElement;
  expect(preview.style.opacity).toBe('0.4');
  expect(preview.parentElement!.style.backgroundImage).toContain('conic-gradient');
  expect(screen.queryByRole('checkbox', { name: 'Transparent' })).toBeNull();
  await user.click(background);
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Color opacity' }), { target: { value: '0' } });
  expect(current.background.opacity).toBe(0);
  await user.keyboard('{Escape}');
  await user.click(screen.getByRole('button', { name: 'Clip', exact: true }));
  const x = screen.getByRole('textbox', { name: 'Clip X position' });
  fireEvent.change(x, { target: { value: '35' } }); fireEvent.blur(x);
  await user.click(screen.getByRole('checkbox', { name: 'Flip' }));
  await user.click(screen.getByRole('button', { name: 'Reset', exact: true }));
  expect(current).toEqual({ mode: 'render' });
  expect(screen.getByRole('button', { name: 'Enable Explode' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Enable Clip' })).toBeTruthy();
  expect(within(mode).getByRole('combobox', { name: 'Mode' }).textContent).toBe('Render');
  await user.click(screen.getByRole('button', { name: 'Enable Clip' }));
  expect(resolveViewSettings(current).clip.offsets.x).toBe(0.5);
  expect(resolveViewSettings(current).clip.invert).toBe(false);
  expect((screen.getByRole('textbox', { name: 'Clip X position' }) as HTMLInputElement).value).toBe('50.00 mm');
  expect((screen.getByRole('checkbox', { name: 'Flip' }) as HTMLInputElement).checked).toBe(false);
  expect(within(mode).getByRole('combobox', { name: 'Mode' }).textContent).toBe('Render');
});

it('keeps tools first, then Solid features, then optional rendering features in every preset', () => {
  const headings = ['Mode', 'Surfaces', 'Explode', 'Clip', 'Edges', 'Grid', 'Axes', 'Lighting', 'Background', 'Floor'];
  for (const mode of ['solid', 'render', 'wireframe']) {
    render(<Harness initial={{ mode }} />);
    expect(screen.getAllByRole('heading').map(node => node.textContent)).toEqual(headings);
    cleanup();
  }
});

it('keeps Explode open at zero and resets its amount when reopened without changing the preset', async () => {
  const user = userEvent.setup();
  render(<Harness />);
  expect(screen.queryByRole('textbox', { name: 'Explode value' })).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Enable Explode' }));
  const input = screen.getByRole('textbox', { name: 'Explode value' });
  expect((input as HTMLInputElement).value).toBe('50%');
  for (const amount of ['50', '0', '75']) {
    fireEvent.change(input, { target: { value: amount } }); fireEvent.blur(input);
    expect(current.exploded).toEqual({ enabled: true, amount: Number(amount) / 100 });
    expect(screen.getByRole('button', { name: 'Disable Explode' })).toBeTruthy();
  }
  await user.click(screen.getByRole('button', { name: 'Disable Explode' }));
  expect(current.exploded).toEqual({ enabled: false });
  await user.click(screen.getByRole('button', { name: 'Enable Explode' }));
  expect((screen.getByRole('textbox', { name: 'Explode value' }) as HTMLInputElement).value).toBe('50%');
  expect(screen.getByRole('combobox', { name: 'Mode', exact: true }).textContent).toBe('Solid');
});

it('exposes Grid and Axes independently in every preset', async () => {
  const user = userEvent.setup();
  render(<Harness />);
  await user.click(screen.getByRole('button', { name: 'Disable Grid' }));
  expect(current.grid).toEqual({ enabled: false });
  expect(screen.queryByRole('button', { name: 'Grid color' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Axis color' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Lighting', exact: true })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Background', exact: true })).toBeTruthy();
});

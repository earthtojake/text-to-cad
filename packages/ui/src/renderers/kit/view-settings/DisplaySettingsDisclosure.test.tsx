import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { resolveViewSettings } from '@text-to-cad/core/common/viewSettings.js';
import { createViewSettingsStore } from './viewSettingsStore.js';
import { CrossSectionControls, ExplodeControls, clipSummary } from '../../../../dist/renderers/kit/tools/model-effects/ModelViewControls.js';
import { FileSheetSettingsSection } from '../../../../dist/renderers/kit/inspector/FileSheet.js';

Object.assign(globalThis, { React });
beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });
let current: any;
// Explode and Cross-section remain independent STEP tools, with their own stack panels.
const BOUNDS = { min: [0, -50, 0], max: [100, 50, 40] };
function Tools() {
  const [store] = React.useState(() => createViewSettingsStore({ mode: 'solid' }));
  const { display: settings } = React.useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  current = settings;
  return <>
    <button type="button" onClick={() => store.patch({ exploded: { enabled: !resolveViewSettings(settings).exploded.enabled, amount: resolveViewSettings(settings).exploded.enabled ? 0 : 0.5 } })}>Explode</button>
    <button type="button" onClick={() => store.patch({ clip: { enabled: !resolveViewSettings(settings).clip.enabled } })}>Cross-section</button>
    <ExplodeControls viewSettings={settings} onViewSettingsPatch={store.patch} />
    <output aria-label="Clip summary">{clipSummary(settings, BOUNDS)}</output>
    <CrossSectionControls viewSettings={settings} onViewSettingsPatch={store.patch} bounds={BOUNDS} />
  </>;
}

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

it('Cross-section turns on at an X centre cut; its body is the axis dropdown and one slider: the slider places the plane in millimetres, zero removes it, the dropdown keeps the share on the new axis', async () => {
  const user = userEvent.setup();
  render(<Tools />);
  await user.click(screen.getByRole('button', { name: 'Cross-section' }));
  expect(resolveViewSettings(current).clip).toEqual({ enabled: true, axis: 'x', invert: false, partColors: true });
  // One slider and nothing else: no typed value, no Flip.
  expect(screen.queryByRole('textbox', { name: 'Clip amount value' })).toBeNull();
  expect(screen.queryByRole('checkbox', { name: 'Flip' })).toBeNull();
  const amount = () => screen.getByRole('slider', { name: 'Clip amount' });
  expect(amount().getAttribute('aria-valuenow')).toBe('50');
  // The axis is a compact dropdown left of the slider, in the one row of the body.
  const axis = screen.getByRole('button', { name: 'Clip axis: X' });
  expect(axis.textContent).toBe('X');
  expect(axis.closest('[data-slot="slider"]')).toBeNull();
  expect(amount().closest('[data-slot="slider"]')!.parentElement!.contains(axis)).toBe(true);
  expect(axis.compareDocumentPosition(amount()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getByRole('status', { name: 'Clip summary' }).textContent).toBe('50%');
  amount().focus();
  await user.keyboard('{ArrowRight}');
  // 50.1% of X's 0..100 cut away from the top: the plane stands at x = 49.9 mm.
  expect(resolveViewSettings(current).clip.at).toBeCloseTo(49.9, 9);
  await user.keyboard('{End}');
  expect(resolveViewSettings(current).clip.at).toBe(0);
  expect(screen.getByRole('status', { name: 'Clip summary' }).textContent).toBe('100%');
  await user.keyboard('{PageDown}');
  const share = Number(amount().getAttribute('aria-valuenow'));
  expect(share).toBeGreaterThan(50);
  expect(share).toBeLessThan(100);
  await user.click(axis);
  await user.click(screen.getByRole('menuitemradio', { name: 'Y', exact: true }));
  expect([resolveViewSettings(current).clip.axis, screen.getByRole('button', { name: 'Clip axis: Y' }).textContent]).toEqual(['y', 'Y']);
  // The same share of Y's -50..50.
  expect(resolveViewSettings(current).clip.at).toBeCloseTo(50 - share, 9);
  expect(Number(amount().getAttribute('aria-valuenow'))).toBeCloseTo(share, 9);
  // An axis chosen keeps the dropdown open; Escape closes it and hands focus back to its trigger.
  // Take it to the slider after that.
  await user.keyboard('{Escape}');
  await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
  await act(async () => {});
  amount().focus();
  await user.keyboard('{Home}');
  expect(resolveViewSettings(current).clip.enabled).toBe(false);
  expect(resolveViewSettings(current).clip.invert).toBe(false);
});

it('Explode and Clip report their value at their step\'s precision, never float noise', () => {
  // 0.28 × 100 is 28.000000000000004, and 1 − 0.7 is 0.30000000000000004: a screen reader would read both.
  render(<ExplodeControls viewSettings={{ exploded: { enabled: true, amount: 0.28 } }} onViewSettingsPatch={() => {}} />);
  expect(screen.getByRole('slider', { name: 'Explode amount' }).getAttribute('aria-valuenow')).toBe('28');
  cleanup();
  render(<CrossSectionControls viewSettings={{ clip: { enabled: true, axis: 'x', at: 70, invert: false, partColors: true } }}
    onViewSettingsPatch={() => {}} bounds={{ min: [0, 0, 0], max: [100, 100, 100] }} />);
  expect(screen.getByRole('slider', { name: 'Clip amount' }).getAttribute('aria-valuenow')).toBe('30');
});

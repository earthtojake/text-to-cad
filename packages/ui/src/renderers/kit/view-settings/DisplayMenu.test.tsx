import React from 'react';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { STEP_PART_VIEW_FEATURES, viewFeaturesForKind } from '@text-to-cad/core/common/viewSettings.js';
import { createViewSettingsStore } from './viewSettingsStore.js';
import DisplayPopover from '../../../../dist/renderers/kit/shell/DisplayPopover.js';
import { DISPLAY_MODE_OPTIONS } from '../../../../dist/renderers/kit/view-settings/DisplayModeOptions.js';

Object.assign(globalThis, { React });
beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
let store: ReturnType<typeof createViewSettingsStore>;
// The Display tile as the shell wires it (`useRendererShell`): the modes the file offers, and the Grid switch.
function Harness({ features }: { features?: any }) {
  [store] = React.useState(() => createViewSettingsStore({ camera: { focalLength: 80 }, clip: { enabled: true, at: 4 } }));
  React.useLayoutEffect(() => { if (features) store.configure({ features }); }, [features]);
  const { scene } = React.useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const offered = features?.modes ?? DISPLAY_MODE_OPTIONS.map((option: any) => option.value);
  return <><button>Outside</button><DisplayPopover
    mode={{ value: scene.view.mode, options: DISPLAY_MODE_OPTIONS.filter((option: any) => offered.includes(option.value)), onChange: store.selectMode }}
    grid={{ value: scene.view.grid.enabled, onChange: store.setGrid }} /></>;
}
const trigger = () => screen.getByRole('button', { name: /^Display mode:/ });
// The menu's accessible name is its tile's ("Display mode: Solid"); its own label is Display.
const menu = () => document.querySelector<HTMLElement>('[role=menu][aria-label="Display"]')!;
const shown = () => document.querySelector('[role=menu][aria-label="Display"]');

it("is one simple list: the modes, a rule, then the Grid switch, and nothing else to set", async () => {
  const user = userEvent.setup({ skipHover: true });
  render(<Harness />);
  await user.click(trigger());
  const root = menu();
  const modes = within(root).getAllByRole('menuitemradio');
  expect(modes.map(item => item.textContent)).toEqual(['Solid', 'Shaded', 'Parts', 'X-ray', 'Hidden line', 'Wireframe']);
  expect(within(root).getByRole('group', { name: 'Display mode' })).toBeTruthy();
  expect(within(root).getByRole('menuitemradio', { name: 'Solid', checked: true })).toBeTruthy();
  // Each mode row carries its sphere; the check is on the right, as every menu row's is.
  for (const item of modes) expect(item.querySelector('svg')).not.toBeNull();
  expect(modes[0].querySelector('span.absolute')!.className).toContain('right-2');
  const separator = within(root).getByRole('separator');
  const grid = within(root).getByRole('menuitemcheckbox', { name: 'Grid' });
  expect(grid.getAttribute('aria-checked')).toBe('false');
  expect(modes.at(-1)!.compareDocumentPosition(separator) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(separator.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  // No settings page: no per-mode settings, no projection (Projection's own tile), nothing else.
  expect(within(root).queryAllByRole('menuitem')).toEqual([]);
  expect(within(root).queryByRole('button')).toBeNull();
  expect(within(root).queryByRole('menuitemradio', { name: 'Perspective' })).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Outside' }));
  await waitFor(() => expect(shown()).toBeNull());
});

it('a mode chosen is the mode on screen and closes the list; Grid switches on and off in any mode, leaving it open', async () => {
  const user = userEvent.setup({ skipHover: true });
  render(<Harness />);
  await user.click(trigger());
  await user.click(screen.getByRole('menuitemradio', { name: 'Parts' }));
  await waitFor(() => expect(shown()).toBeNull());
  expect(store.getSnapshot().display).toEqual({ mode: 'parts', camera: { focalLength: 80 }, clip: { enabled: true, at: 4 } });
  expect(store.getSnapshot().scene.view.surfaces.colorMode).toBe('by-part');
  expect(trigger().getAttribute('aria-label')).toBe('Display mode: Parts');
  expect(trigger().getAttribute('data-display-mode')).toBe('parts');
  for (const mode of ['X-ray', 'Wireframe']) {
    await user.click(trigger());
    await user.click(screen.getByRole('menuitemradio', { name: mode }));
    await waitFor(() => expect(shown()).toBeNull());
  }
  await user.click(trigger());
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Grid' }));
  expect(shown()).not.toBeNull();
  expect(screen.getByRole('menuitemcheckbox', { name: 'Grid' }).getAttribute('aria-checked')).toBe('true');
  expect([store.getSnapshot().display.mode, store.getSnapshot().display.grid, store.getSnapshot().scene.view.grid.enabled]).toEqual(['wireframe', true, true]);
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Grid' }));
  expect([store.getSnapshot().display.grid, store.getSnapshot().scene.view.grid.enabled]).toEqual([undefined, false]);
});

it('lists only the modes the file offers: a part file no Parts; a mesh Solid, and Parts with several parts; Grid always', async () => {
  const user = userEvent.setup({ skipHover: true });
  const listed = async (features: any) => {
    render(<Harness features={features} />);
    await user.click(trigger());
    const items = [...within(menu()).getAllByRole('menuitemradio').map(item => item.textContent),
      ...within(menu()).getAllByRole('menuitemcheckbox').map(item => item.textContent)];
    cleanup();
    return items;
  };
  expect(await listed(STEP_PART_VIEW_FEATURES)).toEqual(['Solid', 'Shaded', 'X-ray', 'Hidden line', 'Wireframe', 'Grid']);
  expect(await listed(viewFeaturesForKind('stl', { parts: 1 }))).toEqual(['Solid', 'Grid']);
  expect(await listed(viewFeaturesForKind('3mf', { parts: 4 }))).toEqual(['Solid', 'Parts', 'Grid']);
});

it('keyboard: the arrows walk the list and Enter chooses', async () => {
  const user = userEvent.setup({ skipHover: true });
  render(<Harness />);
  trigger().focus();
  await user.keyboard('{Enter}');
  await waitFor(() => expect(shown()).not.toBeNull());
  // Opened from the keyboard, the first mode has the focus: one step down is Shaded.
  await waitFor(() => expect(document.activeElement?.textContent).toBe('Solid'));
  await user.keyboard('{ArrowDown}');
  await user.keyboard('{Enter}');
  await waitFor(() => expect(store.getSnapshot().display.mode).toBe('shaded'));
  await waitFor(() => expect(shown()).toBeNull());
});

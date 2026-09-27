import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FloatingToolBar from '../../../../../dist/renderers/kit/tools/FloatingToolBar.js';
import { MeasureModeIcon, MeasureModeMenu, SelectModeIcon, SelectModeMenu } from '../../../../../dist/renderers/step/components/workbench/SelectionModes.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const badges = (root: Element) => [...root.querySelectorAll('svg[data-tool-icon-base]')].map(icon =>
  `${icon.getAttribute('data-tool-icon-base')}:${icon.querySelector('[data-tool-icon-badge]')?.getAttribute('data-tool-icon-badge') ?? ''}`);
const menu = () => document.querySelector('[role=menu]')!;
const glyphs = (root: Element) => [...root.querySelectorAll('svg[data-mode-glyph]')].map(icon => icon.getAttribute('data-mode-glyph'));

it('Select\'s mode is one button showing the mode in hand; its menu lists the modes (Parts only in an assembly), then only the options that apply', async () => {
  const user = userEvent.setup();
  const modeChange = vi.fn(), connectedChange = vi.fn();
  const view = render(<SelectModeMenu mode="faces" assembly={false} onModeChange={modeChange}
    connected={{ edgeChain: true, tangentFaces: true }} onConnectedChange={connectedChange} />);
  const button = screen.getByRole('button', { name: 'Select mode: Faces' });
  // The button is the panel header's sliders icon; the strip shows the mode.
  expect([glyphs(button), !!button.querySelector('svg.lucide-sliders-horizontal')]).toEqual([[], true]);
  await user.click(button);
  expect(menu().getAttribute('aria-label')).toBe('Select mode');
  expect(screen.getAllByRole('menuitemradio').map(item => [item.textContent, item.getAttribute('aria-checked')]))
    .toEqual([['All', 'false'], ['Faces', 'true'], ['Edges', 'false']]);
  // Each row its mode's own glyph at full size (All: the pointer); no composite in a menu.
  expect(glyphs(menu())).toEqual(['select', 'faces', 'edges']);
  expect(badges(document.body)).toEqual([]);
  // Faces grows by tangency only: Group edges does nothing here, so it is not offered.
  expect(screen.getAllByRole('menuitemcheckbox').map(item => item.textContent)).toEqual(['Group faces']);
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Group faces' }));
  expect(connectedChange).toHaveBeenCalledWith('tangentFaces', false);
  expect(screen.getByRole('menu')).toBeTruthy();
  await user.click(screen.getByRole('menuitemradio', { name: 'Edges' }));
  expect(modeChange).toHaveBeenCalledWith('edges');
  expect(screen.queryByRole('menu')).toBeNull();
  view.rerender(<SelectModeMenu mode="all" assembly onModeChange={modeChange}
    connected={{ edgeChain: true, tangentFaces: false }} onConnectedChange={connectedChange} />);
  await user.click(screen.getByRole('button', { name: 'Select mode: All' }));
  expect(screen.getAllByRole('menuitemradio').map(item => item.textContent)).toEqual(['All', 'Parts', 'Faces', 'Edges']);
  expect(screen.getAllByRole('menuitemcheckbox').map(item => [item.textContent, item.getAttribute('aria-checked')]))
    .toEqual([['Group edges', 'true'], ['Group faces', 'false']]);
  await user.keyboard('{Escape}');
  view.rerender(<SelectModeMenu mode="parts" assembly onModeChange={modeChange}
    connected={{ edgeChain: true, tangentFaces: true }} onConnectedChange={connectedChange} />);
  await user.click(screen.getByRole('button', { name: 'Select mode: Parts' }));
  expect(screen.queryAllByRole('menuitemcheckbox')).toEqual([]);
  expect(menu().querySelector('[role=separator]')).toBeNull();
});

it('Measure\'s snapping is one button showing the mode in hand; its menu is four plain rows, each its glyph at full size', async () => {
  const user = userEvent.setup();
  const changed = vi.fn();
  render(<MeasureModeMenu mode="edges" onModeChange={changed} />);
  await user.click(screen.getByRole('button', { name: 'Measure snapping: Edges' }));
  expect(screen.getAllByRole('menuitemradio').map(item => item.textContent)).toEqual(['All', 'Points', 'Edges', 'Faces']);
  expect(glyphs(menu())).toEqual(['measure', 'points', 'edges', 'faces']);
  expect(menu().querySelector('[data-slot=dropdown-menu-label], [role=separator]')).toBeNull();
  await user.click(screen.getByRole('menuitemradio', { name: 'Points' }));
  expect(changed).toHaveBeenCalledWith('points');
});

it('the strip shows each tool\'s mode as its glyph badged with the mode, and opens no menu', async () => {
  const user = userEvent.setup();
  const select = vi.fn();
  render(<FloatingToolBar tools={[
    { id: 'select', label: 'Select', active: true, icon: <SelectModeIcon mode="parts" aria-hidden="true" />, onSelect: select },
    { id: 'measure', label: 'Measure', active: false, icon: <MeasureModeIcon mode="edges" aria-hidden="true" />, onSelect: () => {} }]} />);
  const button = screen.getByRole('button', { name: 'Select', exact: true });
  expect(button.querySelector('[data-select-mode]')?.getAttribute('data-select-mode')).toBe('parts');
  expect(screen.getByRole('button', { name: 'Measure', exact: true }).querySelector('[data-measure-mode]')?.getAttribute('data-measure-mode')).toBe('edges');
  expect(badges(document.body)).toEqual(['select:parts', 'measure:edges']);
  await user.click(button);
  expect(select).toHaveBeenCalledOnce();
  expect(screen.queryByRole('menu')).toBeNull();
  cleanup();
  render(<SelectModeIcon mode="nonsense" />);
  expect(badges(document.body)).toEqual(['select:']);
});

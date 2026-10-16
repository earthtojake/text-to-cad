import React from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { BOARD_DISPLAY_DEFAULTS, BoardDisplaySection, readBoardDisplay } from '../../../../dist/renderers/plot/board/BoardDisplay.js';
import BOARD from '../__fixtures__/board.plot.json';

Object.assign(globalThis, { React });
afterEach(cleanup);

// The Display's two sections over the committed board (two copper layers, no inner): what each
// control writes, and how the Mode reads it back. The contract itself is core's (`plot2d/boardDisplay.test.js`).
const SHEET = BOARD.sheets[0];
function mount(display = readBoardDisplay(null)) {
  const onChange = vi.fn();
  render(<BoardDisplaySection display={display} onChange={onChange} sheet={SHEET} />);
  return onChange;
}
const checkbox = (name: string) => screen.getByRole('checkbox', { name }) as HTMLInputElement;

it('lists a checkbox per layer of the payload in its groups, ticked as the mode draws them', () => {
  mount();
  const groups = screen.getAllByRole('group').map((group) => [group.getAttribute('aria-label'), within(group).getAllByRole('checkbox').map((box) => box.closest('label')!.textContent)]);
  expect(groups).toEqual([
    ['Front layers', ['F.CrtYd', 'F.Fab', 'F.SilkS', 'F.Paste', 'F.Mask', 'F.Cu']],
    ['Back layers', ['B.Cu', 'B.Mask']],
    ['Other layers', ['Edge.Cuts', 'Vias', 'Ratsnest', 'Drills']],
  ]);
  // Board: every layer but the courtyard.
  expect(checkbox('F.CrtYd').checked).toBe(false);
  for (const name of ['F.Cu', 'F.Mask', 'F.Paste', 'F.SilkS', 'F.Fab', 'B.Cu', 'B.Mask', 'Edge.Cuts', 'Vias', 'Ratsnest', 'Drills']) expect(checkbox(name).checked, name).toBe(true);
  expect(screen.getByRole('combobox', { name: 'Mode' }).textContent).toContain('Board');
  expect(checkbox('Copper pours').checked).toBe(true);
  expect(screen.queryByRole('button', { name: 'Reset board display' })).toBeNull();
});

it('a checkbox writes the mode\'s set with that layer changed; a set changed from its mode reads as Custom, with Reset', () => {
  const onChange = mount();
  fireEvent.click(checkbox('F.SilkS'));
  expect(onChange).toHaveBeenLastCalledWith({ ...BOARD_DISPLAY_DEFAULTS, layers: ['B.Mask', 'B.Cu', 'F.Cu', 'F.Mask', 'F.Paste', 'F.Fab', 'Edge.Cuts', 'vias', 'ratsnest', 'drills'] });
  cleanup();
  const custom = mount(readBoardDisplay(onChange.mock.lastCall![0]));
  expect(checkbox('F.SilkS').checked).toBe(false);
  expect(screen.getByRole('combobox', { name: 'Mode' }).textContent).toContain('Custom');
  expect(screen.getByRole('button', { name: 'Reset board display' })).not.toBeNull();
  // Ticked back, the set is the mode's again.
  fireEvent.click(checkbox('F.SilkS'));
  expect(custom).toHaveBeenLastCalledWith({ ...BOARD_DISPLAY_DEFAULTS, layers: null });
  fireEvent.click(screen.getByRole('button', { name: 'Reset board display' }));
  expect(custom).toHaveBeenLastCalledWith(BOARD_DISPLAY_DEFAULTS);
});

it('Copper pours is a choice while a copper layer is drawn, and goes when none is', () => {
  const onChange = mount();
  fireEvent.click(checkbox('Copper pours'));
  expect(onChange).toHaveBeenLastCalledWith({ ...BOARD_DISPLAY_DEFAULTS, poured: false });
  cleanup();
  mount({ ...BOARD_DISPLAY_DEFAULTS, mode: 'assembly' });
  expect(screen.queryByRole('checkbox', { name: 'Copper pours' })).toBeNull();
  cleanup();
  // Assembly with F.Cu ticked draws copper: the pours are a choice again.
  mount({ ...BOARD_DISPLAY_DEFAULTS, mode: 'assembly', layers: ['F.Cu', 'Edge.Cuts'] });
  expect(checkbox('Copper pours').checked).toBe(true);
  expect(checkbox('F.Cu').checked).toBe(true);
  expect(checkbox('F.SilkS').checked).toBe(false);
});

it('View from writes the side alone, which no mode owns', () => {
  const onChange = mount({ ...BOARD_DISPLAY_DEFAULTS, mode: 'copper', layers: ['F.Cu'] });
  fireEvent.keyDown(screen.getByRole('combobox', { name: 'View from' }), { key: 'ArrowDown' });
  fireEvent.click(screen.getByRole('option', { name: 'Bottom' }));
  expect(onChange).toHaveBeenLastCalledWith({ ...BOARD_DISPLAY_DEFAULTS, mode: 'copper', layers: ['F.Cu'], side: 'bottom' });
});

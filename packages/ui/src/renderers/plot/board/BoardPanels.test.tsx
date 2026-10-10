import React from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createBoardIndex } from '@text-to-cad/core/lib/board2d/boardIndex.js';
import { BoardReferencePanel, BoardTreePanel } from '../../../../dist/renderers/plot/board/BoardPanels.js';

Object.assign(globalThis, { React });
afterEach(cleanup);

// One resistor across two nets: enough for a part row, a net row and the pads under them.
const square = (cx: number, cy: number, w: number, h: number) => [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]];
const index = createBoardIndex({
  origin: [5, 25], nets: [{ name: 'VIN', class: '' }, { name: 'GND', class: '' }],
  parts: [{ ref: 'R1', value: '10k', footprint: 'R_0603', side: 'top', at: [15, 20], rotation: 0, fields: {}, outline: square(15, 20, 3, 1.4) }],
  pads: [
    { part: 'R1', number: '1', name: '', net: 'VIN', type: 'passive', side: 'top', at: [14.175, 20], polygon: square(14.175, 20, 0.8, 0.95) },
    { part: 'R1', number: '2', name: '', net: 'GND', type: 'passive', side: 'top', at: [15.825, 20], polygon: square(15.825, 20, 0.8, 0.95) },
  ],
  tracks: [], vias: [], zones: [], holes: [], outline: [], findings: [],
}, { x: 0, y: 0 });

function tree(props: Record<string, unknown> = {}) {
  const spies = { select: vi.fn(), hover: vi.fn(), onIsolate: vi.fn(), clear: vi.fn() };
  const element = (extra: Record<string, unknown>) => <BoardTreePanel index={index} documentKind="board" selection={[]} selectMode="all" onSelectMode={() => {}} active {...spies} {...props} {...extra} />;
  const view = render(element({}));
  return { spies, rerender: (extra: Record<string, unknown>) => view.rerender(element(extra)) };
}
const open = (label: string) => fireEvent.click(screen.getByRole('button', { name: `Expand ${label}` }));

it('a tree row under the pointer, or in keyboard focus, lights what it names on the canvas; a group names nothing', () => {
  const { spies } = tree();
  open('Resistors');
  const row = screen.getByRole('button', { name: 'Select R1' });
  fireEvent.mouseEnter(row.parentElement!);
  expect(spies.hover).toHaveBeenLastCalledWith('#R1');
  fireEvent.mouseLeave(row.parentElement!);
  expect(spies.hover).toHaveBeenLastCalledWith(null);
  fireEvent.focus(row);
  expect(spies.hover).toHaveBeenLastCalledWith('#R1');
  fireEvent.mouseEnter(screen.getByRole('button', { name: 'Resistors' }).parentElement!);
  expect(spies.hover).toHaveBeenLastCalledWith(null);
  expect(spies.select).not.toHaveBeenCalled();
});

it('a part’s and a net’s eye isolate it without selecting it; a pad has none; an isolated row keeps its eye lit', () => {
  const { spies, rerender } = tree();
  open('Resistors'); open('R1'); open('Nets');
  expect(screen.queryByRole('button', { name: 'Isolate 1' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Isolate R1' }));
  expect(spies.onIsolate).toHaveBeenLastCalledWith('#R1');
  fireEvent.click(screen.getByRole('button', { name: 'Isolate VIN' }));
  expect(spies.onIsolate).toHaveBeenLastCalledWith('#net:VIN');
  expect(spies.select).not.toHaveBeenCalled();
  // The memoised rows draw again for what changed: the isolated row's eye is lit and pressed.
  rerender({ isolated: ['#net:VIN'] });
  expect(screen.getByRole('button', { name: 'Exit isolate VIN' }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('button', { name: 'Isolate R1' }).getAttribute('aria-pressed')).toBe('false');
});

it('the Reference’s rows that name other things select them: a pad’s net and part, a net’s parts', () => {
  const onSelect = vi.fn();
  const { rerender } = render(<BoardReferencePanel index={index} resolved={[index.resolve('#R1.1')]} finding={null} active onClear={() => {}} onSelect={onSelect} onCopy={() => {}} />);
  const reference = () => within(document.querySelector('[data-board-reference]') as HTMLElement);
  fireEvent.click(reference().getByRole('button', { name: 'VIN' }));
  expect(onSelect).toHaveBeenLastCalledWith(['#net:VIN']);
  fireEvent.click(reference().getByRole('button', { name: 'R1 · 10k' }));
  expect(onSelect).toHaveBeenLastCalledWith(['#R1']);
  rerender(<BoardReferencePanel index={index} resolved={[index.resolve('#net:GND')]} finding={null} active onClear={() => {}} onSelect={onSelect} onCopy={() => {}} />);
  fireEvent.click(reference().getByRole('button', { name: 'R1' }));
  expect(onSelect).toHaveBeenLastCalledWith(['#R1']);
  // The ID is words: the selection's own reference goes nowhere.
  expect(reference().queryByRole('button', { name: '#net:GND' })).toBeNull();
});

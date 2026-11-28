import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { SegmentedControl } from './segmented-control.jsx';
Object.assign(globalThis, { React });
afterEach(cleanup);

const Icon = (props: object) => <svg {...props} />;
const OPTIONS = [{ value: 'grid', label: 'Grid', Icon }, { value: 'list', label: 'List', Icon }, { value: 'table', label: 'Table' }];

// A host that keeps the choice, and every choice it was handed.
function Kept({ chosen }: { chosen: string[] }) {
  const [value, setValue] = useState('grid');
  return <SegmentedControl label="Layout" value={value} options={OPTIONS} onChange={(next: string) => { chosen.push(next); setValue(next); }} />;
}
const state = () => screen.getAllByRole('button').map(button => [button.getAttribute('aria-label') ?? button.textContent, button.getAttribute('aria-pressed'), button.tabIndex]);

it('is a labelled group of toggles, the chosen one pressed and the one Tab stop; pressing the chosen one changes nothing', () => {
  const chosen: string[] = [];
  render(<Kept chosen={chosen} />);
  const group = screen.getByRole('group', { name: 'Layout' });
  expect(group.hasAttribute('data-segmented-control')).toBe(true);
  // An icon option is named by its label; a worded one by its word.
  expect(state()).toEqual([['Grid', 'true', 0], ['List', 'false', -1], ['Table', 'false', -1]]);
  fireEvent.click(screen.getByRole('button', { name: 'Grid' }));
  expect(chosen).toEqual([]);
  fireEvent.click(screen.getByRole('button', { name: 'List' }));
  expect([chosen, state()]).toEqual([['list'], [['Grid', 'false', -1], ['List', 'true', 0], ['Table', 'false', -1]]]);
});

it('chooses the neighbour with ← and →, wrapping, and the ends with Home and End, the focus going with the choice', () => {
  const chosen: string[] = [];
  render(<Kept chosen={chosen} />);
  const grid = screen.getByRole('button', { name: 'Grid' });
  grid.focus();
  fireEvent.keyDown(grid, { key: 'ArrowLeft' });
  expect([chosen.at(-1), document.activeElement?.textContent]).toEqual(['table', 'Table']);
  fireEvent.keyDown(document.activeElement!, { key: 'ArrowRight' });
  expect([chosen.at(-1), document.activeElement?.getAttribute('aria-label')]).toEqual(['grid', 'Grid']);
  fireEvent.keyDown(document.activeElement!, { key: 'End' });
  fireEvent.keyDown(document.activeElement!, { key: 'Home' });
  expect(chosen).toEqual(['table', 'grid', 'table', 'grid']);
  // Another key is the button's own.
  fireEvent.keyDown(document.activeElement!, { key: 'ArrowDown' });
  expect(chosen).toHaveLength(4);
});

it('is the control tall at either scale, its faces 2px in on a track whose corners are a face\'s + 2', () => {
  render(<Kept chosen={[]} />);
  const group = screen.getByRole('group', { name: 'Layout' });
  expect(group.className).toContain('rounded-[calc(var(--cad-radius-control)+2px)]');
  for (const button of screen.getAllByRole('button')) {
    expect([button.className.includes('h-control'), button.className.includes('p-0.5'), button.firstElementChild!.className.includes('rounded-control')])
      .toEqual([true, true, true]);
  }
  // An icon option is the control + 4 wide, its glyph the glyph token.
  expect(screen.getByRole('button', { name: 'Grid' }).className).toContain('w-[calc(var(--cad-control)+4px)]');
  expect(screen.getByRole('button', { name: 'Grid' }).firstElementChild!.className).toContain('[&_svg]:size-glyph');
});

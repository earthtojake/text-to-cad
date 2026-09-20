import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import MeasurePanel from '../../../../../dist/renderers/cad/components/workbench/MeasurePanel.js';

afterEach(cleanup);
const measurement = (id: string, distance: number, colorIndex: number) => ({ id, colorIndex,
  measurement: { euclidean: distance, delta: [distance, 0, 0], unit: 'mm' }, pickA: { snapKind: 'vertex' }, pickB: { snapKind: 'edge' } });

it('does not exist until something has been measured', () => {
  const view = render(<MeasurePanel measurements={[]} />);
  expect(view.container.innerHTML).toBe('');
});

it('adds one dense row per measurement, which can be activated or deleted; two or more can be cleared together', () => {
  const onActivate = vi.fn(), onDelete = vi.fn(), onClear = vi.fn();
  const props = { activeId: 'b', onActivate, onDelete, onClear };
  const view = render(<MeasurePanel {...props} measurements={[measurement('a', 21.38, 0)]} />);
  expect(screen.getByRole('region', { name: 'Measurements' })).toBeTruthy();
  expect(screen.getAllByRole('listitem')).toHaveLength(1);
  expect(screen.queryByRole('button', { name: 'Clear all' })).toBeNull();

  view.rerender(<MeasurePanel {...props} measurements={[measurement('a', 21.38, 0), measurement('b', 119.5, 1)]} />);
  const rows = screen.getAllByRole('listitem');
  expect(rows.map(row => row.className.includes('h-6'))).toEqual([true, true]);
  expect(rows[0].textContent).toContain('21.38');
  expect(rows[1].className).toContain('bg-sidebar-accent');
  // Everything the old two-line row showed is still one hover away.
  expect(rows[0].getAttribute('title')).toMatch(/21\.38.*→/);
  fireEvent.click(rows[0]);
  expect(onActivate).toHaveBeenCalledWith('a');
  fireEvent.click(screen.getByRole('button', { name: 'Delete measurement 2' }));
  expect(onDelete).toHaveBeenCalledWith('b');
  expect(onActivate).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: 'Clear all' }));
  expect(onClear).toHaveBeenCalledTimes(1);
  // No snap filter, title, close button or footer: those are the Measure button's business.
  expect(screen.queryByRole('button', { name: /Snap to|Finish measuring|Close/ })).toBeNull();
});

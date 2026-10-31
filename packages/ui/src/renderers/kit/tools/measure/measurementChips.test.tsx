import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { MeasurementsBar } from '../../../../../dist/renderers/kit/tools/measure/measurementChips.js';

afterEach(cleanup);

const item = (id: string, euclidean: number) => ({ id, colorIndex: 0, pickA: { point: [0, 0, 0], snapKind: 'vertex' }, pickB: { point: [euclidean, 0, 0], snapKind: 'vertex' },
  measurement: { euclidean, delta: [euclidean, 0, 0], unit: 'mm' } });

it("Measure's row lists its measurements as chips, each with its card and its X, then Clear; and is not there while nothing is measured", () => {
  const onDelete = vi.fn(), hover = vi.fn(), clear = vi.fn();
  const session = (measurements: object[]) => ({ measurements, onDelete, hover, clear }) as any;
  const view = render(<MeasurementsBar measure={session([])} />);
  expect(view.container.querySelector('[data-cad-sub-toolbar]')).toBeNull();
  view.rerender(<MeasurementsBar measure={session([item('m1', 5), item('m2', 12)])} />);
  const row = screen.getByRole('toolbar', { name: 'Measurements' });
  expect([...row.querySelectorAll('[data-quick-edit-ref]')].map(chip => chip.getAttribute('data-quick-edit-ref'))).toEqual(['measure-m1', 'measure-m2']);
  const chip = screen.getByRole('button', { name: 'Measurement 1: 5.00 mm' });
  fireEvent.pointerDown(chip, { pointerType: 'touch' });
  fireEvent.click(chip);
  expect(document.querySelector('[data-quick-edit-ref-card="measure-m1"]')!.textContent).toContain('Distance5.00 mm');
  fireEvent.click(screen.getByRole('button', { name: 'Remove Measurement 2: 12.00 mm' }));
  expect(onDelete).toHaveBeenCalledWith('m2');
  fireEvent.click(screen.getByRole('button', { name: 'Clear measurements' }));
  expect(clear).toHaveBeenCalledOnce();
});

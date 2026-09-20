import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { ZoomControl } from '../../../../dist/renderers/kit/camera/ZoomControl.js';

afterEach(cleanup);
it('uses the small live readout to open scoped camera and model actions', async () => {
  const user = userEvent.setup();
  const change=vi.fn(), reset=vi.fn(), model=vi.fn(), fit=vi.fn(), selection=vi.fn();
  const props = { zoomPercent: 125, onZoomPercentChange: change, onZoomReset: reset,
    onModelReset: model, onZoomFit: fit, onZoomSelection: selection };
  const { rerender } = render(<ZoomControl {...props} />);
  expect(screen.getByLabelText('Zoom level percent').textContent).toBe('125%');
  expect(screen.queryByRole('textbox')).toBeNull();
  const action = async (name: string) => {
    await user.click(screen.getByRole('button', {name:'Zoom controls'}));
    await user.click(screen.getByRole('menuitem', {name, exact:true}));
  };
  await action('Zoom out'); await action('Zoom in'); await action('Zoom to 100%');
  expect(change.mock.calls.map(([value])=>value)).toEqual([115,135,100]);
  await action('Zoom to fit'); expect(fit).toHaveBeenCalledOnce();
  await action('Reset camera'); expect(reset).toHaveBeenCalledOnce(); expect(model).not.toHaveBeenCalled();
  await action('Reset model'); expect(model).toHaveBeenCalledOnce();
  await user.click(screen.getByRole('button', {name:'Zoom controls'}));
  expect(screen.getByRole('menuitem', {name:'Zoom to selection'}).getAttribute('aria-disabled')).toBe('true');
  await user.keyboard('{Escape}');
  rerender(<ZoomControl {...props} zoomPercent={143.7} selectionAvailable />);
  expect(screen.getByLabelText('Zoom level percent').textContent).toBe('144%');
  await action('Zoom to selection'); expect(selection).toHaveBeenCalledOnce();
});

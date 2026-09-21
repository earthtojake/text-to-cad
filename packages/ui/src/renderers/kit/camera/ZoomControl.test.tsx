import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { ZoomControl } from '../../../../dist/renderers/kit/camera/ZoomControl.js';

afterEach(cleanup);
it('uses the small live readout to open the camera actions, framing among them', async () => {
  const user = userEvent.setup();
  const change=vi.fn(), resetZoom=vi.fn(), fit=vi.fn(), selection=vi.fn();
  const props = { zoomPercent: 125, onZoomPercentChange: change, onResetZoom: resetZoom,
    onZoomFit: fit, onZoomSelection: selection };
  const { rerender } = render(<ZoomControl {...props} />);
  expect(screen.getByLabelText('Zoom level percent').textContent).toBe('125%');
  expect(screen.queryByRole('textbox')).toBeNull();
  const open = () => user.click(screen.getByRole('button', {name:'Zoom controls'}));
  const action = async (name: string) => {
    await open();
    await user.click(screen.getByRole('menuitem', {name, exact:true}));
  };
  // Every item, in order: framing is ONE act named "Reset Zoom", and the menu
  // holds nothing about the model, its motion or its display settings.
  await open();
  expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual([
    'Zoom in', 'Zoom out', 'Zoom to 100%', 'Zoom to fit', 'Zoom to selection', 'Reset Zoom'
  ]);
  await user.keyboard('{Escape}');
  await action('Zoom out'); await action('Zoom in'); await action('Zoom to 100%');
  expect(change.mock.calls.map(([value])=>value)).toEqual([115,135,100]);
  await action('Zoom to fit'); expect(fit).toHaveBeenCalledOnce();
  // "Zoom to 100%" is the zoom number; "Reset Zoom" re-frames the model. Two items, two callbacks.
  await action('Reset Zoom'); expect(resetZoom).toHaveBeenCalledOnce();
  expect(change.mock.calls.length).toBe(3);
  await open();
  expect(screen.getByRole('menuitem', {name:'Zoom to selection'}).getAttribute('aria-disabled')).toBe('true');
  await user.keyboard('{Escape}');
  rerender(<ZoomControl {...props} zoomPercent={143.7} selectionAvailable />);
  expect(screen.getByLabelText('Zoom level percent').textContent).toBe('144%');
  await action('Zoom to selection'); expect(selection).toHaveBeenCalledOnce();
});

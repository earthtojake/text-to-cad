import React from 'react';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import ZoomControl, { ZOOM_FACTOR } from '../../../../dist/renderers/kit/shell/ZoomControl.js';

// The menu's positioning measures what it is anchored to: jsdom has no observer of its own.
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any;
afterEach(cleanup);

it('the zoom is its percentage, redrawn as the view says it moved, and its menu steps, fits and frames the selection', async () => {
  const user = userEvent.setup();
  let percent = 100;
  const listeners = new Set<() => void>();
  const zoom = {
    read: () => percent,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
    zoomBy: vi.fn(), fit: vi.fn(), zoomTo100: vi.fn(), zoomToSelection: vi.fn(), selectionAvailable: false
  };
  const view = render(<ZoomControl zoom={zoom} />);
  const button = screen.getByRole('button', { name: 'Zoom 100%' });
  expect(button.textContent).toBe('100%');
  // The view moved: the number follows, a frame later, whole and grouped.
  percent = 1249.6;
  act(() => { for (const listener of listeners) listener(); });
  await waitFor(() => expect(button.textContent).toBe('1,250%'));
  await user.click(button);
  const items = await screen.findAllByRole('menuitem');
  expect(items.map(item => [item.textContent, item.hasAttribute('data-disabled')])).toEqual([
    ['Zoom inCtrl+=', false], ['Zoom outCtrl+-', false], ['Zoom to 100%⇧0', false], ['Zoom to fitF', false], ['Zoom to selection⇧2', true]
  ]);
  await user.click(screen.getByRole('menuitem', { name: /Zoom in/ }));
  expect(zoom.zoomBy).toHaveBeenCalledWith(ZOOM_FACTOR);
  await user.click(button);
  await user.click(await screen.findByRole('menuitem', { name: /Zoom to 100%/ }));
  expect(zoom.zoomTo100).toHaveBeenCalledTimes(1);
  await user.click(button);
  await user.click(await screen.findByRole('menuitem', { name: /Zoom to fit/ }));
  expect(zoom.fit).toHaveBeenCalledTimes(1);
  // With something picked, Zoom to selection frames it.
  view.rerender(<ZoomControl zoom={{ ...zoom, selectionAvailable: true }} />);
  await user.click(button);
  await user.click(await screen.findByRole('menuitem', { name: /Zoom to selection/ }));
  expect(zoom.zoomToSelection).toHaveBeenCalledTimes(1);
  view.unmount();
  expect(listeners.size).toBe(0);
});

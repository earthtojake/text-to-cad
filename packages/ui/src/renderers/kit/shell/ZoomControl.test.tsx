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

// A host that anchors the cube at the bottom-left (`--cad-viewport-corner-left`, Codex's views) moves every
// corner control there, as one group, the bottom row reading from the corner outwards.
it('every corner control follows the corner the host anchors the cube at', async () => {
  const { ViewCornerRow, ViewCornerSideProvider, ViewCubeColumn, viewCornerSide } = await import('../../../../dist/renderers/kit/shell/ViewCorner.js');
  const zoom = { read: () => 100, subscribe: () => () => {}, zoomBy: vi.fn(), fit: vi.fn() };
  const corner = (side: string) => {
    const view = render(<ViewCornerSideProvider value={side}>
      <ViewCornerRow><span /></ViewCornerRow>
      <ViewCubeColumn projection={{ value: 'orthographic', onChange: () => {} }} onHome={() => {}} />
      <ZoomControl zoom={zoom} />
    </ViewCornerSideProvider>);
    const style = (selector: string) => (view.container.querySelector(selector) as HTMLElement).style;
    const placed = (selector: string) => [style(selector).left, style(selector).right];
    const column = [...view.container.querySelectorAll('[data-view-corner]')].find(el => !el.hasAttribute('data-view-corner-row')) as HTMLElement;
    const result = { pill: placed('[data-zoom-pill]'), row: placed('[data-view-corner-row]'), order: style('[data-view-corner-row]').flexDirection,
      column: [column.style.left, column.style.right] };
    view.unmount();
    return result;
  };
  expect(corner('right')).toEqual({ pill: ['', 'calc(var(--cad-viewport-corner-right, -6px) + 14px)'],
    row: ['', 'calc(var(--cad-viewport-corner-right, -6px) + 132px)'], order: 'row', column: ['', 'calc(var(--cad-viewport-corner-right, -6px) + 20px)'] });
  expect(corner('left')).toEqual({ pill: ['calc(var(--cad-viewport-corner-left, 0px) + 14px)', 'auto'],
    row: ['calc(var(--cad-viewport-corner-left, 0px) + 132px)', 'auto'], order: 'row-reverse', column: ['calc(var(--cad-viewport-corner-left, 0px) + 20px)', 'auto'] });
  const host = document.body.appendChild(document.createElement('div'));
  expect(viewCornerSide(host)).toBe('right');
  host.style.setProperty('--cad-viewport-corner-left', '2px');
  expect(viewCornerSide(host)).toBe('left');
  host.remove();
});

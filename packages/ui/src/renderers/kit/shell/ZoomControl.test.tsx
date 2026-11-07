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

// A host that anchors the cube at the bottom-left (`--cad-viewport-corner-left`) moves every
// corner control there, as one group: each column flush with its anchor's outer edge, the pill's a gap over it.
it('every corner control follows the corner the host anchors the cube at', async () => {
  const { ViewCornerSideProvider, ViewCubeColumn, ViewPillColumn, viewCornerSide } = await import('../../../../dist/renderers/kit/shell/ViewCorner.js');
  const zoom = { read: () => 100, subscribe: () => () => {}, zoomBy: vi.fn(), fit: vi.fn() };
  const corner = (side: string) => {
    const view = render(<ViewCornerSideProvider value={side}>
      <ViewPillColumn><span /></ViewPillColumn>
      <ViewCubeColumn projection={{ value: 'orthographic', onChange: () => {} }} onHome={() => {}} />
      <ZoomControl zoom={zoom} />
    </ViewCornerSideProvider>);
    const element = (selector: string) => view.container.querySelector(selector) as HTMLElement;
    const placed = (selector: string) => [element(selector).style.left, element(selector).style.right, element(selector).style.bottom];
    const cube = [...view.container.querySelectorAll('[data-view-corner]')].find(el => !el.hasAttribute('data-view-pill-column')) as HTMLElement;
    const result = { pill: placed('[data-zoom-pill]'), pillColumn: placed('[data-view-pill-column]'),
      aligned: element('[data-view-pill-column]').classList.contains(side === 'left' ? 'items-start' : 'items-end'),
      cubeColumn: [cube.style.left, cube.style.right] };
    view.unmount();
    return result;
  };
  const bottom = 'calc(8px + var(--cad-viewport-corner-bottom, 0px))';
  // The pill 8px off the bottom, its 24px, then the corner's 4px gap.
  const over = 'calc(36px + var(--cad-viewport-corner-bottom, 0px))';
  expect(corner('right')).toEqual({ pill: ['', 'calc(var(--cad-viewport-corner-right, -6px) + 14px)', bottom],
    pillColumn: ['', 'calc(var(--cad-viewport-corner-right, -6px) + 14px)', over], aligned: true,
    cubeColumn: ['', 'calc(var(--cad-viewport-corner-right, -6px) + 20px)'] });
  expect(corner('left')).toEqual({ pill: ['calc(var(--cad-viewport-corner-left, 0px) + 14px)', 'auto', bottom],
    pillColumn: ['calc(var(--cad-viewport-corner-left, 0px) + 14px)', 'auto', over], aligned: true,
    cubeColumn: ['calc(var(--cad-viewport-corner-left, 0px) + 20px)', 'auto'] });
  const host = document.body.appendChild(document.createElement('div'));
  expect(viewCornerSide(host)).toBe('right');
  host.style.setProperty('--cad-viewport-corner-left', '2px');
  expect(viewCornerSide(host)).toBe('left');
  host.remove();
});

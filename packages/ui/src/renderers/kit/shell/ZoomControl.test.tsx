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

// The zoom is ONE control: its percentage and a chevron, no − or +, on a faint resting surface (not the strip's chrome),
// 28px tall; its outer edge the corner's inset (12px) in and its middle on the tool strip's (8px down, 40px tall).
it("the zoom is one dropdown, the percentage and a chevron on a faint surface, centred on the strip's line at the corner's inset", async () => {
  const { FLOATING_CHROME_SURFACE_CLASS } = await import('../../../../dist/lib/floatingSurface.js');
  const zoom = { read: () => 100, subscribe: () => () => {}, zoomBy: vi.fn(), fit: vi.fn() };
  const view = render(<ZoomControl zoom={zoom} />);
  const pill = view.container.querySelector('[data-zoom-pill]') as HTMLElement;
  for (const name of FLOATING_CHROME_SURFACE_CLASS.split(' ')) expect(pill.classList.contains(name), name).toBe(false);
  const button = pill.querySelector<HTMLElement>('[data-zoom-control]')!;
  expect([[...pill.querySelectorAll('button')].map(node => node.getAttribute('aria-label')), Boolean(button.querySelector('.lucide-chevron-down')),
    ['h-control', 'bg-foreground/6'].every(name => button.classList.contains(name))]).toEqual([['Zoom 100%'], true, true]);
  expect([pill.style.right, pill.style.top, pill.style.bottom]).toEqual(['calc(var(--cad-viewport-corner-right, 2px) + 10px)', 'calc(14px + var(--cad-viewport-corner-top, 0px))', '']);
});

// A host that anchors the cube at the top-left (`--cad-viewport-corner-left`) moves the corner there: the pill
// the corner's inset from the left edge.
it('the corner follows the side the host anchors the cube at', async () => {
  const { ViewCornerSideProvider, viewCornerSide } = await import('../../../../dist/renderers/kit/shell/ViewCorner.js');
  const zoom = { read: () => 100, subscribe: () => () => {}, zoomBy: vi.fn(), fit: vi.fn() };
  const corner = (side: string) => {
    const view = render(<ViewCornerSideProvider value={side}>
      <ZoomControl zoom={zoom} />
    </ViewCornerSideProvider>);
    const pill = view.container.querySelector('[data-zoom-pill]') as HTMLElement;
    const placed = [pill.style.left, pill.style.right, pill.style.top];
    view.unmount();
    return placed;
  };
  const pillTop = 'calc(14px + var(--cad-viewport-corner-top, 0px))';
  expect(corner('right')).toEqual(['', 'calc(var(--cad-viewport-corner-right, 2px) + 10px)', pillTop]);
  expect(corner('left')).toEqual(['calc(var(--cad-viewport-corner-left, 0px) + 10px)', 'auto', pillTop]);
  const host = document.body.appendChild(document.createElement('div'));
  expect(viewCornerSide(host)).toBe('right');
  host.style.setProperty('--cad-viewport-corner-left', '2px');
  expect(viewCornerSide(host)).toBe('left');
  host.remove();
});

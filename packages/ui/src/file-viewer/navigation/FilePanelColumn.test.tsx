import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { FilePanelColumn, PANEL_MIN_WIDTH, PANEL_MAX_WIDTH } from '../../../dist/file-viewer/navigation/FilePanelColumn.js';

afterEach(cleanup);
it('resizes any panel down to the minimum by keyboard and stops there: the keyboard never closes it', () => {
  expect(PANEL_MIN_WIDTH).toBe(200);
  for (const id of ['tree', 'source']) {
    const resize = vi.fn(), collapse = vi.fn();
    render(<FilePanelColumn id={id} label={id} width={PANEL_MIN_WIDTH} onWidthChange={resize} onCollapse={collapse}>Content</FilePanelColumn>);
    const handle = screen.getByRole('separator');
    fireEvent.keyDown(handle, { key: 'Home' });
    expect(resize).toHaveBeenLastCalledWith(PANEL_MIN_WIDTH);
    fireEvent.keyDown(handle, { key: 'ArrowRight' });
    expect(resize).toHaveBeenLastCalledWith(PANEL_MIN_WIDTH);
    expect(collapse).not.toHaveBeenCalled();
    fireEvent.keyDown(handle, { key: 'End' });
    expect(resize).toHaveBeenLastCalledWith(PANEL_MAX_WIDTH);
    cleanup();
  }
});
it('a drag past the minimum stops at it, closes only well below it, and a cancelled drag resizes nothing', () => {
  const resize = vi.fn(), collapse = vi.fn();
  const { container } = render(<div><FilePanelColumn id="tree" label="Files" width={320} onWidthChange={resize} onCollapse={collapse}>Content</FilePanelColumn></div>);
  const handle = screen.getByRole('separator');
  handle.setPointerCapture = vi.fn(); handle.hasPointerCapture = () => true; handle.releasePointerCapture = vi.fn();
  container.firstElementChild!.getBoundingClientRect = () => ({ right: 1000 } as DOMRect);
  const pointer = (type: string, x: number) => {
    const event = new Event(type, { bubbles: true });
    Object.assign(event, { button: 0, pointerId: 1, clientX: x });
    fireEvent(handle, event);
  };
  pointer('pointerdown', 680); pointer('pointermove', 700);
  expect(resize).toHaveBeenLastCalledWith(300);
  pointer('pointercancel', 700); pointer('pointermove', 900);
  expect(resize).toHaveBeenCalledTimes(1);
  pointer('pointerdown', 700);
  // Just under the minimum: held at it.
  pointer('pointermove', 1000 - PANEL_MIN_WIDTH + 30);
  expect(resize).toHaveBeenLastCalledWith(PANEL_MIN_WIDTH);
  expect(collapse).not.toHaveBeenCalled();
  // Past half of it: closed.
  pointer('pointermove', 1000 - PANEL_MIN_WIDTH / 2 + 1);
  expect(collapse).toHaveBeenCalledOnce();
  pointer('pointermove', 680);
  expect(resize).toHaveBeenCalledTimes(2);
});

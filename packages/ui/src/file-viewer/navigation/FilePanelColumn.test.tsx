import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { FilePanelColumn, PANEL_MIN_WIDTH, PANEL_MAX_WIDTH } from '../../../dist/file-viewer/navigation/FilePanelColumn.js';

afterEach(cleanup);
it('resizes either panel down to the minimum, then collapses rather than squeezing it', () => {
  for (const id of ['tree', 'cad-file-sheet']) {
    const resize = vi.fn(), collapse = vi.fn();
    render(<FilePanelColumn id={id} label={id} width={PANEL_MIN_WIDTH} onWidthChange={resize} onCollapse={collapse}>Content</FilePanelColumn>);
    const handle = screen.getByRole('separator');
    fireEvent.keyDown(handle, { key: 'Home' });
    expect(resize).toHaveBeenLastCalledWith(PANEL_MIN_WIDTH);
    expect(collapse).not.toHaveBeenCalled();
    fireEvent.keyDown(handle, { key: 'ArrowRight' });
    expect(collapse).toHaveBeenCalledOnce();
    fireEvent.keyDown(handle, { key: 'End' });
    expect(resize).toHaveBeenLastCalledWith(PANEL_MAX_WIDTH);
    cleanup();
  }
});
it('stops resizing after a cancelled drag and collapses on crossing the minimum', () => {
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
  expect(collapse).not.toHaveBeenCalled();
  pointer('pointerdown', 700); pointer('pointermove', 1001 - PANEL_MIN_WIDTH);
  expect(collapse).toHaveBeenCalledOnce();
  pointer('pointermove', 680);
  expect(resize).toHaveBeenCalledTimes(1);
});

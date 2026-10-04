import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { FilePanelColumn, PANEL_MIN_WIDTH, PANEL_MAX_WIDTH, filePanelName } from '../../../dist/file-viewer/navigation/FilePanelColumn.js';

afterEach(cleanup);
const pointer = (handle: HTMLElement, type: string, x: number) => {
  const event = new Event(type, { bubbles: true });
  Object.assign(event, { button: 0, pointerId: 1, clientX: x });
  fireEvent(handle, event);
};
const capture = (handle: HTMLElement) => { handle.setPointerCapture = vi.fn(); handle.hasPointerCapture = () => true; handle.releasePointerCapture = vi.fn(); };

it('resizes a panel down to the minimum by keyboard and stops there: the keyboard never closes it', () => {
  expect(PANEL_MIN_WIDTH).toBe(140);
  const resize = vi.fn(), collapse = vi.fn();
  render(<FilePanelColumn id="source" label="Source" width={PANEL_MIN_WIDTH} onWidthChange={resize} onCollapse={collapse}>Content</FilePanelColumn>);
  // The column's handle is its left edge, so ArrowLeft widens it.
  const handle = screen.getByRole('separator');
  fireEvent.keyDown(handle, { key: 'Home' });
  expect(resize).toHaveBeenLastCalledWith(PANEL_MIN_WIDTH);
  fireEvent.keyDown(handle, { key: 'ArrowRight' });
  expect(resize).toHaveBeenLastCalledWith(PANEL_MIN_WIDTH);
  fireEvent.keyDown(handle, { key: 'ArrowLeft' });
  expect(resize).toHaveBeenLastCalledWith(PANEL_MIN_WIDTH + 16);
  expect(collapse).not.toHaveBeenCalled();
  fireEvent.keyDown(handle, { key: 'End' });
  expect(resize).toHaveBeenLastCalledWith(PANEL_MAX_WIDTH);
});

it('drags a declared panel\'s left border from the column\'s right, and a cancelled drag resizes nothing', () => {
  const resize = vi.fn(), collapse = vi.fn();
  const { container } = render(<div><FilePanelColumn id="details" label="Details" width={320} onWidthChange={resize} onCollapse={collapse}>Content</FilePanelColumn></div>);
  const handle = screen.getByRole('separator');
  capture(handle);
  container.firstElementChild!.getBoundingClientRect = () => ({ right: 1000 } as DOMRect);
  pointer(handle, 'pointerdown', 680); pointer(handle, 'pointermove', 700);
  expect(resize).toHaveBeenLastCalledWith(300);
  pointer(handle, 'pointercancel', 700); pointer(handle, 'pointermove', 900);
  expect(resize).toHaveBeenCalledTimes(1);
});

it("names a panel's handle and its sheet after the panel, never after the toggle's verb", () => {
  expect(['Hide details', 'Show details', 'details'].map(filePanelName)).toEqual(['details', 'details', 'details']);
  for (const label of ['Hide details', 'Show details']) {
    render(<FilePanelColumn id="details" label={label} width={280} onWidthChange={vi.fn()}>Content</FilePanelColumn>);
    expect(screen.getByRole('separator').getAttribute('aria-label')).toBe('Resize details panel');
    cleanup();
    render(<FilePanelColumn id="details" label={label} width={280} onWidthChange={vi.fn()} mobile>Content</FilePanelColumn>);
    expect(screen.getByRole('dialog', { name: 'details' })).toBeTruthy();
    cleanup();
  }
});

import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { FilePanelColumn, PANEL_MIN_WIDTH, PANEL_MAX_WIDTH, filePanelName } from '../../../dist/file-viewer/navigation/FilePanelColumn.js';
import { FileExplorer } from '../../../dist/file-viewer/navigation/FileExplorer.js';

afterEach(cleanup);
const pointer = (handle: HTMLElement, type: string, x: number) => {
  const event = new Event(type, { bubbles: true });
  Object.assign(event, { button: 0, pointerId: 1, clientX: x });
  fireEvent(handle, event);
};
const capture = (handle: HTMLElement) => { handle.setPointerCapture = vi.fn(); handle.hasPointerCapture = () => true; handle.releasePointerCapture = vi.fn(); };

it('resizes the explorer and a panel down to the minimum by keyboard and stops there: the keyboard never closes either', () => {
  expect(PANEL_MIN_WIDTH).toBe(140);
  const panels = [
    // The explorer's handle is its right edge, so ArrowRight widens it; the column's is its left, so ArrowLeft does.
    { draw: (props: object) => <FileExplorer label="Files" {...props as any}>Content</FileExplorer>, wider: 'ArrowRight', narrower: 'ArrowLeft' },
    { draw: (props: object) => <FilePanelColumn id="source" label="Source" {...props as any}>Content</FilePanelColumn>, wider: 'ArrowLeft', narrower: 'ArrowRight' },
  ];
  for (const { draw, wider, narrower } of panels) {
    const resize = vi.fn(), collapse = vi.fn();
    render(draw({ width: PANEL_MIN_WIDTH, onWidthChange: resize, onCollapse: collapse }));
    const handle = screen.getByRole('separator');
    fireEvent.keyDown(handle, { key: 'Home' });
    expect(resize).toHaveBeenLastCalledWith(PANEL_MIN_WIDTH);
    fireEvent.keyDown(handle, { key: narrower });
    expect(resize).toHaveBeenLastCalledWith(PANEL_MIN_WIDTH);
    fireEvent.keyDown(handle, { key: wider });
    expect(resize).toHaveBeenLastCalledWith(PANEL_MIN_WIDTH + 16);
    expect(collapse).not.toHaveBeenCalled();
    fireEvent.keyDown(handle, { key: 'End' });
    expect(resize).toHaveBeenLastCalledWith(PANEL_MAX_WIDTH);
    cleanup();
  }
});

it('drags the explorer\'s right edge from its left: past the minimum it stops at it, and only well below it closes', () => {
  const resize = vi.fn(), collapse = vi.fn();
  render(<FileExplorer label="Files" width={320} onWidthChange={resize} onCollapse={collapse}>Content</FileExplorer>);
  const handle = screen.getByRole('separator', { name: 'Resize files panel' });
  capture(handle);
  handle.parentElement!.getBoundingClientRect = () => ({ left: 8 } as DOMRect);
  pointer(handle, 'pointerdown', 328); pointer(handle, 'pointermove', 308);
  expect(resize).toHaveBeenLastCalledWith(300);
  pointer(handle, 'pointercancel', 308); pointer(handle, 'pointermove', 500);
  expect(resize).toHaveBeenCalledTimes(1);
  pointer(handle, 'pointerdown', 308);
  pointer(handle, 'pointermove', 8 + PANEL_MIN_WIDTH - 30);
  expect(resize).toHaveBeenLastCalledWith(PANEL_MIN_WIDTH);
  expect(collapse).not.toHaveBeenCalled();
  pointer(handle, 'pointermove', 8 + PANEL_MIN_WIDTH / 2 - 1);
  expect(collapse).toHaveBeenCalledOnce();
  // It floats: inset from the view's corner like the tool strip, above the view, as tall as its
  // rows up to the view's height less the inset at either end.
  const panel = screen.getByRole('complementary', { name: 'Files' });
  expect([panel.style.top, panel.style.left, panel.style.bottom, panel.style.maxHeight, panel.style.width]).toEqual(['8px', '8px', '', 'calc(100% - 16px)', '320px']);
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
  expect(['Hide files', 'Show files', 'files'].map(filePanelName)).toEqual(['files', 'files', 'files']);
  for (const label of ['Hide details', 'Show details']) {
    render(<FilePanelColumn id="details" label={label} width={280} onWidthChange={vi.fn()}>Content</FilePanelColumn>);
    expect(screen.getByRole('separator').getAttribute('aria-label')).toBe('Resize details panel');
    cleanup();
    render(<FilePanelColumn id="details" label={label} width={280} onWidthChange={vi.fn()} mobile>Content</FilePanelColumn>);
    expect(screen.getByRole('dialog', { name: 'details' })).toBeTruthy();
    cleanup();
  }
  render(<FileExplorer label="Files" width={280} onWidthChange={vi.fn()} mobile>Content</FileExplorer>);
  expect(screen.getByRole('dialog', { name: 'Files' })).toBeTruthy();
});

it('the explorer goes when a press lands anywhere outside it, the navbar included; not for its own toggle or a press inside', () => {
  const dismiss = vi.fn();
  render(<div>
    <header data-viewer-navbar=""><button type="button" data-file-panel="tree">Hide files</button><button type="button">File actions</button></header>
    <FileExplorer label="Files" width={240} onWidthChange={() => {}} onDismiss={dismiss}><button type="button">tree row</button></FileExplorer>
    <main>model</main>
  </div>);
  fireEvent.pointerDown(screen.getByRole('button', { name: 'tree row' }));
  // Its toggle closes it itself.
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Hide files' }));
  expect(dismiss).not.toHaveBeenCalled();
  fireEvent.pointerDown(screen.getByRole('button', { name: 'File actions' }));
  expect(dismiss).toHaveBeenCalledTimes(1);
  fireEvent.pointerDown(screen.getByText('model'));
  expect(dismiss).toHaveBeenCalledTimes(2);
});

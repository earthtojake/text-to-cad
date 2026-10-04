import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { FilePanelColumn, PANEL_MIN_HEIGHT, PANEL_MIN_WIDTH, PANEL_MAX_WIDTH, filePanelName } from '../../../dist/file-viewer/navigation/FilePanelColumn.js';
import { FileExplorer } from '../../../dist/file-viewer/navigation/FileExplorer.js';

afterEach(cleanup);
const pointer = (handle: HTMLElement, type: string, x: number) => {
  const event = new Event(type, { bubbles: true });
  Object.assign(event, { button: 0, pointerId: 1, clientX: x });
  fireEvent(handle, event);
};
const capture = (handle: HTMLElement) => { handle.setPointerCapture = vi.fn(); handle.hasPointerCapture = () => true; handle.releasePointerCapture = vi.fn(); };

const pointerAt = (handle: HTMLElement, type: string, x: number, y: number) => {
  const event = new Event(type, { bubbles: true });
  Object.assign(event, { button: 0, pointerId: 1, clientX: x, clientY: y });
  fireEvent(handle, event);
};
// The explorer in a view `viewHeight` tall, drawn `width` by `height` (jsdom lays nothing out).
function explorer(props: object, { width, height, viewHeight }: { width: number; height: number; viewHeight: number }) {
  const { container } = render(<div><FileExplorer label="Files" {...props as any}>Content</FileExplorer></div>);
  Object.defineProperty(container.firstElementChild, 'clientHeight', { value: viewHeight });
  const panel = screen.getByRole('complementary', { name: 'Files' });
  panel.getBoundingClientRect = () => ({ width, height } as DOMRect);
  return { panel, grip: screen.getByRole('separator', { name: 'Resize files' }) };
}

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

it("the explorer's corner sizes its width and height cap by keyboard, within bounds", () => {
  const resize = vi.fn();
  const { grip } = explorer({ width: PANEL_MIN_WIDTH, onResize: resize }, { width: PANEL_MIN_WIDTH, height: 200, viewHeight: 416 });
  const keys = ['ArrowLeft', 'ArrowRight', 'ArrowDown', 'ArrowUp', 'Home', 'End'];
  for (const key of keys) fireEvent.keyDown(grip, { key });
  // The width never under its minimum nor over its maximum; the cap never under its floor nor
  // past the view, less the inset at either end.
  expect(resize.mock.calls.map(([size]) => size)).toEqual([
    { width: PANEL_MIN_WIDTH }, { width: PANEL_MIN_WIDTH + 16 }, { height: 216 }, { height: 184 },
    { width: PANEL_MIN_WIDTH, height: PANEL_MIN_HEIGHT }, { width: PANEL_MAX_WIDTH, height: 400 },
  ]);
});

it("drags the explorer's bottom-right corner: both edges move, written once when it lets go, and a cancelled drag writes nothing", () => {
  const resize = vi.fn();
  const { panel, grip } = explorer({ width: 320, height: 300, onResize: resize }, { width: 320, height: 300, viewHeight: 616 });
  // It floats: inset from the view's corner like the tool strip, above the view, as tall as its
  // rows up to its cap and the view's height less the inset at either end.
  // (jsdom writes `min(300px, calc(100% - 16px))` without the inner calc; a browser keeps it.)
  const cap = () => panel.style.maxHeight.replace('calc(', '').replace('))', ')');
  expect([panel.style.top, panel.style.left, panel.style.bottom, cap(), panel.style.width]).toEqual(['8px', '8px', '', 'min(300px, 100% - 16px)', '320px']);
  capture(grip);
  pointerAt(grip, 'pointerdown', 500, 500); pointerAt(grip, 'pointermove', 540, 450);
  // Drawn at the new size as it moves, written only when it lets go.
  expect([panel.style.width, cap()]).toEqual(['360px', 'min(250px, 100% - 16px)']);
  expect(resize).not.toHaveBeenCalled();
  pointerAt(grip, 'pointerup', 540, 450);
  expect(resize.mock.calls).toEqual([[{ width: 360, height: 250 }]]);
  pointerAt(grip, 'pointerdown', 500, 500); pointerAt(grip, 'pointermove', 700, 900); pointerAt(grip, 'pointercancel', 700, 900);
  expect(resize).toHaveBeenCalledTimes(1);
  expect(panel.style.width).toBe('320px');
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
  render(<FileExplorer label="Files" width={280} onResize={vi.fn()} mobile>Content</FileExplorer>);
  expect(screen.getByRole('dialog', { name: 'Files' })).toBeTruthy();
});

it('the explorer goes when a press lands anywhere outside it, the navbar included; not for its own toggle or a press inside', () => {
  const dismiss = vi.fn();
  render(<div>
    <header data-viewer-navbar=""><button type="button" data-file-panel="tree">Hide files</button><button type="button">File actions</button></header>
    <FileExplorer label="Files" width={240} onResize={() => {}} onDismiss={dismiss}><button type="button">tree row</button></FileExplorer>
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

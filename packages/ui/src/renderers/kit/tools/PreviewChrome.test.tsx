import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import PreviewChrome, { createPreviewIdle } from '../../../../dist/renderers/kit/tools/PreviewChrome.js';

afterEach(cleanup);
it('keeps editor controls hidden throughout Preview and restores them on exit', () => {
  const { container, rerender } = render(<PreviewChrome active><button>Tool</button></PreviewChrome>);
  const chrome = container.querySelector('[data-preview-chrome]')!;
  expect(chrome.hasAttribute('hidden')).toBe(true);
  expect(chrome.hasAttribute('inert')).toBe(true);
  fireEvent.pointerMove(document.body);
  expect(screen.queryByRole('button', { name: 'Tool' })).toBeNull();
  rerender(<PreviewChrome active={false}><button>Tool</button></PreviewChrome>);
  expect(chrome.hasAttribute('hidden')).toBe(false);
  expect(chrome.hasAttribute('inert')).toBe(false);
  expect(screen.getByRole('button', { name: 'Tool' })).toBeTruthy();
});

it("puts Preview's own bar over the view's top edge, the name at its left and its controls at its right, and its panel under it, only while it is up", () => {
  const view = render(<PreviewChrome active name="arm.step" controls={<button>Exit preview</button>} panel={<div data-testid="settings" />} />);
  const bar = view.container.querySelector<HTMLElement>('[data-preview-bar]')!;
  expect([bar.querySelector('[data-preview-name]')!.textContent, bar.querySelector('[data-preview-name]')!.nextElementSibling!.hasAttribute('data-preview-controls')]).toEqual(['arm.step', true]);
  expect(screen.getByRole('button', { name: 'Exit preview' }).closest('[data-preview-controls]')).not.toBeNull();
  expect(screen.getByTestId('settings').closest('[data-preview-panel]')).not.toBeNull();
  view.rerender(<PreviewChrome active={false} name="arm.step" controls={<button>Exit preview</button>} panel={<div data-testid="settings" />} />);
  expect(view.container.querySelector('[data-preview-bar]')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Exit preview' })).toBeNull();
});

it("names the file in Preview's bar muted, as its controls are", () => {
  const view = render(<PreviewChrome active name="arm.step" />);
  const name = view.container.querySelector<HTMLElement>('[data-preview-name]')!;
  expect([name.classList.contains('text-muted-foreground'), name.classList.contains('text-foreground')]).toEqual([true, false]);
});

it('hides the bar at once when the pointer leaves the view or the window, unless its settings hold it, and brings it back on a move', async () => {
  const root = document.createElement('div');
  document.body.append(root);
  try {
    const idle = createPreviewIdle();
    idle.setActive(true, root);
    // Waits for the one move's events: the pointer may be passing onto a menu of the bar's.
    const settle = () => new Promise(resolve => setTimeout(resolve));
    expect(idle.shown()).toBe(true);
    fireEvent.pointerLeave(root);
    await settle();
    expect(idle.shown()).toBe(false);
    fireEvent.pointerMove(root);
    expect(idle.shown()).toBe(true);
    fireEvent(window, new Event('blur'));
    await settle();
    expect(idle.shown()).toBe(false);
    fireEvent.pointerMove(root);
    // Held by its open settings, it stays.
    idle.setHeld(true);
    fireEvent.mouseLeave(root);
    await settle();
    expect(idle.shown()).toBe(true);
    idle.setActive(false, null);
  } finally { root.remove(); }
});

it("counts the pointer's rest from the frame that shows the chrome: a long frame is never idle time", () => {
  const frames: FrameRequestCallback[] = [];
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => frames.push(callback));
  vi.stubGlobal('cancelAnimationFrame', (handle: number) => { frames[handle - 1] = () => {}; });
  const frame = () => { for (const callback of frames.splice(0)) callback(0); };
  const root = document.createElement('div');
  document.body.append(root);
  try {
    const idle = createPreviewIdle();
    idle.setActive(true, root);
    fireEvent.pointerMove(root);
    // The frame the move lands in takes ten seconds to draw (a software GPU drawing Render): still up.
    vi.advanceTimersByTime(10_000);
    expect(idle.shown()).toBe(true);
    frame();
    frame();  // drawn: the count starts
    vi.advanceTimersByTime(2_000);
    expect(idle.shown()).toBe(true);
    // The count over, it goes at the next frame; a move that frame brings first keeps it up.
    fireEvent.pointerMove(root);
    frame();
    expect(idle.shown()).toBe(true);
    frame();
    frame();
    vi.advanceTimersByTime(2_000);
    frame();
    expect(idle.shown()).toBe(false);
    fireEvent.pointerMove(root);
    expect(idle.shown()).toBe(true);
    idle.setActive(false, null);
  } finally {
    root.remove();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  }
});

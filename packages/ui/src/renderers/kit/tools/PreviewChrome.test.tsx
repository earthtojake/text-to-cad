import React from 'react';
import { cleanup, fireEvent, render, screen, act } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import PreviewChrome, { PREVIEW_CHROME_IDLE_MS } from '../../../../dist/renderers/kit/tools/PreviewChrome.js';

afterEach(() => { cleanup(); vi.useRealTimers(); });
it('keeps editor controls hidden throughout Preview and restores them on exit, with one top-right bar in both', () => {
  const actions = vi.fn(() => <button>Display settings</button>);
  const { container, rerender } = render(<PreviewChrome active actions={actions}><button>Tool</button></PreviewChrome>);
  const chrome = container.querySelector('[data-preview-chrome]')!;
  const bar = container.querySelector('[data-viewport-actions]')!;
  expect(chrome.hasAttribute('hidden')).toBe(true);
  expect(chrome.hasAttribute('inert')).toBe(true);
  fireEvent.pointerMove(document.body);
  expect(chrome.getAttribute('data-visible')).toBe('false');
  expect(screen.queryByRole('button', { name: 'Tool' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Display settings' })).toBeTruthy();
  rerender(<PreviewChrome active={false} actions={actions}><button>Tool</button></PreviewChrome>);
  expect(chrome.hasAttribute('hidden')).toBe(false);
  expect(chrome.hasAttribute('inert')).toBe(false);
  expect(screen.getByRole('button', { name: 'Tool' })).toBeTruthy();
  // The same bar, in the same place, in either mode.
  expect(container.querySelector('[data-viewport-actions]')).toBe(bar);
  expect(screen.getByRole('button', { name: 'Display settings' })).toBeTruthy();
});

it('fades preview controls together, keeps their hover area awake, and never reveals editing tools', () => {
  vi.useFakeTimers();
  const { container, rerender } = render(<PreviewChrome active surface={document.body}
    playbar={<div data-preview-hover-hold="" data-testid="playback"><button>Pause</button></div>}>
    <button>Edit</button>
  </PreviewChrome>);
  const controls = container.querySelector('[data-preview-controls]')!;
  act(() => vi.advanceTimersByTime(PREVIEW_CHROME_IDLE_MS));
  expect(controls.getAttribute('data-visible')).toBe('false');
  expect(controls.hasAttribute('inert')).toBe(true);
  fireEvent.pointerMove(document.body);
  expect(controls.getAttribute('data-visible')).toBe('true');
  expect(screen.queryByRole('button', { name: 'Edit' })).toBeNull();
  fireEvent.pointerMove(screen.getByTestId('playback'));
  act(() => vi.advanceTimersByTime(PREVIEW_CHROME_IDLE_MS * 3));
  expect(controls.getAttribute('data-visible')).toBe('true');
  fireEvent.pointerMove(document.body);
  act(() => vi.advanceTimersByTime(PREVIEW_CHROME_IDLE_MS));
  expect(controls.getAttribute('data-visible')).toBe('false');
  // A popover its owner keeps open (Display settings) holds the controls up.
  rerender(<PreviewChrome active hold surface={document.body}><button>Edit</button></PreviewChrome>);
  act(() => vi.advanceTimersByTime(PREVIEW_CHROME_IDLE_MS * 3));
  expect(controls.getAttribute('data-visible')).toBe('true');
});

it('shows the bar and no playbar outside preview', () => {
  const { container } = render(<PreviewChrome active={false} playbar={<div data-testid="playback" />} actions={() => <button>Preview</button>} />);
  expect(container.querySelector('[data-preview-controls]')!.getAttribute('data-visible')).toBe('true');
  expect(screen.queryByTestId('playback')).toBeNull();
  expect(screen.getByRole('button', { name: 'Preview' })).toBeTruthy();
});

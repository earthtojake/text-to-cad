import React from 'react';
import { cleanup, fireEvent, render, screen, act } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import PreviewChrome, { PREVIEW_CHROME_IDLE_MS } from '../../../../dist/renderers/kit/tools/PreviewChrome.js';

afterEach(() => { cleanup(); vi.useRealTimers(); });
it('keeps editor controls hidden throughout Preview and restores them on exit', () => {
  const onExit = vi.fn();
  const { container, rerender } = render(<PreviewChrome active onExit={onExit}><button>Tool</button></PreviewChrome>);
  const chrome = container.querySelector('[data-preview-chrome]')!;
  expect(chrome.hasAttribute('hidden')).toBe(true);
  expect(chrome.hasAttribute('inert')).toBe(true);
  fireEvent.pointerMove(document.body);
  expect(chrome.getAttribute('data-visible')).toBe('false');
  expect(screen.queryByRole('button', { name: 'Tool' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Exit fullscreen' }));
  expect(onExit).toHaveBeenCalledTimes(1);
  rerender(<PreviewChrome active={false} onExit={onExit}><button>Tool</button></PreviewChrome>);
  expect(chrome.hasAttribute('hidden')).toBe(false);
  expect(chrome.hasAttribute('inert')).toBe(false);
  expect(screen.getByRole('button', { name: 'Tool' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Exit fullscreen' })).toBeNull();
});

it('fades presentation controls together, keeps their hover area awake, and never reveals editing tools', () => {
  vi.useFakeTimers();
  const { container } = render(<PreviewChrome active surface={document.body}
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
});

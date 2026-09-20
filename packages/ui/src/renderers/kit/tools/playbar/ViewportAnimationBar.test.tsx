import React from 'react';
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ViewportAnimationBar } from '../../../../../dist/renderers/kit/tools/playbar/ViewportAnimationBar.js';
import { createAnimationClock } from '../../../../../dist/renderers/kit/tools/playbar/animationClock.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const runtime = (overrides = {}) => ({
  clips: [{ id: 'a', label: 'Open', duration: 10 }], activeClipId: 'a', playing: true, elapsedSec: 2,
  speed: 1, loopEnabled: true, onPlayToggle: vi.fn(), onScrub: vi.fn(), ...overrides,
});

it('follows the clock on the runtime it is handed, whoever owns it', () => {
  const clock = createAnimationClock(), other = createAnimationClock();
  render(<ViewportAnimationBar runtime={runtime({ clock })}/>);
  const time = screen.getByRole('slider', { name: 'Animation time' });
  act(() => { clock.setAnimationClock(3); other.setAnimationClock(7); });
  expect(time.getAttribute('aria-valuenow')).toBe('3');
});

it('shows the stopped time from the runtime, not the clock', () => {
  const clock = createAnimationClock();
  clock.setAnimationClock(9);
  render(<ViewportAnimationBar runtime={runtime({ clock, playing: false, elapsedSec: 4 })}/>);
  expect(screen.getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuenow')).toBe('4');
});

it('draws nothing without routines and refuses a routine without a clock', () => {
  const { container } = render(<ViewportAnimationBar runtime={runtime({ clips: [] })}/>);
  expect(container.innerHTML).toBe('');
  const error = vi.spyOn(console, 'error').mockImplementation(() => {});
  expect(() => render(<ViewportAnimationBar runtime={runtime()}/>)).toThrow(/animation clock/);
  error.mockRestore();
});

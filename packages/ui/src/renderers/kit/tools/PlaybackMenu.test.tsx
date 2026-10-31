import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import PlaybackMenu from '../../../../dist/renderers/kit/tools/PlaybackMenu.js';
import { AnimationTimeControl, animationControlsHaveContent } from '../../../../dist/renderers/kit/tools/playbar/AnimationTimeControl.js';
import { createAnimationClock } from '../../../../dist/renderers/kit/tools/playbar/animationClock.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const clocks = () => ({ step: createAnimationClock() });
const routine = (patch = {}) => ({ clips: [{ id: 'turn', label: 'Turn', duration: 8 }], activeClipId: 'turn', elapsedSec: 2, playing: false,
  speed: 1, loopEnabled: true, onPlayToggle: vi.fn(), onScrub: vi.fn(), onSpeedChange: vi.fn(), onLoopToggle: vi.fn(), onClipSelect: vi.fn(), ...patch });

it("scrubs and follows the renderer's live clock", () => {
  const { step } = clocks(), runtime = routine({ clock: step });
  const { rerender } = render(<AnimationTimeControl runtime={runtime} />);
  const time = screen.getByRole('slider', { name: 'Animation time' });
  expect(time.getAttribute('aria-valuetext')).toBe('2.00s of 8.00s');
  fireEvent.keyDown(time, { key: 'ArrowRight' });
  expect(runtime.onScrub).toHaveBeenLastCalledWith(2.01);
  rerender(<AnimationTimeControl runtime={{ ...runtime, playing: true }} />);
  act(() => { step.setAnimationClock(3); });
  expect(time.getAttribute('aria-valuenow')).toBe('3');
});

it("has the routine's Speed, Loop and Autoplay in Playback settings, and nothing of the orbit", async () => {
  const user = userEvent.setup();
  const onAutoplayChange = vi.fn();
  const runtime = routine({ speed: 1.25 });
  render(<PlaybackMenu animation={runtime} autoplay={false} onAutoplayChange={onAutoplayChange} />);
  await user.click(screen.getByRole('button', { name: 'Playback settings' }));
  const speed = await screen.findByRole('menuitem', { name: 'Animation speed: 1.25×' });
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Loop' }));
  expect(runtime.onLoopToggle).toHaveBeenLastCalledWith(false);
  // Ticking a checkbox leaves the menu open.
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Autoplay' }));
  expect(onAutoplayChange).toHaveBeenLastCalledWith(true);
  expect(screen.getAllByRole('menuitemcheckbox').map(item => item.textContent)).toEqual(['Loop', 'Autoplay']);
  expect(screen.queryByRole('menuitem', { name: /Orbit/ })).toBeNull();
  await user.click(speed);
  const speeds = (await screen.findAllByRole('menuitemradio')).map(item => item.textContent);
  // An authored speed the presets lack is listed, so the menu never shows nothing checked.
  expect(speeds).toEqual(['0.25×', '0.5×', '0.75×', '1×', '1.25×', '1.5×', '2×', '3×']);
  // jsdom has no geometry for the submenu's pointer grace area; the keyboard path is the same handler.
  screen.getByRole('menuitemradio', { name: '2×' }).focus();
  await user.keyboard('{Enter}');
  expect(runtime.onSpeedChange).toHaveBeenLastCalledWith(2);
});

it('has no animation for a file without routines, loading or failed', () => {
  for (const runtime of [null, { clips: [] }, { clips: [], status: 'loading' }, { clips: [], error: 'the clips could not be read' }]) {
    expect(animationControlsHaveContent(runtime)).toBe(false);
  }
  expect(animationControlsHaveContent(routine())).toBe(true);
});

it('keeps clocks isolated and uses the stopped time from its own runtime', () => {
  const clock = createAnimationClock(), other = createAnimationClock();
  const { rerender } = render(<AnimationTimeControl runtime={routine({ clock, playing: true })} />);
  act(() => { clock.setAnimationClock(3); other.setAnimationClock(7); });
  expect(screen.getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuenow')).toBe('3');
  rerender(<AnimationTimeControl runtime={routine({ clock, playing: false, elapsedSec: 4 })} />);
  expect(screen.getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuenow')).toBe('4');
});

it('requires an explicit clock for a routine', () => {
  const error = vi.spyOn(console, 'error').mockImplementation(() => {});
  expect(() => render(<AnimationTimeControl runtime={routine()} />)).toThrow(/animation clock/);
  error.mockRestore();
});

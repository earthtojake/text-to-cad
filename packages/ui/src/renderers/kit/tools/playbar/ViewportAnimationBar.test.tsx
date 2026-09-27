import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import PlaybackMenu from '../../../../../dist/renderers/kit/tools/PlaybackMenu.js';
import { ViewportAnimationBar, animationControlsHaveContent } from '../../../../../dist/renderers/kit/tools/playbar/ViewportAnimationBar.js';
import { createAnimationClock } from '../../../../../dist/renderers/kit/tools/playbar/animationClock.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const clocks = () => ({ step: createAnimationClock() });
const bar = ({ step }: ReturnType<typeof clocks>, runtime: any, props = {}) => <ViewportAnimationBar runtime={runtime ? { ...runtime, clock: step } : null} {...props}/>;
const routine = (patch = {}) => ({ clips: [{ id: 'turn', label: 'Turn', duration: 8 }], activeClipId: 'turn', elapsedSec: 2, playing: false,
  speed: 1, loopEnabled: true, onPlayToggle: vi.fn(), onScrub: vi.fn(), onSpeedChange: vi.fn(), onLoopToggle: vi.fn(), onClipSelect: vi.fn(), ...patch });

it('plays, scrubs and follows the renderer\'s live clock, with no restart button', () => {
  const store = clocks(), runtime = routine();
  const { rerender } = render(bar(store, runtime));
  const time = screen.getByRole('slider', { name: 'Animation time' });
  expect(time.getAttribute('aria-valuetext')).toBe('2.00s of 8.00s');
  fireEvent.click(screen.getByRole('button', { name: 'Play animation' }));
  expect(runtime.onPlayToggle).toHaveBeenCalledOnce();
  fireEvent.keyDown(time, { key: 'ArrowRight' });
  expect(runtime.onScrub).toHaveBeenLastCalledWith(2.01);
  // Dragging the scrubber to the start is the restart.
  expect(screen.queryByRole('button', { name: 'Restart animation' })).toBeNull();
  rerender(bar(store, { ...runtime, playing: true }));
  act(() => { store.step.setAnimationClock(3); });
  expect(time.getAttribute('aria-valuenow')).toBe('3');
  expect(screen.getByRole('button', { name: 'Pause animation' })).toBeTruthy();
});

it('keeps routine, speed and loop out of the transport even with several clips', () => {
  render(bar(clocks(), routine({ clips: [{ id: 'turn', label: 'Turn', duration: 8 }, { id: 'open', label: 'Open', duration: 3 }] })));
  expect(screen.getAllByRole('button').map(button => button.getAttribute('aria-label'))).toEqual(['Play animation']);
  expect(screen.getByRole('slider', { name: 'Animation time' })).toBeTruthy();
});

it('ends with what it is handed after the transport: preview\'s Playback settings', () => {
  render(bar(clocks(), routine(), { trailing: <button type="button" aria-label="Playback settings" /> }));
  expect(screen.getAllByRole('button').map(button => button.getAttribute('aria-label'))).toEqual(['Play animation', 'Playback settings']);
});

it('has one Playback settings menu: the routine\'s Speed, Loop and Autoplay, then the orbit', async () => {
  const user = userEvent.setup();
  const onMenuOpenChange = vi.fn(), onAutoplayChange = vi.fn(), onOrbitChange = vi.fn(), onOrbitSpeedChange = vi.fn();
  const runtime = routine({ speed: 1.25 });
  render(<PlaybackMenu animation={runtime} autoplay={false} onAutoplayChange={onAutoplayChange} orbit onOrbitChange={onOrbitChange}
    orbitSpeed={1} onOrbitSpeedChange={onOrbitSpeedChange} onOpenChange={onMenuOpenChange} />);
  await user.click(screen.getByRole('button', { name: 'Playback settings' }));
  // Preview holds its chrome open while the menu is open.
  expect(onMenuOpenChange).toHaveBeenLastCalledWith(true);
  const speed = await screen.findByRole('menuitem', { name: 'Animation speed: 1.25×' });
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Loop' }));
  expect(runtime.onLoopToggle).toHaveBeenLastCalledWith(false);
  // Ticking a checkbox leaves the menu open.
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Autoplay' }));
  expect(onAutoplayChange).toHaveBeenLastCalledWith(true);
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Orbit' }));
  expect(onOrbitChange).toHaveBeenLastCalledWith(false);
  expect(screen.getByRole('menuitem', { name: 'Orbit speed: 1×' })).toBeTruthy();
  await user.click(speed);
  const speeds = (await screen.findAllByRole('menuitemradio')).map(item => item.textContent);
  // An authored speed the presets lack is listed, so the menu never shows nothing checked.
  expect(speeds).toEqual(['0.25×', '0.5×', '0.75×', '1×', '1.25×', '1.5×', '2×', '3×']);
  // jsdom has no geometry for the submenu's pointer grace area; the keyboard path is the same handler.
  screen.getByRole('menuitemradio', { name: '2×' }).focus();
  await user.keyboard('{Enter}');
  expect(runtime.onSpeedChange).toHaveBeenLastCalledWith(2);
});

it('offers a static file\'s orbit alone, and a routine picker only with several routines', async () => {
  const user = userEvent.setup();
  const view = render(<PlaybackMenu animation={null} autoplay={false} onAutoplayChange={vi.fn()} orbit={false} onOrbitChange={vi.fn()}
    orbitSpeed={0.5} onOrbitSpeedChange={vi.fn()} />);
  await user.click(screen.getByRole('button', { name: 'Playback settings' }));
  expect((await screen.findAllByRole('menuitemcheckbox')).map(item => item.textContent)).toEqual(['Orbit']);
  expect(screen.queryByRole('menuitem', { name: /Routine/ })).toBeNull();
  expect(screen.getByRole('menuitem', { name: 'Orbit speed: 0.5×' })).toBeTruthy();
  view.unmount();
  render(<PlaybackMenu animation={routine({ clips: [{ id: 'turn', label: 'Turn', duration: 8 }, { id: 'open', label: 'Open', duration: 3 }] })}
    autoplay onAutoplayChange={vi.fn()} orbit onOrbitChange={vi.fn()} orbitSpeed={1} onOrbitSpeedChange={vi.fn()} />);
  await user.click(screen.getByRole('button', { name: 'Playback settings' }));
  expect((await screen.findByRole('menuitem', { name: /Routine/ })).textContent).toContain('Turn');
});

it('does not exist for a file without routines, loading or failed', () => {
  for (const runtime of [null, { clips: [] }, { clips: [], status: 'loading' }, { clips: [], error: 'sidecar failed' }]) {
    expect(animationControlsHaveContent(runtime)).toBe(false);
    const view = render(bar(clocks(), runtime));
    expect(view.container.innerHTML).toBe('');
    view.unmount();
  }
});

it('keeps clocks isolated and uses the stopped time from its own runtime', () => {
  const clock = createAnimationClock(), other = createAnimationClock();
  const { rerender } = render(<ViewportAnimationBar runtime={routine({ clock, playing: true })} />);
  act(() => { clock.setAnimationClock(3); other.setAnimationClock(7); });
  expect(screen.getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuenow')).toBe('3');
  rerender(<ViewportAnimationBar runtime={routine({ clock, playing: false, elapsedSec: 4 })} />);
  expect(screen.getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuenow')).toBe('4');
});

it('requires an explicit clock for a routine', () => {
  const error = vi.spyOn(console, 'error').mockImplementation(() => {});
  expect(() => render(<ViewportAnimationBar runtime={routine()} />)).toThrow(/animation clock/);
  error.mockRestore();
});

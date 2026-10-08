import React from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import PlaybackMenu, { OrbitMenu, RoutineMenu } from '../../../../../dist/renderers/kit/tools/PlaybackMenu.js';
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

const twoRoutines = [{ id: 'turn', label: 'Turn', duration: 8 }, { id: 'open', label: 'Open', duration: 3 }];
const labels = () => screen.getAllByRole('button').map(button => button.getAttribute('aria-label'));

it('keeps routine, speed and loop out of the transport even with several clips', () => {
  render(bar(clocks(), routine({ clips: twoRoutines })));
  expect(labels()).toEqual(['Play animation']);
  expect(screen.getByRole('slider', { name: 'Animation time' })).toBeTruthy();
});

it('starts with the Routines it is handed and ends with Playback settings, the transport between them', () => {
  const runtime = routine({ clips: twoRoutines });
  render(bar(clocks(), runtime, { leading: <RoutineMenu animation={runtime} />,
    trailing: <PlaybackMenu animation={runtime} autoplay={false} onAutoplayChange={vi.fn()} /> }));
  expect(labels()).toEqual(['Routines', 'Play animation', 'Playback settings']);
});

it("lists several routines at the playbar's left as a playlist, the one in hand checked; one routine has no list", async () => {
  const user = userEvent.setup();
  const onOpenChange = vi.fn();
  const runtime = routine({ clips: twoRoutines });
  const view = render(<RoutineMenu animation={runtime} onOpenChange={onOpenChange} />);
  await user.click(screen.getByRole('button', { name: 'Routines' }));
  // Preview holds its chrome up while the list is open.
  expect(onOpenChange).toHaveBeenLastCalledWith(true);
  const list = screen.getByRole('menu', { name: 'Routines' });
  expect(within(list).getAllByRole('menuitemradio').map(item => [item.textContent, item.getAttribute('aria-checked')]))
    .toEqual([['Turn', 'true'], ['Open', 'false']]);
  // Choosing one plays it next and closes the list.
  await user.click(within(list).getByRole('menuitemradio', { name: 'Open' }));
  expect(runtime.onClipSelect).toHaveBeenLastCalledWith('open');
  expect(screen.queryByRole('menu')).toBeNull();
  view.unmount();
  render(<RoutineMenu animation={routine()} />);
  expect(screen.queryByRole('button', { name: 'Routines' })).toBeNull();
});

it("has the routine's Speed, Loop and Autoplay in the playbar's Playback settings, and nothing of the orbit", async () => {
  const user = userEvent.setup();
  const onMenuOpenChange = vi.fn(), onAutoplayChange = vi.fn();
  const runtime = routine({ speed: 1.25 });
  render(<PlaybackMenu animation={runtime} autoplay={false} onAutoplayChange={onAutoplayChange} onOpenChange={onMenuOpenChange} />);
  await user.click(screen.getByRole('button', { name: 'Playback settings' }));
  // Preview holds its chrome open while the menu is open.
  expect(onMenuOpenChange).toHaveBeenLastCalledWith(true);
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

it("has preview's Orbit, on or off and its Speed, in the Orbit menu", async () => {
  const user = userEvent.setup();
  const onOrbitChange = vi.fn(), onSpeedChange = vi.fn();
  render(<OrbitMenu orbit onOrbitChange={onOrbitChange} speed={0.5} onSpeedChange={onSpeedChange} />);
  await user.click(screen.getByRole('button', { name: 'Orbit' }));
  const menu = screen.getByRole('menu', { name: 'Orbit' });
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'Orbit' }));
  expect(onOrbitChange).toHaveBeenLastCalledWith(false);
  // Ticking it leaves the menu open, on its Speed.
  await user.click(within(screen.getByRole('menu', { name: 'Orbit' })).getByRole('menuitem', { name: 'Orbit speed: 0.5×' }));
  (await screen.findByRole('menuitemradio', { name: '5×' })).focus();
  await user.keyboard('{Enter}');
  expect(onSpeedChange).toHaveBeenLastCalledWith(5);
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

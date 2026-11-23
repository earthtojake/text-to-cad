import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import PlaybackMenu from '../../../../dist/renderers/kit/tools/PlaybackMenu.js';
import { AnimationTimeControl, animationControlsHaveContent } from '../../../../dist/renderers/kit/tools/playbar/AnimationTimeControl.js';
import { createAnimationClock } from '../../../../dist/renderers/kit/tools/playbar/animationClock.js';
import { DEFAULT_PANEL_WIDTH } from '../../../../dist/renderers/kit/shell/sidebars.js';

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

it("has the routine's Speed and Loop in Playback settings, no Autoplay, and nothing of the orbit", async () => {
  const user = userEvent.setup();
  const runtime = routine({ speed: 1.25 });
  render(<PlaybackMenu animation={runtime} />);
  await user.click(screen.getByRole('button', { name: 'Playback settings' }));
  const speed = await screen.findByRole('menuitem', { name: 'Animation speed: 1.25×' });
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Loop' }));
  expect(runtime.onLoopToggle).toHaveBeenLastCalledWith(false);
  // Ticking a checkbox leaves the menu open.
  expect(screen.getAllByRole('menuitemcheckbox').map(item => item.textContent)).toEqual(['Loop']);
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

it("the Animation section holds the same controls playing and paused, its scrubber's start lets the routine go, and a file without routines has none", async () => {
  const { default: AnimationTab } = await import('../../../../dist/renderers/kit/tools/playbar/AnimationSection.js');
  const bar = () => document.querySelector<HTMLElement>('[data-animation-section]')!;
  // Each control by its accessible name: the routine's dropdown, Play/Pause and the scrubber (one row), Speed, Loop.
  const controls = () => [...bar().querySelectorAll('[data-animation-clip-menu], [data-animation-play], [role=slider], [data-animation-speed], [data-animation-loop]')]
    .map(control => control.getAttribute('aria-label') || control.textContent);
  const props = {};
  const clock = createAnimationClock();
  const playing = routine({ clock, enabled: true, playing: true, onRelease: vi.fn() });
  const { rerender } = render(<AnimationTab runtime={playing} {...props} />);
  act(() => { clock.setAnimationClock(3); });
  expect(controls()).toEqual(['Routines: Turn', 'Pause animation', 'Animation time', 'Animation speed: 1×', 'Loop']);
  // One clip: its dropdown all the same, above the transport; Play at the row's left, the scrubber the rest (no Reset
  // there: the tab's actions row has it, at the bottom right);
  // no time readout (the time is the scrubber's value).
  expect([bar().querySelector('[data-animation-clip-menu] [data-field-value]')!.textContent, bar().querySelector('[data-animation-time]'),
    [...bar().querySelector('[data-animation-transport]')!.children].map(child => child.hasAttribute('data-animation-play') ? 'play' : child.hasAttribute('data-animation-reset') ? 'reset' : child.hasAttribute('data-animation-scrubber') ? 'scrubber' : '?')])
    .toEqual(['Turn', null, ['play', 'scrubber']]);
  expect(document.querySelector('[data-animation-reset]')!.closest('[data-panel-foot]')).not.toBeNull();
  // Every control the panel's own: Clip and Speed bordered dropdowns as Joints' Position is (the clip's name alone, no
  // duration; Clip labelled as Speed is), Play/Pause the strip's 28px tile, Loop a
  // switch row, a label and its switch, no icon.
  const clipMenu = bar().querySelector<HTMLElement>('[data-animation-clip-menu]')!, speed = bar().querySelector<HTMLElement>('[data-animation-speed]')!;
  expect([clipMenu.hasAttribute('data-panel-dropdown'), speed.hasAttribute('data-panel-dropdown'), clipMenu.textContent, speed.textContent]).toEqual([true, true, 'Turn', '1×']);
  expect(bar().querySelector('[data-animation-play]')!.className).toEqual(expect.stringContaining('size-control'));
  // The clip row is labelled as Speed's is, the same row: its label and the dropdown.
  expect([clipMenu.classList.contains('w-full'), clipMenu.closest('[data-panel-select-row]')!.children.length, clipMenu.closest('[data-panel-select-row]')!.firstElementChild!.textContent,
    speed.closest('[data-panel-select-row]')!.className]).toEqual([true, 2, 'Animation', clipMenu.closest('[data-panel-select-row]')!.className]);
  expect(['loop'].map(id => { const row = bar().querySelector(`[data-animation-${id}]`)!; return [row.hasAttribute('data-panel-switch-row'), row.querySelector('svg'), Boolean(row.querySelector('[role=switch]'))]; }))
    .toEqual([[true, null, true]]);
  expect(screen.getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuetext')).toBe('3.00s of 8.00s');
  // Playing, its start is a scrub from the start: the routine plays on.
  fireEvent.keyDown(screen.getByRole('slider', { name: 'Animation time' }), { key: 'Home' });
  expect([playing.onScrub.mock.calls.at(-1), playing.onRelease.mock.calls.length]).toEqual([[0], 0]);
  // Paused mid-routine: the same controls; scrubbed to its start, it lets the model go, at rest.
  const paused = routine({ clock: createAnimationClock(), enabled: true, onRelease: vi.fn() });
  rerender(<AnimationTab runtime={paused} {...props} />);
  expect(controls()).toEqual(['Routines: Turn', 'Play animation', 'Animation time', 'Animation speed: 1×', 'Loop']);
  fireEvent.keyDown(screen.getByRole('slider', { name: 'Animation time' }), { key: 'ArrowRight' });
  expect(paused.onScrub).toHaveBeenLastCalledWith(2.01);
  fireEvent.keyDown(screen.getByRole('slider', { name: 'Animation time' }), { key: 'Home' });
  expect([paused.onRelease.mock.calls.length, paused.onScrub.mock.calls.length]).toEqual([1, 1]);
  // Paused at its start (a routine just played from its start and paused), it is at rest as well.
  const atStart = routine({ clock: createAnimationClock(), enabled: true, elapsedSec: 0, onRelease: vi.fn() });
  rerender(<AnimationTab runtime={atStart} {...props} />);
  expect(atStart.onRelease).toHaveBeenCalledTimes(1);
  rerender(<AnimationTab runtime={{ clips: [] }} {...props} />);
  expect(document.querySelector('[data-animation-section]')).toBeNull();
});

it("the Animation section's settings are the Playback settings menu's items as the panel's rows: Speed a dropdown, Loop a switch; the routines a dropdown, the one in hand checked, a choice putting another in hand", async () => {
  for (const [name, value] of Object.entries({ scrollIntoView() {}, hasPointerCapture: () => false, setPointerCapture() {}, releasePointerCapture() {} })) {
    (Element.prototype as any)[name] = value;
  }
  const { default: AnimationSection } = await import('../../../../dist/renderers/kit/tools/playbar/AnimationSection.js');
  const user = userEvent.setup({ pointerEventsCheck: 0 });
  const runtime = routine({ clock: createAnimationClock(), enabled: true, playing: true,
    clips: [{ id: 'turn', label: 'Turn', duration: 8 }, { id: 'open', label: 'Open', duration: 2 }] });
  render(<AnimationSection runtime={runtime} />);
  await user.click(screen.getByRole('button', { name: 'Routines: Turn' }));
  const clips = await screen.findAllByRole('menuitemradio');
  expect(clips.map(clip => [clip.textContent, clip.getAttribute('aria-checked')])).toEqual([['Turn', 'true'], ['Open', 'false']]);
  await user.click(clips[1]);
  expect([runtime.onClipSelect.mock.calls, runtime.onPlayToggle.mock.calls.length]).toEqual([[['open']], 1]);
  // Loop: a switch; no Autoplay.
  expect([screen.getByRole('switch', { name: 'Loop' }).getAttribute('aria-checked'), screen.queryByRole('switch', { name: 'Autoplay' })]).toEqual(['true', null]);
  await user.click(screen.getByRole('switch', { name: 'Loop' }));
  expect(runtime.onLoopToggle).toHaveBeenLastCalledWith(false);
  await user.click(screen.getByRole('button', { name: 'Animation speed: 1×' }));
  const speeds = await screen.findAllByRole('menuitemradio');
  expect(speeds.map(item => [item.textContent, item.getAttribute('aria-checked')]).filter(([, checked]) => checked === 'true')).toEqual([['1×', 'true']]);
  expect(speeds.map(item => item.textContent)).toEqual(['0.25×', '0.5×', '0.75×', '1×', '1.5×', '2×', '3×']);
  await user.click(screen.getByRole('menuitemradio', { name: '1.5×' }));
  expect(runtime.onSpeedChange).toHaveBeenLastCalledWith(1.5);
});

// The Animation tab's "changed" dot (`FlatPanel.jsx`'s `FlatPanelChanged`): on exactly while its Reset is, from the
// same state — the routine off its start; Speed and Loop are preferences and never set it. Reset is the tab's
// actions row's, at its bottom right, and puts the routine back at its start.
it("the Animation tab's dot is on exactly while its Reset is, and its preferences never set it", async () => {
  const { default: AnimationSection } = await import('../../../../dist/renderers/kit/tools/playbar/AnimationSection.js');
  const { default: FlatPanel } = await import('../../../../dist/renderers/kit/shell/FlatPanel.js');
  const panel = (runtime: object) => <FlatPanel mode="docked" open onClose={() => {}} label="Model panel" searchLabel="Search the model"
    sections={<AnimationSection runtime={runtime} />} tab="animation" onTabChange={() => {}} width={DEFAULT_PANEL_WIDTH} maxWidth={480}
    onWidthChange={() => {}} focusSearch={0} />;
  const state = () => {
    const reset = document.querySelector<HTMLButtonElement>('[data-animation-reset]')!, heading = document.querySelector<HTMLElement>('[data-flat-panel-heading]')!;
    return [!reset.disabled, heading.hasAttribute('data-changed'), Boolean(heading.querySelector('[data-tool-changed]')), heading.getAttribute('aria-label')];
  };
  const rest = routine({ clock: createAnimationClock(), enabled: true, elapsedSec: 0, onRelease: vi.fn() });
  const { rerender } = render(panel(rest));
  expect(state()).toEqual([false, false, false, null]);
  // Speed and Loop changed: still at its start, no dot.
  rerender(panel({ ...rest, speed: 2, loopEnabled: false }));
  expect(state()).toEqual([false, false, false, null]);
  rerender(panel(routine({ clock: createAnimationClock(), enabled: true, elapsedSec: 3, onRelease: vi.fn() })));
  expect(state()).toEqual([true, true, true, 'Animation, changed']);
  const away = routine({ clock: createAnimationClock(), enabled: true, elapsedSec: 3, onRelease: vi.fn() });
  rerender(panel(away as any));
  fireEvent.click(document.querySelector('[data-animation-reset]')!);
  expect(away.onRelease).toHaveBeenCalledTimes(1);
  rerender(<FlatPanel mode="docked" open onClose={() => {}} label="Model panel" searchLabel="Search the model"
    sections={<AnimationSection runtime={routine({ clock: createAnimationClock(), enabled: true, elapsedSec: 3 })} disabled />}
    tab="animation" onTabChange={() => {}} width={DEFAULT_PANEL_WIDTH} maxWidth={480} onWidthChange={() => {}} focusSearch={0} />);
  expect(state()).toEqual([false, false, false, null]);
});

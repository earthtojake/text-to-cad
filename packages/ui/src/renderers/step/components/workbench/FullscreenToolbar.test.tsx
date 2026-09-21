import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FullscreenToolbar, { FULLSCREEN_TOOLBAR_IDLE_MS } from '../../../../../dist/renderers/step/components/workbench/FullscreenToolbar.js';
import { AnimationClockProvider, createAnimationClock } from '../../../../../dist/renderers/step/workbench/animationClockStore.js';

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  HTMLElement.prototype.scrollIntoView ||= () => {};
  HTMLElement.prototype.setPointerCapture ||= () => {};
  HTMLElement.prototype.releasePointerCapture ||= () => {};
  HTMLElement.prototype.hasPointerCapture ||= () => false;
});
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
const clips = [{ id: 'turn', label: 'Turn', duration: 8 }, { id: 'sweep', label: 'Sweep', duration: 4 }];
function Harness({ clips: available = clips, toggle = vi.fn(), select = vi.fn(), exit = vi.fn(), restart = vi.fn(), scrub = vi.fn(), speed = vi.fn(), loop = vi.fn(), stepClock }: any) {
  const [playing, setPlaying] = React.useState(false), [activeClipId, setClip] = React.useState('turn'), [orbitSpeed, setOrbit] = React.useState(1);
  const [animationSpeed, setSpeed] = React.useState(1), [loopEnabled, setLoop] = React.useState(true);
  const [step] = React.useState(() => stepClock || createAnimationClock());
  return <AnimationClockProvider value={step}>
    <FullscreenToolbar orbitSpeed={orbitSpeed} onOrbitSpeedChange={setOrbit} onExit={exit}
      animation={{ clips: available, playing, activeClipId, elapsedSec: 2, onRestart: restart, onScrub: scrub, speed: animationSpeed, loopEnabled,
        onSpeedChange(value: number) { speed(value); setSpeed(value); }, onLoopToggle(value: boolean) { loop(value); setLoop(value); },
        onPlayToggle() { toggle(); setPlaying(value => !value); },
        onClipSelect(id: string) { select(id); setClip(id); setPlaying(false); } }}/>
  </AnimationClockProvider>;
}

it('fades both control areas on idle, wakes on pointer/keyboard activity, and cleans up', () => {
  vi.useFakeTimers();
  const { unmount } = render(<Harness/>);
  const controls = screen.getByRole('group', { name: 'Fullscreen controls' });
  act(() => vi.advanceTimersByTime(FULLSCREEN_TOOLBAR_IDLE_MS));
  expect(controls.getAttribute('aria-hidden')).toBe('true'); expect(controls.hasAttribute('inert')).toBe(true);
  expect(screen.queryByRole('button', { name: 'Exit fullscreen' })).toBeNull();
  expect(screen.queryByRole('toolbar')).toBeNull();
  fireEvent.pointerMove(document);
  expect(controls.getAttribute('aria-hidden')).toBe('false');
  act(() => vi.advanceTimersByTime(FULLSCREEN_TOOLBAR_IDLE_MS));
  fireEvent.keyDown(document, { key: 'Tab' });
  expect(controls.getAttribute('aria-hidden')).toBe('false');
  unmount(); expect(vi.getTimerCount()).toBe(0);
});

it('holds controls visible during a scrub gesture', () => {
  vi.useFakeTimers(); render(<Harness/>);
  fireEvent.pointerDown(screen.getByRole('slider', { name: 'Animation time' }));
  act(() => vi.advanceTimersByTime(FULLSCREEN_TOOLBAR_IDLE_MS * 2));
  expect(screen.getByRole('group', { name: 'Fullscreen controls' }).getAttribute('aria-hidden')).toBe('false');
  fireEvent.pointerUp(document);
  act(() => vi.advanceTimersByTime(FULLSCREEN_TOOLBAR_IDLE_MS));
  expect(screen.queryByRole('toolbar')).toBeNull();
});

it('the corner settings are orbit only, and hold the controls visible while open', () => {
  vi.useFakeTimers(); render(<Harness/>);
  fireEvent.click(screen.getByRole('button', { name: 'Orbit settings' }));
  // Routine, speed and loop live in the playbar, the same one the Animate tool shows.
  expect(screen.queryByRole('heading', { name: 'Animation' })).toBeNull();
  expect(screen.getByRole('heading', { name: 'Orbit' })).toBeTruthy();
  act(() => vi.advanceTimersByTime(FULLSCREEN_TOOLBAR_IDLE_MS * 2));
  expect(screen.getByRole('group', { name: 'Fullscreen controls' }).getAttribute('aria-hidden')).toBe('false');
  fireEvent.keyDown(screen.getByRole('slider', { name: 'Orbit speed' }), { key: 'Home' });
  expect(screen.getByRole('textbox', { name: 'Orbit speed value' }).getAttribute('value')).toBe('0×');
  expect(screen.getByRole('button', { name: 'Play animation' })).toBeTruthy();
});

it('play/pause is a plain button even with multiple routines', () => {
  const toggle = vi.fn(); render(<Harness toggle={toggle}/>);
  const play = screen.getByRole('button', { name: 'Play animation' });
  expect(play.getAttribute('aria-haspopup')).toBeNull();
  fireEvent.click(play);
  fireEvent.click(screen.getByRole('button', { name: 'Pause animation' }));
  expect(toggle).toHaveBeenCalledTimes(2);
  fireEvent.keyDown(play, { key: 'ArrowDown' });
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(screen.queryByRole('listbox')).toBeNull();
});

it('the playbar carries the routine list and the settings menu, and an open menu holds the bar visible', async () => {
  const select = vi.fn(), loop = vi.fn();
  const user = userEvent.setup();
  render(<Harness select={select} loop={loop}/>);
  await user.click(screen.getByRole('button', { name: 'Animation routine: Turn' }));
  await user.click(await screen.findByRole('menuitemradio', { name: 'Sweep' }));
  expect(select).toHaveBeenCalledWith('sweep');
  expect(screen.getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuemax')).toBe('4');
  vi.useFakeTimers({ shouldAdvanceTime: true });
  fireEvent.pointerDown(screen.getByRole('button', { name: 'Playback settings' }), { button: 0, ctrlKey: false });
  fireEvent.click(await screen.findByRole('menuitemcheckbox', { name: 'Loop' })); expect(loop).toHaveBeenCalledWith(false);
  act(() => vi.advanceTimersByTime(FULLSCREEN_TOOLBAR_IDLE_MS * 2));
  // An open menu hides the rest of the page from the accessibility tree, so read the controls' own flag.
  expect(document.querySelector('[aria-label="Fullscreen controls"]')!.getAttribute('data-visible')).toBe('true');
});

it('shares live progress and scrub with the Animate tool\'s bar', () => {
  const stepClock = createAnimationClock(), scrub = vi.fn();
  render(<Harness stepClock={stepClock} scrub={scrub}/>);
  const time = screen.getByRole('slider', { name: 'Animation time' });
  expect(time.getAttribute('aria-valuenow')).toBe('2');
  fireEvent.keyDown(time, { key: 'ArrowRight' });
  expect(scrub).toHaveBeenLastCalledWith(2.01);
  expect(screen.queryByRole('button', { name: 'Restart animation' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Play animation' }));
  act(() => { stepClock.setAnimationClock(3); });
  expect(time.getAttribute('aria-valuenow')).toBe('3');
});

it('Escape closes settings before reaching the fullscreen host', () => {
  render(<Harness/>);
  const hostEscape = vi.fn(); window.addEventListener('keydown', hostEscape);
  try {
    fireEvent.click(screen.getByRole('button', { name: 'Orbit settings' }));
    fireEvent.keyDown(screen.getByRole('dialog', { name: 'Orbit settings' }), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull(); expect(hostEscape).not.toHaveBeenCalled();
    expect(screen.getByRole('toolbar')).toBeTruthy();
  } finally { window.removeEventListener('keydown', hostEscape); }
});

it('a single clip keeps the playbar and its settings but omits the routine list', () => {
  render(<Harness clips={clips.slice(0, 1)}/>);
  expect(screen.getByRole('button', { name: 'Playback settings' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: /Animation routine/ })).toBeNull();
});

it('without animation fullscreen has no tool: no play bar, and the corner still controls orbit', () => {
  const exit = vi.fn(); render(<Harness clips={[]} exit={exit}/>);
  expect(screen.queryByRole('toolbar')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Position' })).toBeNull();
  expect(screen.queryByRole('slider', { name: 'Animation time' })).toBeNull();
  expect(screen.getAllByRole('button').map(button => button.getAttribute('aria-label'))).toEqual(['Orbit settings', 'Exit fullscreen']);
  fireEvent.click(screen.getByRole('button', { name: 'Orbit settings' }));
  expect(screen.queryByRole('heading', { name: 'Animation' })).toBeNull();
  expect(screen.getByRole('heading', { name: 'Orbit' })).toBeTruthy();
  const input = screen.getByRole('textbox', { name: 'Orbit speed value' });
  act(() => input.focus());
  fireEvent.change(input, { target: { value: '1.37' } }); fireEvent.keyDown(input, { key: 'Enter' });
  expect(screen.getByRole('slider', { name: 'Orbit speed' }).getAttribute('aria-valuenow')).toBe('1.37');
  fireEvent.keyDown(screen.getByRole('slider', { name: 'Orbit speed' }), { key: 'End' });
  expect(input.getAttribute('value')).toBe('5×');
  fireEvent.click(screen.getByRole('button', { name: 'Exit fullscreen' })); expect(exit).toHaveBeenCalledOnce();
});

import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ViewportAnimationBar, animationControlsHaveContent } from '../../../../../dist/renderers/cad/components/workbench/AnimationControlsSection.js';
import { AnimationClockProvider, createAnimationClock } from '../../../../../dist/renderers/cad/workbench/animationClockStore.js';
import { EmbeddedGlbAnimationClockProvider } from '../../../../../dist/renderers/cad/workbench/embeddedGlbAnimationClockStore.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const clocks = () => ({ step: createAnimationClock(), glb: createAnimationClock() });
const bar = ({ step, glb }: ReturnType<typeof clocks>, runtime: any, props = {}) => <AnimationClockProvider value={step}>
  <EmbeddedGlbAnimationClockProvider value={glb}><ViewportAnimationBar runtime={runtime} {...props}/></EmbeddedGlbAnimationClockProvider>
</AnimationClockProvider>;
const routine = (patch = {}) => ({ clips: [{ id: 'turn', label: 'Turn', duration: 8 }], activeClipId: 'turn', elapsedSec: 2, playing: false,
  speed: 1, loopEnabled: true, onPlayToggle: vi.fn(), onScrub: vi.fn(), onSpeedChange: vi.fn(), onLoopToggle: vi.fn(), onClipSelect: vi.fn(), ...patch });

it.each(['step', 'embedded-glb'])('plays, scrubs and follows the live %s clock, with no restart button', clockKind => {
  const store = clocks(), runtime = routine({ clockKind });
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
  act(() => { store.step.setAnimationClock(3); store.glb.setAnimationClock(4); });
  expect(time.getAttribute('aria-valuenow')).toBe(clockKind === 'step' ? '3' : '4');
  expect(screen.getByRole('button', { name: 'Pause animation' })).toBeTruthy();
});

it('is ordered routine, transport, settings, and offers a routine list only when there is a choice', async () => {
  const user = userEvent.setup();
  const one = routine();
  const { rerender } = render(bar(clocks(), one));
  expect(screen.queryByRole('button', { name: /Animation routine/ })).toBeNull();
  const two = routine({ clips: [{ id: 'turn', label: 'Turn', duration: 8 }, { id: 'open', label: 'Open', duration: 3 }] });
  rerender(bar(clocks(), two));
  const buttons = [...screen.getByRole('toolbar', { name: 'Animation playback' }).querySelectorAll('button')].map(button => button.getAttribute('aria-label'));
  expect(buttons).toEqual(['Animation routine: Turn', 'Play animation', 'Playback settings']);
  await user.click(screen.getByRole('button', { name: 'Animation routine: Turn' }));
  await user.click(await screen.findByRole('menuitemradio', { name: 'Open' }));
  expect(two.onClipSelect).toHaveBeenCalledWith('open');
});

it('has a player\'s settings menu: Speed opens the list of speeds, Loop toggles in place', async () => {
  const user = userEvent.setup();
  const onMenuOpenChange = vi.fn(), runtime = routine({ speed: 1.25 });
  render(bar(clocks(), runtime, { onMenuOpenChange }));
  await user.click(screen.getByRole('button', { name: 'Playback settings' }));
  // Fullscreen holds its auto-hiding bar open while a menu of the bar's is.
  expect(onMenuOpenChange).toHaveBeenLastCalledWith(true);
  const speed = await screen.findByRole('menuitem', { name: /Speed/ });
  expect(speed.textContent).toContain('1.25×');
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Loop' }));
  expect(runtime.onLoopToggle).toHaveBeenLastCalledWith(false);
  expect(screen.getByRole('menuitemcheckbox', { name: 'Loop' })).toBeTruthy();
  await user.click(speed);
  const speeds = (await screen.findAllByRole('menuitemradio')).map(item => item.textContent);
  // An authored speed the presets lack is listed, so the menu never shows nothing checked.
  expect(speeds).toEqual(['0.25×', '0.5×', '0.75×', 'Normal', '1.25×', '1.5×', '2×', '3×']);
  // jsdom has no geometry for the submenu's pointer grace area; the keyboard path is the same handler.
  screen.getByRole('menuitemradio', { name: '2×' }).focus();
  await user.keyboard('{Enter}');
  expect(runtime.onSpeedChange).toHaveBeenLastCalledWith(2);
});

it('does not exist for a file without routines, loading or failed', () => {
  for (const runtime of [null, { clips: [] }, { clips: [], status: 'loading' }, { clips: [], error: 'sidecar failed' }]) {
    expect(animationControlsHaveContent(runtime)).toBe(false);
    const view = render(bar(clocks(), runtime));
    expect(view.container.innerHTML).toBe('');
    view.unmount();
  }
});

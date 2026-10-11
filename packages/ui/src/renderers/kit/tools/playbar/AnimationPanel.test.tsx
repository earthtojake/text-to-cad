import React from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import AnimationPanel from '../../../../../dist/renderers/kit/tools/playbar/AnimationPanel.js';
import { createAnimationClock } from '../../../../../dist/renderers/kit/tools/playbar/animationClock.js';

const restores: (() => void)[] = [];
function override(target: object, key: string, descriptor: PropertyDescriptor) {
  const previous = Object.getOwnPropertyDescriptor(target, key);
  Object.defineProperty(target, key, { configurable: true, ...descriptor });
  restores.push(() => previous ? Object.defineProperty(target, key, previous) : delete (target as any)[key]);
}
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  // A Select's listbox, which jsdom cannot lay out or point at.
  override(Element.prototype, 'scrollIntoView', { value() {} });
  for (const name of ['setPointerCapture', 'releasePointerCapture']) override(Element.prototype, name, { value() {} });
  override(Element.prototype, 'hasPointerCapture', { value: () => false });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); while (restores.length) restores.pop()!(); });

const TURN = { id: 'turn', label: 'Turn', duration: 8 };
const OPEN = { id: 'open', label: 'Open', duration: 3 };
const routines = (clips: object[], patch = {}) => ({ clips, activeClipId: 'turn', elapsedSec: 2, playing: false, speed: 1, loopEnabled: true,
  clock: createAnimationClock(), onPlayToggle: vi.fn(), onScrub: vi.fn(), onSpeedChange: vi.fn(), onLoopToggle: vi.fn(), onClipSelect: vi.fn(), ...patch });

it('is headed as every tool panel is — Animation, its settings, its X — over the transport, with no Routine row for one routine', async () => {
  const user = userEvent.setup();
  const runtime = routines([TURN]);
  const onClose = vi.fn();
  render(<AnimationPanel runtime={runtime} autoplay={false} onAutoplayChange={vi.fn()} onClose={onClose} />);
  const panel = screen.getByRole('region', { name: 'Animation controls' });
  expect(within(panel).getAllByRole('heading').map(heading => heading.textContent)).toEqual(['Animation']);
  expect(within(panel).getAllByRole('button').map(button => button.getAttribute('aria-label')))
    .toEqual(['Animation settings', 'Close animation controls', 'Play animation']);
  expect(within(panel).getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuetext')).toBe('2.00s of 8.00s');
  expect(within(panel).queryByRole('combobox', { name: 'Routine' })).toBeNull();
  await user.click(within(panel).getByRole('button', { name: 'Play animation' }));
  expect(runtime.onPlayToggle).toHaveBeenCalledOnce();
  await user.click(within(panel).getByRole('button', { name: 'Close animation controls' }));
  expect(onClose).toHaveBeenCalledOnce();
});

it('chooses the routine in a row above the transport when there are several', async () => {
  const user = userEvent.setup();
  const runtime = routines([TURN, OPEN]);
  render(<AnimationPanel runtime={runtime} autoplay={false} onAutoplayChange={vi.fn()} onClose={vi.fn()} />);
  const routine = screen.getByRole('combobox', { name: 'Routine' });
  expect(routine.textContent).toBe('Turn');
  expect(routine.compareDocumentPosition(screen.getByRole('button', { name: 'Play animation' })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  await user.click(routine);
  expect(screen.getAllByRole('option').map(option => option.textContent)).toEqual(['Turn', 'Open']);
  await user.click(screen.getByRole('option', { name: 'Open' }));
  expect(runtime.onClipSelect).toHaveBeenLastCalledWith('open');
});

it('holds Speed, Loop and Autoplay in its heading\'s settings, as preview\'s Playback settings do', async () => {
  const user = userEvent.setup();
  const runtime = routines([TURN], { speed: 0.5 });
  const onAutoplayChange = vi.fn();
  render(<AnimationPanel runtime={runtime} autoplay={false} onAutoplayChange={onAutoplayChange} onClose={vi.fn()} />);
  await user.click(screen.getByRole('button', { name: 'Animation settings' }));
  const menu = screen.getByRole('menu', { name: 'Animation settings' });
  expect(within(menu).getByRole('menuitem', { name: 'Animation speed: 0.5×' })).toBeTruthy();
  expect(within(menu).getAllByRole('menuitemcheckbox').map(item => item.textContent)).toEqual(['Loop', 'Autoplay']);
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'Loop' }));
  expect(runtime.onLoopToggle).toHaveBeenLastCalledWith(false);
  // Ticking a checkbox leaves the menu open.
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'Autoplay' }));
  expect(onAutoplayChange).toHaveBeenLastCalledWith(true);
  await user.click(within(menu).getByRole('menuitem', { name: 'Animation speed: 0.5×' }));
  // jsdom has no geometry for the submenu's pointer grace area; the keyboard path is the same handler.
  screen.getByRole('menuitemradio', { name: '2×' }).focus();
  await user.keyboard('{Enter}');
  expect(runtime.onSpeedChange).toHaveBeenLastCalledWith(2);
});

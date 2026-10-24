import React from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import AnimationSection from '../../../../../dist/renderers/kit/tools/playbar/AnimationSection.js';
import { createAnimationClock } from '../../../../../dist/renderers/kit/tools/playbar/animationClock.js';
import FileSidebar from '../../../../../dist/renderers/kit/tools/FileSidebar.js';

const restores: (() => void)[] = [];
function override(target: object, key: string, descriptor: PropertyDescriptor) {
  const previous = Object.getOwnPropertyDescriptor(target, key);
  Object.defineProperty(target, key, { configurable: true, ...descriptor });
  restores.push(() => previous ? Object.defineProperty(target, key, previous) : delete (target as any)[key]);
}
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  // A menu's content, which jsdom cannot lay out or point at.
  override(Element.prototype, 'scrollIntoView', { value() {} });
  for (const name of ['setPointerCapture', 'releasePointerCapture']) override(Element.prototype, name, { value() {} });
  override(Element.prototype, 'hasPointerCapture', { value: () => false });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); while (restores.length) restores.pop()!(); });

const TURN = { id: 'turn', label: 'Turn', duration: 8 };
const OPEN = { id: 'open', label: 'Open', duration: 3 };
// The section where it lives, the file sidebar's, its tile pressed: its Reset is in the heading
// the sidebar draws.
async function openSection(user: ReturnType<typeof userEvent.setup>, section: React.ReactElement) {
  const view = render(<FileSidebar layout={{ panels: {}, collapsed: {} }} onLayoutChange={() => {}}>{section}</FileSidebar>);
  await user.click(screen.getByRole('button', { name: 'Animation' }));
  return view;
}
const routines = (clips: object[], patch = {}) => ({ clips, activeClipId: 'turn', elapsedSec: 2, playing: false, speed: 1, loopEnabled: true,
  clock: createAnimationClock(), onPlayToggle: vi.fn(), onScrub: vi.fn(), onSpeedChange: vi.fn(), onLoopToggle: vi.fn(), onClipSelect: vi.fn(), onRelease: vi.fn(), ...patch });

it('one routine is its transport alone: Reset in the heading, then Play, the scrubber and its Playback settings', async () => {
  const user = userEvent.setup();
  const runtime = routines([TURN], { speed: 0.5 });
  const onAutoplayChange = vi.fn();
  const { container } = await openSection(user, <AnimationSection runtime={runtime} autoplay={false} onAutoplayChange={onAutoplayChange} />);
  expect(container.querySelector('[data-animation-routine]')).toBeNull();
  const transport = container.querySelector<HTMLElement>('[data-animation-transport]')!;
  expect(within(transport).getAllByRole('button').map(button => button.getAttribute('aria-label')))
    .toEqual(['Play animation', 'Playback settings']);
  expect(within(transport).getByRole('slider', { name: 'Animation time' })).toBeTruthy();
  // Reset puts the routine back at rest, and can only while it is under way.
  const reset = screen.getByRole('button', { name: 'Reset animation' });
  expect(reset.hasAttribute('disabled')).toBe(false);
  await user.click(reset);
  expect(runtime.onRelease).toHaveBeenCalledTimes(1);
  await user.click(within(transport).getByRole('button', { name: 'Play animation' }));
  expect(runtime.onPlayToggle).toHaveBeenCalledTimes(1);
  await user.click(within(transport).getByRole('button', { name: 'Playback settings' }));
  const menu = screen.getByRole('menu');
  expect(within(menu).getByRole('menuitem', { name: 'Animation speed: 0.5×' })).toBeTruthy();
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'Loop' }));
  expect(runtime.onLoopToggle).toHaveBeenLastCalledWith(false);
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'Autoplay' }));
  expect(onAutoplayChange).toHaveBeenLastCalledWith(true);
});

it('several routines lead with the one in hand, a list to choose another from, each with its duration', async () => {
  const user = userEvent.setup();
  const runtime = routines([TURN, OPEN]);
  await openSection(user, <AnimationSection runtime={runtime} autoplay={false} onAutoplayChange={vi.fn()} />);
  await user.click(screen.getByRole('button', { name: 'Routine: Turn' }));
  const menu = screen.getByRole('menu');
  expect(within(menu).getAllByRole('menuitemradio').map(item => [item.textContent, item.getAttribute('aria-checked')]))
    .toEqual([['Turn8.00s', 'true'], ['Open3.00s', 'false']]);
  await user.click(within(menu).getByRole('menuitemradio', { name: /^Open/ }));
  expect(runtime.onClipSelect).toHaveBeenLastCalledWith('open');
});

it('Reset is idle at rest: nothing playing and no time elapsed', async () => {
  await openSection(userEvent.setup(), <AnimationSection runtime={routines([TURN], { elapsedSec: 0 })} autoplay={false} onAutoplayChange={vi.fn()} />);
  expect(screen.getByRole('button', { name: 'Reset animation' }).hasAttribute('disabled')).toBe(true);
});

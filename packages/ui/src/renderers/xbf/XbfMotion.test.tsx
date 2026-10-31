import React, { useEffect, useRef, useState } from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FileSidebar from '../../../dist/renderers/kit/tools/FileSidebar.js';
import AnimationSection from '../../../dist/renderers/kit/tools/playbar/AnimationSection.js';
import XbfPositionSection, { useXbfPose } from '../../../dist/renderers/xbf/XbfPositionSection.js';
import { useXbfMotion } from '../../../dist/renderers/xbf/useXbfMotion.js';
import { useMotionExclusion } from '../../../dist/renderers/kit/tools/model-effects/motionExclusion.js';

// An engine document's motions played from the file sidebar's Motion section (`useXbfMotion.js`
// through the shell's `AnimationSection`), over Position as the renderer composes them: while a
// motion owns the pose its frames pose the scene and Position shows them read-only. A motion and
// the pose are one motion at a time (`motionExclusion.js`): taking the motion up puts the pose at
// rest, nothing set aside, so Reset leaves the model as built. Frames are driven by hand: the
// clock's animation frames are queued and run at chosen times.

Object.assign(globalThis, { React });
const restores: (() => void)[] = [];
function override(target: object, key: string, descriptor: PropertyDescriptor) {
  const previous = Object.getOwnPropertyDescriptor(target, key);
  Object.defineProperty(target, key, { configurable: true, ...descriptor });
  restores.push(() => previous ? Object.defineProperty(target, key, previous) : delete (target as any)[key]);
}
let frames: FrameRequestCallback[] = [];
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  override(HTMLElement.prototype, 'clientHeight', { get(this: HTMLElement) { return this.hasAttribute('data-file-sidebar-room') ? 600 : 0; } });
  override(Element.prototype, 'scrollIntoView', { value() {} });
  for (const name of ['setPointerCapture', 'releasePointerCapture']) override(Element.prototype, name, { value() {} });
  override(Element.prototype, 'hasPointerCapture', { value: () => false });
  frames = [];
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { frames.push(callback); return frames.length; });
  vi.stubGlobal('cancelAnimationFrame', () => {});
  vi.spyOn(performance, 'now').mockReturnValue(0);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); while (restores.length) restores.pop()!(); });

/** Runs the animation frames queued, as the browser would at `now` (ms). */
function frameAt(now: number) {
  const due = frames;
  frames = [];
  act(() => { for (const callback of due) callback(now); });
}

const I = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
// A hinge with one named configuration and two motions: `wave`, a linear sweep -10..60 over 2 s,
// and `swing`, from `open` back to as built, eased, over 1 s.
const kinematics = {
  schema: 'cadgen.kinematics/2', name: 'rig', ground: 0, loop: null, couplings: {},
  links: [{ name: 'base', instances: [0], matrix: I }, { name: 'arm', instances: [1], matrix: I }],
  pairs: [{ label: 'hinge', type: 'revolute', links: [0, 1], frames: [I, I], limits: [[-180, 180]], units: ['deg'] }],
  asBuilt: { hinge: 0 }, configurations: { open: { hinge: 90 } },
  motions: {
    wave: { duration: 2, ease: 'linear', keys: [{ t: 0, values: { hinge: -10 } }, { t: 2, values: { hinge: 60 } }] },
    swing: { duration: 1, ease: 'cubic', keys: [{ t: 0, configuration: 'open' }, { t: 1, values: { hinge: 0 } }] },
  },
};

// The renderer's composition (`XbfRenderer.jsx`): the scene posed by Position unless a motion owns
// the pose, by the motion's frames while it does, and by Position as it lets go; the pose and the
// motion one motion at a time.
function Harness({ mechanism = kinematics, scene }: { mechanism?: any, scene: { setPose: (values: any) => void } }) {
  const [layout, setLayout] = useState<any>({ panels: {}, collapsed: {} });
  const pose = useXbfPose(mechanism);
  const position = useRef(pose);
  position.current = pose;
  const motion = useXbfMotion(mechanism, (values: any) => scene.setPose(values || (position.current.applied ? position.current.values : null)));
  const owns = useRef(false);
  owns.current = Boolean(motion?.enabled);
  useMotionExclusion('arm.xbf', {
    position: { applied: pose.applied, reset: pose.reset },
    motion: { applied: Boolean(motion?.enabled), reset: () => motion?.onRelease() }
  });
  useEffect(() => { if (!owns.current) scene.setPose(pose.applied ? pose.values : null); }, [pose.values, pose.applied]);
  return <FileSidebar layout={layout} onLayoutChange={(patch: any) => setLayout((current: any) => ({ ...current, ...patch }))}>
    <XbfPositionSection kinematics={mechanism} motion={motion?.enabled ? motion : null} values={pose.values} couplings={pose.couplings}
      preset={pose.preset} changed={pose.applied} onValues={pose.setValues} onPreset={pose.choosePreset} onReset={pose.reset} />
    {motion ? <AnimationSection runtime={motion} autoplay={false} onAutoplayChange={() => {}} /> : null}
  </FileSidebar>;
}

const lastPose = (scene: { setPose: ReturnType<typeof vi.fn> }) => scene.setPose.mock.calls.at(-1)?.[0] ?? null;
const hingeAt = (scene: { setPose: ReturnType<typeof vi.fn> }) => lastPose(scene)?.hinge?.[0] ?? null;
const tiles = () => within(screen.getByRole('group', { name: 'File sidebar' })).getAllByRole('button').map(button => button.getAttribute('aria-label'));

it('a document with no motions has no Motion section', () => {
  const { motions: _none, ...still } = kinematics;
  render(<Harness mechanism={still} scene={{ setPose: vi.fn() }} />);
  expect(tiles()).toEqual(['Position']);
});

it("the Motion section lists the document's motions with their durations, and plays, pauses, scrubs, loops and speeds them", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0, skipHover: true });
  const scene = { setPose: vi.fn() };
  render(<Harness scene={scene} />);
  expect(tiles()).toEqual(['Position', 'Motion']);
  await user.click(screen.getByRole('button', { name: 'Motion' }));
  const panel = screen.getByRole('region', { name: 'Motion' });
  expect(within(panel).getByRole('heading').textContent).toBe('Motion');
  // At rest as the file opens: nothing to reset, the scene as Position has it.
  expect((screen.getByRole('button', { name: 'Reset motion' }) as HTMLButtonElement).disabled).toBe(true);
  expect(lastPose(scene)).toBeNull();
  await user.click(within(panel).getByRole('button', { name: 'Motion: wave' }));
  expect(within(screen.getByRole('menu')).getAllByRole('menuitemradio').map(item => item.textContent))
    .toEqual(['wave2.00s', 'swing1.00s']);
  await user.keyboard('{Escape}');

  // Scrubbed to its end: the sweep's last key.
  const scrubber = within(panel).getByRole('slider', { name: 'Animation time' });
  fireEvent.keyDown(scrubber, { key: 'End' });
  expect(hingeAt(scene)).toBe(60);
  // Played from its end, it starts again from 0; half a second in, a quarter of the sweep.
  await user.click(within(panel).getByRole('button', { name: 'Play motion' }));
  expect(hingeAt(scene)).toBe(-10);
  frameAt(500);
  expect(hingeAt(scene)).toBeCloseTo(7.5, 9);
  // Looping (as every motion opens): past its end it wraps and keeps playing.
  frameAt(2250);
  expect(hingeAt(scene)).toBeCloseTo(-10 + 35 * 0.25, 9);
  // Paused, its frame stays.
  await user.click(within(panel).getByRole('button', { name: 'Pause motion' }));
  expect(hingeAt(scene)).toBeCloseTo(-10 + 35 * 0.25, 9);
  expect((screen.getByRole('button', { name: 'Reset motion' }) as HTMLButtonElement).disabled).toBe(false);

  // Speed 2x and Loop off: a second of clock is two of the motion (played from the frame it is
  // paused at, the clock reading 0 as it starts), and it stops at its end.
  await user.click(within(panel).getByRole('button', { name: 'Playback settings' }));
  await user.click(await screen.findByRole('menuitemcheckbox', { name: 'Loop' }));
  await user.click(await screen.findByRole('menuitem', { name: 'Animation speed: 1×' }));
  // jsdom has no geometry for the submenu's pointer grace area; the keyboard path is the same handler.
  (await screen.findByRole('menuitemradio', { name: '2×' })).focus();
  await user.keyboard('{Enter}');
  if (screen.queryByRole('menu')) await user.keyboard('{Escape}');
  await user.click(within(panel).getByRole('button', { name: 'Play motion' }));
  frameAt(250);
  expect(hingeAt(scene)).toBeCloseTo(-10 + 35 * 0.75, 9);
  frameAt(2000);
  expect(hingeAt(scene)).toBe(60);
  expect(within(panel).getByRole('button', { name: 'Play motion' })).toBeTruthy();
  expect(frames).toEqual([]);

  // Another motion is chosen at its start, at rest until it plays: `swing` opens at `open`.
  await user.click(within(panel).getByRole('button', { name: 'Motion: wave' }));
  await user.click(screen.getByRole('menuitemradio', { name: /^swing/ }));
  expect(hingeAt(scene)).toBe(90);
});

it("a motion replaces Position's pose, shown read-only while it owns it, and Reset leaves the model as built, nothing set aside", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0, skipHover: true });
  const scene = { setPose: vi.fn() };
  render(<Harness scene={scene} />);
  // Position first: the `open` configuration.
  await user.click(screen.getByRole('button', { name: 'Position' }));
  await user.click(screen.getByRole('button', { name: 'Pose: Default' }));
  await user.click(screen.getByRole('menuitemradio', { name: 'open' }));
  expect(hingeAt(scene)).toBe(90);

  // The motion takes the pose: half a second of `wave` is 7.5 degrees, and Position says so, read-only.
  await user.click(screen.getByRole('button', { name: 'Motion' }));
  const motionPanel = screen.getByRole('region', { name: 'Motion' });
  await user.click(within(motionPanel).getByRole('button', { name: 'Play motion' }));
  frameAt(500);
  await user.click(within(motionPanel).getByRole('button', { name: 'Pause motion' }));
  expect(hingeAt(scene)).toBeCloseTo(7.5, 9);
  await user.click(screen.getByRole('button', { name: 'Position' }));
  const position = screen.getByRole('region', { name: 'Position controls' });
  const field = within(position).getByRole('textbox', { name: 'hinge slider value' }) as HTMLInputElement;
  expect(field.value).toBe('7.50°');
  expect(field.disabled).toBe(true);
  expect(within(position).getByRole('slider', { name: 'hinge' }).getAttribute('data-disabled')).not.toBeNull();
  expect((within(position).getByRole('button', { name: 'Pose: Custom' }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByRole('button', { name: 'Reset position' }) as HTMLButtonElement).disabled).toBe(true);

  // Reset lets go: `open` was put at rest as the motion took the pose, so the model is as built.
  await user.click(screen.getByRole('button', { name: 'Motion' }));
  await user.click(screen.getByRole('button', { name: 'Reset motion' }));
  expect(lastPose(scene)).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Position' }));
  const again = screen.getByRole('region', { name: 'Position controls' });
  const after = within(again).getByRole('textbox', { name: 'hinge slider value' }) as HTMLInputElement;
  expect([after.value, after.disabled]).toEqual(['0.00°', false]);
  expect(within(again).getByRole('button', { name: 'Pose: Default' })).toBeTruthy();
});

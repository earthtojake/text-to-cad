import React, { useEffect, useRef, useState } from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FlatPanel from '../../../dist/renderers/kit/shell/FlatPanel.js';
import { DEFAULT_PANEL_WIDTH } from '../../../dist/renderers/kit/shell/sidebars.js';
import AnimationSection, { JointsMotionContext } from '../../../dist/renderers/kit/tools/playbar/AnimationSection.js';
import XbfPositionSection, { useXbfPose } from '../../../dist/renderers/xbf/XbfPositionSection.js';
import { useXbfMotion } from '../../../dist/renderers/xbf/useXbfMotion.js';
import { createAnimationClock } from '../../../dist/renderers/kit/tools/playbar/animationClock.js';
import { useMotionExclusion } from '../../../dist/renderers/kit/tools/model-effects/motionExclusion.js';

// An engine document's motions played from the tools view's Animation tab (`useXbfMotion.js` through the
// shell's `AnimationSection.jsx`), over Position as the
// renderer composes them: while a motion owns the pose its frames pose the scene and Position shows them
// read-only. A motion and the pose are one motion at a time (`motionExclusion.js`): taking the motion up
// puts the pose at rest, nothing set aside, so scrubbing back to the start leaves the model as built. Frames are driven by hand: the
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
  // As the shell draws them: Position a tab of the view's panel, the motions the Animation tab's (here drawn on its
  // own, so its controls are on screen beside Position's).
  return <div style={{ position: 'relative' }}>
    <FlatPanel mode="docked" open onClose={() => {}} label="Model panel" searchLabel="Search the model"
      sections={<XbfPositionSection kinematics={mechanism} motion={motion?.enabled ? motion : null} values={pose.values} couplings={pose.couplings}
        preset={pose.preset} onValues={pose.setValues} onPreset={pose.choosePreset} onReset={pose.reset} />}
      tab="position" onTabChange={() => {}} width={DEFAULT_PANEL_WIDTH} maxWidth={480} onWidthChange={() => {}} focusSearch={0} />
    <AnimationSection runtime={motion} kind="motion" />
  </div>;
}

const lastPose = (scene: { setPose: ReturnType<typeof vi.fn> }) => scene.setPose.mock.calls.at(-1)?.[0] ?? null;
const hingeAt = (scene: { setPose: ReturnType<typeof vi.fn> }) => lastPose(scene)?.hinge?.[0] ?? null;
const bar = () => document.querySelector<HTMLElement>('[data-animation-section]')!;
// The Animation tab's controls, the same set at rest, playing and paused: nothing comes or goes.
const tab = () => bar().closest<HTMLElement>('[data-tool-panel]')!;
const controls = () => [...tab().querySelectorAll('[data-animation-play], [data-animation-reset], [role=slider], [data-animation-speed], [data-animation-loop]')]
  .map(control => control.getAttribute('aria-label') || control.textContent).map(name => name === 'Pause motion' ? 'Play motion' : name!.split(':')[0]);
const CONTROLS = ['Play motion', 'Animation time', 'Animation speed', 'Loop', 'Reset'];
const toStart = () => fireEvent.keyDown(within(bar()).getByRole('slider', { name: 'Animation time' }), { key: 'Home' });
// The routines' dropdown (Clip), above the playbar: each routine by its name, the one in hand checked.
async function clips(user: ReturnType<typeof userEvent.setup>) {
  await user.click(bar().querySelector<HTMLElement>('[data-animation-clip-menu]')!);
  const listed = (await screen.findAllByRole('menuitemradio')).map(item => [item.textContent, item.getAttribute('aria-checked')]);
  await user.keyboard('{Escape}');
  return listed;
}
async function chooseClip(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(bar().querySelector<HTMLElement>('[data-animation-clip-menu]')!);
  await user.click((await screen.findAllByRole('menuitemradio')).find(item => item.textContent!.startsWith(name))!);
}

// A tab and its clip row use the source format's own words: a glTF's `animations` are Animation and Animation; a mechanism's
// motions (an ISO 10303-105 interpolated_configuration_sequence) are Motion and Sequence.
it('a GLB shows Animation and Animation, a mechanism Motion and Sequence', () => {
  const words = () => [document.querySelector('[data-tool-panel-heading] h3')?.textContent, bar().querySelector('[data-panel-select-row]')!.firstElementChild!.textContent];
  const runtime = { clips: [{ id: 'a', label: 'Spin', duration: 1 }], activeClipId: 'a', clock: createAnimationClock(), enabled: true, playing: false, elapsedSec: 0, speed: 1, loopEnabled: true };
  const { unmount } = render(<AnimationSection runtime={runtime} />);
  expect(words()).toEqual(['Animation', 'Animation']);
  unmount();
  render(<AnimationSection runtime={{ ...runtime, noun: 'Motion' }} kind="motion" />);
  expect(words()).toEqual(['Motion', 'Sequence']);
});

it('a document with no motions has no Animation section', () => {
  const { motions: _none, ...still } = kinematics;
  render(<Harness mechanism={still} scene={{ setPose: vi.fn() }} />);
  expect(document.querySelector('[data-animation-section]')).toBeNull();
});

it("the Animation section lists the document's motions by name, its time and its settings, and it plays, pauses, scrubs, loops, speeds and stops them", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0, skipHover: true });
  const scene = { setPose: vi.fn() };
  render(<Harness scene={scene} />);
  // At rest as the file opens: the tab, the scene as Position has it.
  expect(bar().closest('[data-tool-panel]')!.getAttribute('aria-label')).toBe('Motion playback');
  expect([controls(), lastPose(scene)]).toEqual([CONTROLS, null]);
  expect(await clips(user)).toEqual([['wave', 'true'], ['swing', 'false']]);
  expect([within(bar()).getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuetext'), bar().querySelector('[data-animation-speed]')!.getAttribute('aria-label'),
    within(bar()).getByRole('switch', { name: 'Loop' }).getAttribute('aria-checked')])
    .toEqual(['0.00s of 2.00s', 'Animation speed: 1×', 'true']);
  // Reset, the tab's, at its bottom right, is idle at the start; Loop is a label and a switch, no icon; the motions' row is labelled "Sequence".
  expect([within(tab()).getByRole('button', { name: 'Reset' }).hasAttribute('disabled'), bar().querySelectorAll('[data-panel-switch-row] svg').length,
    bar().querySelector('[data-panel-select-row]')!.firstElementChild!.textContent])
    .toEqual([true, 0, 'Sequence']);

  // Play plays the motion in hand, its controls the same; half a second in, a quarter of the sweep.
  await user.click(within(bar()).getByRole('button', { name: 'Play motion' }));
  expect(hingeAt(scene)).toBe(-10);
  expect(controls()).toEqual(CONTROLS);
  frameAt(500);
  expect(hingeAt(scene)).toBeCloseTo(7.5, 9);
  expect(within(bar()).getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuetext')).toBe('0.50s of 2.00s');
  // Looping (as every motion opens): past its end it wraps and keeps playing.
  frameAt(2250);
  expect(hingeAt(scene)).toBeCloseTo(-10 + 35 * 0.25, 9);
  // Paused mid-motion, its frame stays, the controls the same.
  await user.click(within(bar()).getByRole('button', { name: 'Pause motion' }));
  expect(hingeAt(scene)).toBeCloseTo(-10 + 35 * 0.25, 9);
  expect(controls()).toEqual(CONTROLS);

  // Scrubbed to its end: the sweep's last key.
  fireEvent.keyDown(within(bar()).getByRole('slider', { name: 'Animation time' }), { key: 'End' });
  expect(hingeAt(scene)).toBe(60);
  expect(within(bar()).getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuetext')).toBe('2.00s of 2.00s');

  // Speed 2x and Loop off: a second of clock is two of the motion, played from its end (so from 0), and it stops at its end.
  await user.click(within(bar()).getByRole('switch', { name: 'Loop' }));
  await user.click(bar().querySelector<HTMLElement>('[data-animation-speed]')!);
  await user.click(await screen.findByRole('menuitemradio', { name: '2×' }));
  await user.click(within(bar()).getByRole('button', { name: 'Play motion' }));
  frameAt(250);
  expect(hingeAt(scene)).toBeCloseTo(-10 + 35 * 0.5, 9);
  frameAt(2000);
  expect(hingeAt(scene)).toBe(60);
  expect(within(bar()).getByRole('button', { name: 'Play motion' })).toBeTruthy();
  expect(frames).toEqual([]);
  // Reset, the tab's, puts it back at its start and the model at rest, and then is idle.
  await user.click(within(tab()).getByRole('button', { name: 'Reset' }));
  expect([lastPose(scene), within(bar()).getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuetext'),
    within(tab()).getByRole('button', { name: 'Reset' }).hasAttribute('disabled')]).toEqual([null, '0.00s of 2.00s', true]);

  // Another motion chosen in the dropdown plays from its start: `swing` opens at `open`, checked as the one in hand.
  await chooseClip(user, 'swing');
  expect(hingeAt(scene)).toBe(90);
  expect(await clips(user)).toEqual([['wave', 'false'], ['swing', 'true']]);
  expect(within(bar()).getByRole('button', { name: 'Pause motion' })).toBeTruthy();

  // Paused at its start, it lets go: the model as built (swing's first frame is not the rest pose).
  await user.click(within(bar()).getByRole('button', { name: 'Pause motion' }));
  expect([lastPose(scene), controls()]).toEqual([null, CONTROLS]);
  // A frame already asked for draws nothing once it has stopped.
  frameAt(3000);
  expect([lastPose(scene), frames]).toEqual([null, []]);
});

it("a paused motion's frame is Joints' to take over: every control stays live, an edit lets the motion go and starts from the frame, and scrubbed back to its start the model is as built", async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0, skipHover: true });
  const scene = { setPose: vi.fn() };
  render(<Harness scene={scene} />);
  // Position first: the `open` configuration, from the pose row labelled Position.
  const row = document.querySelector<HTMLElement>('[data-pose-row]')!;
  expect(row.querySelector('[data-pose-label]')!.textContent).toBe('Position');
  await user.click(screen.getByRole('button', { name: 'Position: Default' }));
  await user.click(screen.getByRole('menuitemradio', { name: 'open' }));
  expect(hingeAt(scene)).toBe(90);

  // The motion takes the pose: half a second of `wave` is 7.5 degrees, and Joints shows it, nothing disabled.
  await user.click(within(bar()).getByRole('button', { name: 'Play motion' }));
  frameAt(500);
  await user.click(within(bar()).getByRole('button', { name: 'Pause motion' }));
  expect(hingeAt(scene)).toBeCloseTo(7.5, 9);
  // The tab's name carries its changed mark (", changed") while its Reset is on.
  const position = () => screen.getByRole('tabpanel', { name: /^Joints\b/ });
  const field = () => within(position()).getByRole('textbox', { name: 'hinge slider value' }) as HTMLInputElement;
  expect([field().value, field().disabled]).toEqual(['7.50', false]);
  expect(within(position()).getByRole('slider', { name: 'hinge' }).getAttribute('data-disabled')).toBeNull();
  expect((within(position()).getByRole('button', { name: 'Position: Custom' }) as HTMLButtonElement).disabled).toBe(false);

  // A step of the slider from the frame: the motion let go of, the pose one step on from 7.5, nothing jumping.
  fireEvent.keyDown(within(position()).getByRole('slider', { name: 'hinge' }), { key: 'ArrowRight' });
  expect(hingeAt(scene)).toBeGreaterThan(7.5);
  expect(hingeAt(scene)).toBeLessThan(8);
  expect(within(bar()).getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuenow')).toBe('0');
  // A frame asked for before it let go draws nothing now: the pose is Joints'.
  const held = hingeAt(scene);
  frameAt(3000);
  expect(hingeAt(scene)).toBe(held);

  // Played again and paused: a named position chosen lets it go and sets that position outright.
  await user.click(within(bar()).getByRole('button', { name: 'Play motion' }));
  frameAt(3500);
  await user.click(within(bar()).getByRole('button', { name: 'Pause motion' }));
  await user.click(within(position()).getByRole('button', { name: 'Position: Custom' }));
  await user.click(screen.getByRole('menuitemradio', { name: 'open' }));
  expect(hingeAt(scene)).toBe(90);
  expect(within(position()).getByRole('button', { name: 'Position: open' })).toBeTruthy();

  // Played and paused once more, then scrubbed to its start: let go, and `open` was put at rest as it took the pose.
  await user.click(within(bar()).getByRole('button', { name: 'Play motion' }));
  frameAt(4000);
  await user.click(within(bar()).getByRole('button', { name: 'Pause motion' }));
  toStart();
  expect(lastPose(scene)).toBeNull();
  expect([field().value, field().disabled]).toEqual(['0.00', false]);
  expect(within(position()).getByRole('button', { name: 'Position: Default' })).toBeTruthy();
});

// A mechanism with both joints and motions has ONE tab, "Joints" (the shell hands its motion to the Joints tab,
// `JointsMotionContext`): the motion's controls first, a hairline and the joints under their heading, and one Reset at
// the bottom right that puts back both, on while either is off its start.
function Merged({ scene }: { scene: { setPose: (values: any) => void } }) {
  const pose = useXbfPose(kinematics);
  const position = useRef(pose);
  position.current = pose;
  const motion = useXbfMotion(kinematics, (values: any) => scene.setPose(values || (position.current.applied ? position.current.values : null)));
  useEffect(() => { if (!motion?.enabled) scene.setPose(pose.applied ? pose.values : null); }, [pose.values, pose.applied]);
  return <JointsMotionContext.Provider value={{ runtime: motion, disabled: false }}>
    <FlatPanel mode="docked" open onClose={() => {}} label="Model panel" searchLabel="Search the model"
      sections={<XbfPositionSection kinematics={kinematics} motion={motion?.enabled ? motion : null} values={pose.values} couplings={pose.couplings}
        preset={pose.preset} onValues={pose.setValues} onPreset={pose.choosePreset} onReset={pose.reset} />}
      tab="position" onTabChange={() => {}} width={DEFAULT_PANEL_WIDTH} maxWidth={480} onWidthChange={() => {}} focusSearch={0} />
  </JointsMotionContext.Provider>;
}

it('a mechanism with joints and motions has ONE "Joints" tab: the motion first, the joints under a hairline, one Reset for both', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0, skipHover: true });
  const scene = { setPose: vi.fn() };
  render(<Merged scene={scene} />);
  const panel = screen.getByRole('tabpanel', { name: /^Joints\b/ });
  // In order: the motion's controls, the hairline (no heading: the tab is "Joints"), the Position row, a joint's slider; one Reset, the tab's.
  const order = [...panel.querySelectorAll('[data-joints-motion], [data-joints-rule], [data-pose-row], [role=slider][aria-label=hinge], [data-pose-reset], [data-animation-reset]')]
    .map(node => node.hasAttribute('data-joints-motion') ? 'motion' : node.hasAttribute('data-joints-rule') ? `rule:${node.textContent}`
      : node.hasAttribute('data-pose-row') ? 'position' : node.hasAttribute('data-pose-reset') ? 'reset' : node.hasAttribute('data-animation-reset') ? 'transport-reset' : 'joint');
  expect([document.querySelectorAll('[data-tool-panel]').length, order, panel.querySelector('[data-animation-transport] [data-animation-reset]')])
    .toEqual([1, ['motion', 'rule:', 'position', 'joint', 'reset'], null]);
  const reset = () => within(panel).getByRole('button', { name: 'Reset joints' }) as HTMLButtonElement;
  expect(reset().disabled).toBe(true);
  // The motion played and paused: Reset on; pressed, the motion back at its start and the joints as built.
  await user.click(within(panel).getByRole('button', { name: 'Play motion' }));
  frameAt(500);
  await user.click(within(panel).getByRole('button', { name: 'Pause motion' }));
  expect([reset().disabled, hingeAt(scene)]).toEqual([false, 7.5]);
  await user.click(reset());
  expect([reset().disabled, lastPose(scene), within(panel).getByRole('slider', { name: 'Animation time' }).getAttribute('aria-valuenow')]).toEqual([true, null, '0']);
  // A joint set by its named position: Reset on again, and it puts the joints back.
  await user.click(within(panel).getByRole('button', { name: 'Position: Default' }));
  await user.click(screen.getByRole('menuitemradio', { name: 'open' }));
  expect([reset().disabled, hingeAt(scene)]).toEqual([false, 90]);
  await user.click(reset());
  expect([reset().disabled, within(panel).getByRole('button', { name: 'Position: Default' }) !== null]).toEqual([true, true]);
});

// A parameter edit builds the model again (a preview, then a saved version): a mechanism with the same joints keeps the
// Joints pose, one whose joints changed starts at Default. The pose is keyed by the mechanism, never by its object.
it('the Joints pose stays across a rebuild with the same joints, and goes back to Default when the joints changed', () => {
  let pose: ReturnType<typeof useXbfPose>;
  function Pose({ mechanism }: { mechanism: any }) { pose = useXbfPose(mechanism); return null; }
  const { rerender } = render(<Pose mechanism={kinematics} />);
  act(() => pose.choosePreset('open'));
  expect([pose.applied, pose.preset, pose.values?.hinge?.[0]]).toEqual([true, 'open', 90]);
  // The same joints in a new document (a parameter changed elsewhere): the pose is kept.
  rerender(<Pose mechanism={JSON.parse(JSON.stringify(kinematics))} />);
  expect([pose.preset, pose.values?.hinge?.[0]]).toEqual(['open', 90]);
  // A joint's limits changed: Default.
  const changed = JSON.parse(JSON.stringify(kinematics));
  changed.pairs[0].limits = [[-90, 90]];
  rerender(<Pose mechanism={changed} />);
  expect([pose.applied, pose.preset, pose.values?.hinge?.[0]]).toEqual([false, '__default__', 0]);
});

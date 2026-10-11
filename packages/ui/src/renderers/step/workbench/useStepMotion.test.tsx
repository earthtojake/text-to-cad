import type { ReactNode } from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { AnimationClockProvider, createAnimationClock } from '../../../../dist/renderers/step/workbench/animationClockStore.js';
import { stepPosableHandles } from '../../../../dist/renderers/step/workbench/jointHandles.js';
import { useStepMotion } from '../../../../dist/renderers/step/workbench/useStepMotion.js';

// Every load of a routine's keyframes is counted; what loads is the sidecar's own, one routine, `swing`.
const loads = vi.hoisted(() => ({ count: 0 }));
vi.mock('@text-to-cad/core/common/animationRuntime.js', async (importOriginal) => {
  const actual = await importOriginal<{ loadSourceAnimation: (...args: unknown[]) => Promise<unknown> }>();
  return { ...actual, loadSourceAnimation: (...args: unknown[]) => {
    loads.count += 1;
    return actual.loadSourceAnimation(...args);
  } };
});

afterEach(() => { cleanup(); loads.count = 0; });

// The articulation cadgen writes for one revolute mate `swing` (0..120 deg) carrying the flap.
const swing = { id: 'swing', min: 0, max: 120 };
const OPEN = { open: { swing: 90 } };
function articulationOf(mates: { id: string; min: number; max: number }[], poses: object) {
  return { schemaVersion: 2,
    controls: mates.map(mate => ({ id: mate.id, label: mate.id, unit: 'deg', min: mate.min, max: mate.max, default: 0 })),
    joints: mates.map(mate => ({ id: mate.id, parent: null, kind: 'revolute', origin: [0, 0, 0], axis: [0, 0, 1], turn: { bias: 0, terms: [[mate.id, 1]] } })),
    carries: Object.fromEntries(mates.map(mate => [mate.id, ['o1.2']])),
    handles: mates.map(mate => ({ id: mate.id, joint: mate.id, dof: 'turn', control: mate.id, weight: 1, label: mate.id, unit: 'deg', min: mate.min, max: mate.max })),
    poses, opening: Object.fromEntries(mates.map(mate => [mate.id, 0])) };
}
// The flap turning a quarter turn about +Z over the routine's 4 s, as the build bakes it.
const SWING_CLIP = { id: 'swing', label: 'Swing', duration: 4, loop: true, tracks: [{ targets: ['o1.2'], times: [0, 4], pivot: [0, 0, 0],
  transform: [[0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, Math.PI / 16, 0],
    [0, 0, 0, 0, 0, Math.SQRT1_2, Math.SQRT1_2, 0, 0, 0, 0, 0, Math.SQRT1_2 * Math.PI / 16, -Math.SQRT1_2 * Math.PI / 16]] }] };
// One save of hinge.step as the catalog lists it: new STEP bytes, and the sidecar written again
// beside them (a new version on its URL, bound to those bytes), resolved into the articulation of
// its mates and named poses, and its routines (`routine` is their keyframes' hash, which the
// catalog lists as `animationHash`). No mates: no articulation; no routine: no animation.
function saved(revision: number, { mates = [swing], poses = OPEN, routine = '', clips = [SWING_CLIP] }:
  { mates?: { id: string; min: number; max: number }[]; poses?: object; routine?: string; clips?: object[] } = {}) {
  const documentHash = String(revision).repeat(64);
  return { file: 'hinge.step', kind: 'part', hash: `tree-${revision}`, documentHash,
    ...(mates.length ? { poseUrl: `/__cad/asset?file=hinge.step.json&v=${revision}`, articulation: articulationOf(mates, poses) } : {}),
    ...(routine ? { animation: { clips }, animationHash: routine } : {}) };
}

/**
 * The hook over one entry, as StepSurface mounts it; at every render, `offered` is whether Position
 * is offered (its `poseAvailable`) and `listed` how many routines the Animation tool has.
 */
function mount(entry: ReturnType<typeof saved>) {
  const clock = createAnimationClock();
  const offered: boolean[] = [];
  const listed: number[] = [];
  const hook = renderHook(({ entry }) => {
    const motion = useStepMotion({ entry, fileKey: entry.file, resources: null,
      readStored: () => ({ pose: null }), clipboard: null, reportError: () => {} });
    offered.push(stepPosableHandles(motion.definition).length > 0);
    listed.push(motion.animationControls.clips.length);
    return motion;
  }, { initialProps: { entry },
    wrapper: ({ children }: { children: ReactNode }) => <AnimationClockProvider value={clock}>{children}</AnimationClockProvider> });
  return { ...hook, offered, listed };
}
const loaded = async (result: { current: { definition: { url?: string } | null } }, revision: number) =>
  waitFor(() => expect(result.current.definition?.url).toMatch(new RegExp(`v=${revision}$`)));

it('a rebuild keeps Position, and the pose set on it, while its sidecar is read again and its joints are the same; changed joints start over', async () => {
  const { result, rerender, offered } = mount(saved(1));
  await loaded(result, 1);
  act(() => result.current.onParameterChange('swing', 30));

  offered.length = 0;
  rerender({ entry: saved(2) });
  await loaded(result, 2);
  expect(offered).not.toContain(false);
  expect(result.current.parameterValues).toEqual({ swing: 30 });

  // A save that changed the joint starts it at the new default: the old pose is not fitted onto it,
  // though 30° would still fit inside the new range.
  rerender({ entry: saved(3, { mates: [{ ...swing, max: 40 }] }) });
  await loaded(result, 3);
  expect(result.current.parameterValues).toEqual({ swing: 0 });

  // A save that takes the mates out takes Position with them.
  rerender({ entry: saved(4, { mates: [] }) });
  expect(stepPosableHandles(result.current.definition)).toEqual([]);
});

it('a rebuild keeps the named pose chosen while the joints and named poses are the same, and drops it with the pose when they changed', async () => {
  const { result, rerender } = mount(saved(1));
  await loaded(result, 1);
  act(() => result.current.positionControls.onApplyPose('open'));
  const chosen = () => [result.current.positionControls.activePose, result.current.parameterValues];
  expect(chosen()).toEqual(['open', { swing: 90 }]);

  rerender({ entry: saved(2) });
  await loaded(result, 2);
  expect(chosen()).toEqual(['open', { swing: 90 }]);

  // The named pose itself changed: the pose starts over, and the dropdown names none.
  rerender({ entry: saved(3, { poses: { open: { swing: 45 } } }) });
  await loaded(result, 3);
  expect(chosen()).toEqual(['', { swing: 0 }]);
});

it('an update that leaves the routine as it was neither stops nor rewinds it, and keeps the pose it set aside; a changed routine is loaded again, at rest', async () => {
  const { result, rerender } = mount(saved(1, { routine: 'swing-1' }));
  await loaded(result, 1);
  await waitFor(() => expect(result.current.animationControls.clips).toHaveLength(1));
  act(() => result.current.onParameterChange('swing', 30));
  // Play takes the pose: Position's values are set aside, and the routine plays from rest.
  act(() => result.current.onPlayToggle());
  expect([result.current.animationState.playing, result.current.parameterValues]).toEqual([true, { swing: 0 }]);

  rerender({ entry: saved(2, { routine: 'swing-1' }) });
  await loaded(result, 2);
  expect(loads.count).toBe(1);
  expect(result.current.animationState).toMatchObject({ activeClipId: 'swing', enabled: true, playing: true });
  expect(result.current.animationControls.clips).toHaveLength(1);
  // Leaving preview hands the pose back as Position left it, across the update.
  act(() => result.current.releaseAnimation());
  expect(result.current.parameterValues).toEqual({ swing: 30 });

  // A routine the save changed is loaded again, and is at rest.
  act(() => result.current.onPlayToggle());
  rerender({ entry: saved(3, { routine: 'swing-2' }) });
  await waitFor(() => expect(loads.count).toBe(2));
  await waitFor(() => expect(result.current.animationControls.clips).toHaveLength(1));
  expect(result.current.animationState.playing).toBe(false);
});

it('a changed routine is read again behind the routines in hand: the model goes to rest, Position gets its values back, and the routine chosen stays chosen', async () => {
  const flutter = { ...SWING_CLIP, id: 'flutter', label: 'Flutter' };
  const { result, rerender, listed } = mount(saved(1, { routine: 'pair-1', clips: [SWING_CLIP, flutter] }));
  await loaded(result, 1);
  await waitFor(() => expect(result.current.animationControls.clips).toHaveLength(2));
  act(() => result.current.onParameterChange('swing', 30));
  act(() => result.current.animationControls.onClipSelect('flutter'));
  act(() => result.current.onPlayToggle());
  expect(result.current.animationState).toMatchObject({ activeClipId: 'flutter', playing: true });

  listed.length = 0;
  rerender({ entry: saved(2, { routine: 'pair-2', clips: [SWING_CLIP, flutter] }) });
  await waitFor(() => expect(loads.count).toBe(2));
  await waitFor(() => expect(result.current.animationControls.status).toBe('ready'));
  // The routines never went while the new ones loaded, so the Animation tool stays up over them.
  expect(listed).not.toContain(0);
  expect(result.current.animationState).toMatchObject({ activeClipId: 'flutter', enabled: false, playing: false, elapsedSec: 0 });
  expect(result.current.parameterValues).toEqual({ swing: 30 });
});

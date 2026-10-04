import type { ReactNode } from 'react';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { SOURCE_SIDECAR_SCHEMA_VERSION } from '@text-to-cad/core/common/sourceSidecar.js';
import { AnimationClockProvider, createAnimationClock } from '../../../../dist/renderers/step/workbench/animationClockStore.js';
import { stepPosableDofs } from '../../../../dist/renderers/step/workbench/jointHandles.js';
import { useStepMotion } from '../../../../dist/renderers/step/workbench/useStepMotion.js';

// A routine's source is compiled by importing it, which this realm cannot do: each compile is
// counted, and what it compiles to is one routine, `swing`.
const compiled = vi.hoisted(() => ({ loads: 0 }));
vi.mock('@text-to-cad/core/common/renderModule.js', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  const { normalizeAnimationClips } = await import('@text-to-cad/core/common/animationRuntime.js');
  return { ...actual, loadSourceAnimation: async () => {
    compiled.loads += 1;
    return { clips: normalizeAnimationClips({ swing: { label: 'Swing', duration: 4, loop: true, update() {} } }) };
  } };
});

afterEach(() => { cleanup(); compiled.loads = 0; });

const swing = { name: 'swing', kind: 'revolute', parent: '#base', child: '#flap',
  axis: { origin: [0, 0, 0], dir: [0, 0, 1] }, limits: { value: [0, 120] } };
const OPEN = { open: { swing: 90 } };
// One save of hinge.step as the catalog lists it: new STEP bytes, and the sidecar written again
// beside them (a new version on its URL, bound to those bytes), with its mates, named poses and
// routine (`routine` is its source's hash, which the catalog lists as `animationHash`). No mates and
// no routine: no sidecar.
function saved(revision: number, { mates = [swing], poses = OPEN, routine = '' }: { mates?: object[]; poses?: object; routine?: string } = {}) {
  const documentHash = String(revision).repeat(64);
  const sidecar = { schemaVersion: SOURCE_SIDECAR_SCHEMA_VERSION, documentHash,
    ...(mates.length ? { kinematics: { mates, poses } } : {}),
    ...(routine ? { animation: { language: 'javascript', source: `export const clips = {}; // ${routine}` } } : {}) };
  return { file: 'hinge.step', kind: 'part', hash: `tree-${revision}`, documentHash,
    ...(mates.length ? { poseUrl: `/__cad/asset?file=hinge.step.json&v=${revision}` } : {}),
    ...(mates.length || routine ? { sourceSidecar: sidecar } : {}),
    ...(routine ? { animationHash: routine } : {}) };
}

/** The hook over one entry, as StepSurface mounts it; `offered` is whether Position is offered (its `poseAvailable`), at every render. */
function mount(entry: ReturnType<typeof saved>) {
  const clock = createAnimationClock();
  const offered: boolean[] = [];
  const hook = renderHook(({ entry }) => {
    const motion = useStepMotion({ entry, fileKey: entry.file, resources: null, meshData: null, meshPartial: false,
      readStored: () => ({ pose: null }), clipboard: null, reportError: () => {} });
    offered.push(stepPosableDofs(motion.definition).length > 0);
    return motion;
  }, { initialProps: { entry },
    wrapper: ({ children }: { children: ReactNode }) => <AnimationClockProvider value={clock}>{children}</AnimationClockProvider> });
  return { ...hook, offered };
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
  rerender({ entry: saved(3, { mates: [{ ...swing, limits: { value: [0, 40] } }] }) });
  await loaded(result, 3);
  expect(result.current.parameterValues).toEqual({ swing: 0 });

  // A save that takes the mates out takes Position with them.
  rerender({ entry: saved(4, { mates: [] }) });
  expect(stepPosableDofs(result.current.definition)).toEqual([]);
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

it('an update that leaves the routine as it was neither stops nor rewinds it, and keeps the pose it set aside; a changed routine is compiled again, at rest', async () => {
  const { result, rerender } = mount(saved(1, { routine: 'swing-1' }));
  await loaded(result, 1);
  await waitFor(() => expect(result.current.animationControls.clips).toHaveLength(1));
  act(() => result.current.onParameterChange('swing', 30));
  // Play takes the pose: Position's values are set aside, and the routine plays from rest.
  act(() => result.current.onPlayToggle());
  expect([result.current.animationState.playing, result.current.parameterValues]).toEqual([true, { swing: 0 }]);

  rerender({ entry: saved(2, { routine: 'swing-1' }) });
  await loaded(result, 2);
  expect(compiled.loads).toBe(1);
  expect(result.current.animationState).toMatchObject({ activeClipId: 'swing', enabled: true, playing: true });
  expect(result.current.animationControls.clips).toHaveLength(1);
  // Leaving preview hands the pose back as Position left it, across the update.
  act(() => result.current.releaseAnimation());
  expect(result.current.parameterValues).toEqual({ swing: 30 });

  // A routine the save changed is compiled again, and is at rest.
  act(() => result.current.onPlayToggle());
  rerender({ entry: saved(3, { routine: 'swing-2' }) });
  await waitFor(() => expect(compiled.loads).toBe(2));
  await waitFor(() => expect(result.current.animationControls.clips).toHaveLength(1));
  expect(result.current.animationState.playing).toBe(false);
});

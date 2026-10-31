import { renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { useMotionExclusion } from '../../../../../dist/renderers/kit/tools/model-effects/motionExclusion.js';

it('the motion set off its default puts the others back; a file opening with several set, or a motion going back, puts nothing back', () => {
  const reset = { explode: vi.fn(), clip: vi.fn(), animation: vi.fn() };
  const motions = (file: string, explode: boolean, clip: boolean, animation: boolean) => ({ file,
    motions: { explode: { applied: explode, reset: reset.explode }, clip: { applied: clip, reset: reset.clip }, animation: { applied: animation, reset: reset.animation } } });
  const { rerender } = renderHook(({ file, motions }) => useMotionExclusion(file, motions), { initialProps: motions('a', true, true, false) });
  expect([reset.explode, reset.clip, reset.animation].map(spy => spy.mock.calls.length)).toEqual([0, 0, 0]);
  rerender(motions('a', true, true, true));
  expect([reset.explode, reset.clip, reset.animation].map(spy => spy.mock.calls.length)).toEqual([1, 1, 0]);
  rerender(motions('a', false, false, false));
  rerender(motions('b', true, false, true));
  expect([reset.explode, reset.clip, reset.animation].map(spy => spy.mock.calls.length)).toEqual([1, 1, 0]);
  rerender(motions('b', true, true, true));
  expect([reset.explode, reset.clip, reset.animation].map(spy => spy.mock.calls.length)).toEqual([2, 1, 1]);
});

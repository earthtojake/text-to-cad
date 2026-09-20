import { cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { usePlaybackFrames } from '../../../../../../dist/renderers/cad/components/viewer/hooks/usePlaybackFrames.js';
import { createAnimationClock } from '../../../../../../dist/renderers/cad/workbench/animationClockStore.js';

afterEach(cleanup);

it('poses the model from the clock while playing, without rendering a component per frame', () => {
  const clock = createAnimationClock(), frameRef = { current: vi.fn() as any };
  let renders = 0;
  const view = renderHook(({ playing }) => { renders += 1; usePlaybackFrames(clock, playing, frameRef); }, { initialProps: { playing: false } });
  clock.setAnimationClock(1);
  expect(frameRef.current).not.toHaveBeenCalled();

  view.rerender({ playing: true });
  const rendersWhenPlaying = renders;
  for (const elapsed of [1.1, 1.2, 1.3]) clock.setAnimationClock(elapsed);
  expect(frameRef.current.mock.calls).toEqual([[1.1], [1.2], [1.3]]);
  expect(renders).toBe(rendersWhenPlaying);

  // The viewer republishes the pass when the state it reads changes; ticks run the latest.
  const republished = vi.fn(); frameRef.current = republished;
  clock.setAnimationClock(1.4);
  expect(republished).toHaveBeenCalledWith(1.4);
  // Between a teardown and the next publish there is nothing to run, and nothing throws.
  frameRef.current = null;
  clock.setAnimationClock(1.5);

  frameRef.current = republished;
  view.rerender({ playing: false });
  clock.setAnimationClock(2);
  expect(republished).toHaveBeenCalledTimes(1);
  view.rerender({ playing: true });
  view.unmount();
  clock.setAnimationClock(3);
  expect(republished).toHaveBeenCalledTimes(1);
});

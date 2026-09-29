import { cleanup, renderHook } from '@testing-library/react';
import { useEffect } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { playbackFrameTime, usePlaybackFrames } from '../../../../../dist/renderers/kit/tools/playbar/usePlaybackFrames.js';
import { createAnimationClock } from '../../../../../dist/renderers/kit/tools/playbar/animationClock.js';

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

it('a pass React re-runs mid-play draws the clock, never the time playback started from', () => {
  // The owner's state keeps the time playback started at (0 here: a routine that starts at rest)
  // while the clock moves on. A detail swap or a progressive publish re-runs the pass mid-play, and
  // the frame React draws must be the one the next tick draws, or the rest pose flashes.
  const clock = createAnimationClock();
  const frameRef = { current: vi.fn() as any };
  let playback = { playing: true, elapsedSec: 0 };
  const view = renderHook(({ revision }) => {
    usePlaybackFrames(clock, playback.playing, frameRef);
    // The owner's pass, which React runs whenever what it reads changes (`revision`).
    useEffect(() => { frameRef.current(playbackFrameTime(clock, playback)); }, [revision]);
  }, { initialProps: { revision: 0 } });
  for (const elapsed of [4, 8, 12]) clock.setAnimationClock(elapsed);
  frameRef.current.mockClear();
  view.rerender({ revision: 1 });
  clock.setAnimationClock(12.5);
  expect(frameRef.current.mock.calls).toEqual([[12], [12.5]]);

  // Stopped, the owner's state is the time (pause and a scrub write both, so they agree).
  playback = { playing: false, elapsedSec: 20 };
  clock.setAnimationClock(20);
  frameRef.current.mockClear();
  view.rerender({ revision: 2 });
  expect(frameRef.current.mock.calls).toEqual([[20]]);
  expect(playbackFrameTime(null, { playing: true, elapsedSec: 3 })).toBe(3);
  expect(playbackFrameTime(clock, null)).toBe(0);
});

import { useEffect } from "react";

/**
 * Drive playback from the animation clock instead of from React.
 *
 * While `playing`, every clock tick calls `frameRef.current(elapsedSec)`
 * synchronously: no component re-renders for a frame. The viewer publishes the
 * frame function from the effect that owns the scene state it reads, and
 * republishes it whenever that state changes, so a tick always runs the pass
 * React itself would have run. A tick that finds no function (between a teardown
 * and the next publish) draws nothing; the next publish poses the model anyway.
 *
 * Running inside the tick also makes the clock's adaptive pacing honest: the
 * cost it measures is the frame's real cost, not the cost of scheduling a render.
 */
export function usePlaybackFrames(clock, playing, frameRef) {
  useEffect(() => {
    if (!playing || !clock) return undefined;
    return clock.subscribe(() => frameRef.current?.(clock.getAnimationClock()));
  }, [clock, playing, frameRef]);
}

/**
 * The time a pass React runs draws the routine at. The frame function has two callers, and while a
 * routine plays they must agree: the owner's React state holds the time playback STARTED from (it is
 * written back only when playback stops), so a pass React re-runs mid-play — a detail swap, a
 * progressive publish, a display change — would pose the model there for a frame, and the next tick
 * would put it back. On a routine that starts at rest, every such re-run flashed the rest pose.
 * While playing the clock is the time; stopped, the owner's state is (the two agree then).
 *
 * @param {{ getAnimationClock(): number } | null} clock
 * @param {{ playing?: boolean, elapsedSec?: number } | null} state
 */
export function playbackFrameTime(clock, state) {
  const time = state?.playing === true && clock ? clock.getAnimationClock() : state?.elapsedSec;
  return Number(time) || 0;
}

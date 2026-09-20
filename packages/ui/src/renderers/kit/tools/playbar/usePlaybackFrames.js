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

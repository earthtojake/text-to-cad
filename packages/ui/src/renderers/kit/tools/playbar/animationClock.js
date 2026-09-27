import { useSyncExternalStore } from "react";

/**
 * A playback clock: elapsed seconds, outside React. Whoever owns an animation
 * creates one, advances it per tick, and hands it to the playbar on its runtime
 * (`runtime.clock`), so a playing frame re-renders nothing but the scrubber.
 *
 * @typedef {{ subscribe(listener: () => void): () => void, getAnimationClock(): number,
 *   setAnimationClock(value: number): void, resetAnimationClock(): void }} AnimationClock
 */
export function createAnimationClock() {
  const listeners = new Set();
  let elapsedSec = 0;
  const clock = {
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    getAnimationClock() { return elapsedSec; },
    setAnimationClock(value) {
      const number = Number(value);
      const next = Number.isFinite(number) && number > 0 ? number : 0;
      if (next === elapsedSec) return;
      elapsedSec = next;
      for (const listener of listeners) listener();
    },
    resetAnimationClock() { clock.setAnimationClock(0); }
  };
  return clock;
}

/** The clock's live value, as React state. */
export function useAnimationClockValue(clock) {
  if (!clock) throw new Error("Playback requires its owner's animation clock (runtime.clock).");
  return useSyncExternalStore(clock.subscribe, clock.getAnimationClock, clock.getAnimationClock);
}

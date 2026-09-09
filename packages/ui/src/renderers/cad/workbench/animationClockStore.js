import { createContext, createElement, useContext, useSyncExternalStore } from "react";

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
const AnimationClockContext = createContext(null);
export function AnimationClockProvider({ value, children }) {
  return createElement(AnimationClockContext.Provider, { value }, children);
}
export function useAnimationClockStore() {
  const clock = useContext(AnimationClockContext);
  if (!clock) throw new Error("CAD playback requires its renderer's animation clock.");
  return clock;
}
export function useAnimationClock() {
  const clock = useAnimationClockStore();
  return useSyncExternalStore(clock.subscribe, clock.getAnimationClock, clock.getAnimationClock);
}

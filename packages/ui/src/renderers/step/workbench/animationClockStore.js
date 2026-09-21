import { createContext, createElement, useContext, useSyncExternalStore } from "react";
import { createAnimationClock } from "../../kit/tools/playbar/animationClock.js";

export { createAnimationClock };

const AnimationClockContext = createContext(null);
export function AnimationClockProvider({ value, children }) {
  return createElement(AnimationClockContext.Provider, { value }, children);
}
/** The clock when a provider is mounted, else null: for callers that only hand it on. */
export function useOptionalAnimationClockStore() {
  return useContext(AnimationClockContext);
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

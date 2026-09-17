import { createContext, createElement, useContext, useSyncExternalStore } from "react";
import { createAnimationClock } from "./animationClockStore.js";

// STEP and embedded GLB have separate clocks within each mounted renderer.
export const createEmbeddedGlbAnimationClock = createAnimationClock;
const EmbeddedGlbAnimationClockContext = createContext(null);
export function EmbeddedGlbAnimationClockProvider({ value, children }) {
  return createElement(EmbeddedGlbAnimationClockContext.Provider, { value }, children);
}
export function useEmbeddedGlbAnimationClockStore() {
  const clock = useContext(EmbeddedGlbAnimationClockContext);
  if (!clock) throw new Error("GLB playback requires its renderer's animation clock.");
  return clock;
}
export function useEmbeddedGlbAnimationClock() {
  const clock = useEmbeddedGlbAnimationClockStore();
  return useSyncExternalStore(clock.subscribe, clock.getAnimationClock, clock.getAnimationClock);
}

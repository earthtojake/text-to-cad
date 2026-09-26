import { createContext, createElement, useContext } from "react";
import { createAnimationClock } from "../../kit/tools/playbar/animationClock.js";

export { createAnimationClock };

const AnimationClockContext = createContext(null);
export function AnimationClockProvider({ value, children }) {
  return createElement(AnimationClockContext.Provider, { value }, children);
}
export function useAnimationClockStore() {
  const clock = useContext(AnimationClockContext);
  if (!clock) throw new Error("CAD playback requires its renderer's animation clock.");
  return clock;
}

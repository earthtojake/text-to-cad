import { useMemo } from "react";
import {
  AnimationTransport as KitAnimationTransport,
  PLAYBACK_SPEEDS,
  ViewportAnimationBar as KitViewportAnimationBar,
  animationControlsHaveContent
} from "../../../kit/tools/playbar/ViewportAnimationBar.js";
import { useOptionalAnimationClockStore } from "../../workbench/animationClockStore.js";

export { PLAYBACK_SPEEDS, animationControlsHaveContent };

// The kit's playbar follows the clock on the runtime it is handed. This renderer
// keeps one clock per mounted viewer, in context; here it becomes `runtime.clock`.
export function useAnimationRuntimeClock(runtime) {
  const clock = useOptionalAnimationClockStore();
  return useMemo(() => (runtime ? { ...runtime, clock } : runtime), [runtime, clock]);
}

export function AnimationTransport({ runtime, ...props }) {
  return <KitAnimationTransport runtime={useAnimationRuntimeClock(runtime)} {...props}/>;
}

export function ViewportAnimationBar({ runtime, ...props }) {
  return <KitViewportAnimationBar runtime={useAnimationRuntimeClock(runtime)} {...props}/>;
}

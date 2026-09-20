import { useMemo } from "react";
import {
  AnimationTransport as KitAnimationTransport,
  PLAYBACK_SPEEDS,
  ViewportAnimationBar as KitViewportAnimationBar,
  animationControlsHaveContent
} from "../../../kit/tools/playbar/ViewportAnimationBar.js";
import { useOptionalAnimationClockStore } from "../../workbench/animationClockStore.js";
import { useOptionalEmbeddedGlbAnimationClockStore } from "../../workbench/embeddedGlbAnimationClockStore.js";

export { PLAYBACK_SPEEDS, animationControlsHaveContent };

// The kit's playbar follows the clock on the runtime it is handed. This renderer
// keeps two clocks per mounted viewer (STEP routines, embedded glTF clips) and its
// runtimes name theirs by `clockKind`; here that name becomes `runtime.clock`.
export function useAnimationRuntimeClock(runtime) {
  const stepClock = useOptionalAnimationClockStore();
  const embeddedClock = useOptionalEmbeddedGlbAnimationClockStore();
  const clock = runtime?.clockKind === "embedded-glb" ? embeddedClock : stepClock;
  return useMemo(() => (runtime ? { ...runtime, clock } : runtime), [runtime, clock]);
}

export function AnimationTransport({ runtime, ...props }) {
  return <KitAnimationTransport runtime={useAnimationRuntimeClock(runtime)} {...props}/>;
}

export function ViewportAnimationBar({ runtime, ...props }) {
  return <KitViewportAnimationBar runtime={useAnimationRuntimeClock(runtime)} {...props}/>;
}

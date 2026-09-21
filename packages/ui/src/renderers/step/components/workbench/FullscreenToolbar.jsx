import KitFullscreenToolbar, { FULLSCREEN_TOOLBAR_IDLE_MS } from "../../../kit/tools/fullscreen/FullscreenToolbar.jsx";
import { useAnimationRuntimeClock } from "./AnimationControlsSection.js";

export { FULLSCREEN_TOOLBAR_IDLE_MS };

/** The kit's fullscreen controls over this renderer's animation runtime (see `useAnimationRuntimeClock`). */
export default function FullscreenToolbar({ animation = null, ...props }) {
  return <KitFullscreenToolbar animation={useAnimationRuntimeClock(animation)} {...props}/>;
}

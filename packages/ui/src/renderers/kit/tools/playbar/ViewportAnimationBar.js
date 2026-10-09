import { VIEWPORT_BOTTOM_CENTER } from "../../shell/viewportLayout.js";
import { Pause, Play } from "lucide-react";
import { useAnimationClockValue } from "./animationClock.js";
import { Slider } from "@text-to-cad/ui/primitives/slider";
import { cn } from "@text-to-cad/ui/utils";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import { FILE_SHEET_PRECISION_SLIDER_CLASSES } from "../../inspector/FileSheet.js";

// The transport owns play/pause and scrubbing; the routines and the routine's speed, loop and
// autoplay are the playbar's two menus at either end of it (`PlaybackMenu.jsx`), which the shell
// hands it, and the Animation tool's panel's (`AnimationPanel.jsx`).
//
// Every animation source shares this transport UI. It only edits the clip and clock state of
// the runtime it is handed; evaluating a clip is its owner's. Routines play in preview, where
// the playbar under the model is the transport, and under the Animation tool, whose panel
// carries the same scrubber (`AnimationTimeControl`).
//
// runtime: { clips: [{ id, label, duration }], activeClipId, playing, elapsedSec,
//   speed, loopEnabled, clock, onClipSelect, onPlayToggle, onScrub, onSpeedChange,
//   onLoopToggle, onRelease, savePlayback, restorePlayback }. `clock` is the owner's live
//   AnimationClock (`animationClock.js`); `onRelease` stops, rewinds and puts the model back at
//   rest. Preview's routine is its own: entering preview saves the tools view's routine as it
//   stands (`savePlayback()`: which routine, its time, whether it plays) and releases it, and
//   leaving releases preview's and hands the saved one back (`restorePlayback(saved)`).

export const PLAYBACK_SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3];

function formatSeconds(value) {
  const numericValue = Math.max(Number(value) || 0, 0);
  return `${numericValue.toFixed(numericValue >= 10 ? 1 : 2)}s`;
}

/**
 * The scrubber over the routine in hand. It tracks the LIVE clock while playing: the elapsed time on
 * the runtime snapshot only moves when playback stops, because a playing clip publishes through the
 * clock store instead of React state. Preview's playbar and the Animation tool's panel both draw it.
 */
export function AnimationTimeControl({ runtime, disabled = false }) {
  const activeClip = runtime?.clips?.find(clip => clip.id === runtime?.activeClipId);
  const duration = Math.max(Number(activeClip?.duration) || 1, 0.001);
  const liveElapsedSec = useAnimationClockValue(runtime?.clock);
  const rawElapsedSec = runtime?.playing === true ? liveElapsedSec : runtime?.elapsedSec;
  const value = Math.min(Math.max(Number(rawElapsedSec) || 0, 0), duration);
  return (
    <Slider
      className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
      disabled={disabled}
      value={[value]}
      min={0}
      max={duration}
      step={0.01}
      onValueChange={(nextValue) => runtime?.onScrub?.(nextValue?.[0] ?? 0)}
      thumbProps={{ "aria-label": "Animation time", "aria-valuetext": `${formatSeconds(value)} of ${formatSeconds(duration)}` }}
    />
  );
}

/** Play/Pause and the scrubber over the renderer's live clock. Dragging the scrubber to the start is the restart. */
function AnimationTransport({ runtime, disabled = false }) {
  const iconClass = "size-3.5";
  return <div className="flex h-6 min-w-0 flex-1 items-center gap-1" data-animation-transport>
    <ToolbarButton tooltip={false} disabled={disabled} tooltipSide="top"
      onClick={() => runtime?.onPlayToggle?.()} label={`${runtime?.playing ? "Pause" : "Play"} animation`}>
      {runtime?.playing ? <Pause className={iconClass} strokeWidth={1.5} aria-hidden="true"/> : <Play className={iconClass} strokeWidth={1.5} aria-hidden="true"/>}
    </ToolbarButton>
    <div className="min-w-0 flex-1 px-1">
      <AnimationTimeControl runtime={runtime} disabled={disabled}/>
    </div>
  </div>;
}

/**
 * The playbar: transport in one transparent row under the model, centered: preview's animation
 * control, with `leading` (the Routines list) at its left end and `trailing` (Playback settings'
 * cog) at its right. Its buttons sit 4px apart, as the navbar's and preview's corner's do, and the
 * scrubber as far from the button on either side of it. Preview has no cube to make room for.
 */
export function ViewportAnimationBar({ runtime, disabled = false, className, leading = null, trailing = null }) {

  if (!animationControlsHaveContent(runtime)) return null;
  return <div role="toolbar" aria-label="Animation playback" data-preview-hover-hold="" style={{ "--viewport-bottom-inset": VIEWPORT_BOTTOM_CENTER }} className={cn(
    'absolute bottom-[var(--viewport-bottom-inset)] left-1/2 z-30 flex w-96 max-w-[calc(100%-24px)] -translate-x-1/2 translate-y-1/2 items-center gap-1 px-5 py-4',
    className,
  )}>
    {leading}
    <AnimationTransport runtime={runtime} disabled={disabled}/>
    {trailing}
  </div>;
}

/** A file has animation when it has routines to play: no routines, no playbar, nothing to play in preview and no Animation tool. */
export function animationControlsHaveContent(runtime) {
  return Array.isArray(runtime?.clips) && runtime.clips.length > 0;
}

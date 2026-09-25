import { VIEWPORT_BOTTOM_CENTER } from "../../shell/viewportLayout.js";
import { Pause, Play } from "lucide-react";
import { useAnimationClockValue } from "./animationClock.js";
import { TooltipProvider } from "@hardcore/ui/primitives/tooltip";
import { Slider } from "@hardcore/ui/primitives/slider";
import { cn } from "@hardcore/ui/utils";
import { ToolbarButton } from "../ToolbarButton.js";
import { FILE_SHEET_PRECISION_SLIDER_CLASSES } from "../../inspector/FileSheet.js";

// The playbar owns play/pause and scrubbing. Routine, speed and loop live in PlayMenu.
//
// Every animation source shares this transport UI. The bar only edits the clip
// and clock state of the runtime it is handed; evaluating a clip is its owner's.
// Animation has no panel section: it is the Animate tool's bottom action,
// and the whole of fullscreen's animation control.
//
// runtime: { clips: [{ id, label, duration }], activeClipId, playing, elapsedSec,
//   speed, loopEnabled, clock, onClipSelect, onPlayToggle, onScrub, onSpeedChange,
//   onLoopToggle }. `clock` is the owner's live AnimationClock (`animationClock.js`).

export const PLAYBACK_SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3];

function formatSeconds(value) {
  const numericValue = Math.max(Number(value) || 0, 0);
  return `${numericValue.toFixed(numericValue >= 10 ? 1 : 2)}s`;
}

// The time slider tracks the LIVE clock while playing: the elapsed time on the
// runtime snapshot only moves when playback stops, because a playing clip
// publishes through the clock store instead of React state.
function AnimationTimeControl({ playing, elapsedSec, duration, onScrub, clock, disabled = false }) {
  const liveElapsedSec = useAnimationClockValue(clock);
  const rawElapsedSec = playing ? liveElapsedSec : elapsedSec;
  const value = Math.min(Math.max(Number(rawElapsedSec) || 0, 0), duration);
  return (
    <Slider
      className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
      disabled={disabled}
      value={[value]}
      min={0}
      max={duration}
      step={0.01}
      onValueChange={(nextValue) => onScrub?.(nextValue?.[0] ?? 0)}
      thumbProps={{ "aria-label": "Animation time", "aria-valuetext": `${formatSeconds(value)} of ${formatSeconds(duration)}` }}
    />
  );
}

/** Play/Pause and the scrubber over the renderer's live clock. Dragging the scrubber to the start is the restart. */
export function AnimationTransport({ runtime, disabled = false, responsive = false }) {
  const activeClip = runtime?.clips?.find(clip => clip.id === runtime?.activeClipId);
  const duration = Math.max(Number(activeClip?.duration) || 1, 0.001);
  const iconClass = "size-3.5";
  return <TooltipProvider delayDuration={400}><div className={cn("flex min-w-0 flex-1 items-center gap-2", "h-6",
    responsive && "@max-[8rem]/cad-viewport:h-auto @max-[8rem]/cad-viewport:flex-wrap")} data-animation-transport>
    <ToolbarButton tooltip={false} disabled={disabled} tooltipSide="top"
      onClick={() => runtime?.onPlayToggle?.()} label={`${runtime?.playing ? "Pause" : "Play"} animation`}>
      {runtime?.playing ? <Pause className={iconClass} strokeWidth={1.5} aria-hidden="true"/> : <Play className={iconClass} strokeWidth={1.5} aria-hidden="true"/>}
    </ToolbarButton>
    <div className={cn("min-w-0 flex-1 px-1", responsive && "@max-[8rem]/cad-viewport:order-last @max-[8rem]/cad-viewport:basis-full")}>
      <AnimationTimeControl playing={runtime?.playing === true} elapsedSec={runtime?.elapsedSec}
        duration={duration} onScrub={runtime?.onScrub} clock={runtime?.clock} disabled={disabled}/>
    </div>
  </div></TooltipProvider>;
}

/**
 * The playbar: transport in one transparent row. It is
 * the Animate tool's bottom action in the regular view and the whole of
 * fullscreen's animation control; both mount this component over the same
 * runtime. It stays centered until it needs to make room for the XYZ control.
 */
export function ViewportAnimationBar({ runtime, disabled = false, avoidViewControl = false, className }) {

  if (!animationControlsHaveContent(runtime)) return null;
  return <div role="toolbar" aria-label="Animation playback" data-preview-hover-hold="" style={{ "--viewport-bottom-inset": VIEWPORT_BOTTOM_CENTER }} className={cn(
    'absolute bottom-[var(--viewport-bottom-inset)] translate-y-1/2 z-30 flex items-center gap-2 px-5 py-4',
    avoidViewControl
      ? 'left-[max(0.75rem,calc(50%-10rem))] right-[max(7rem,calc(50%-10rem))] @max-[15rem]/cad-viewport:bottom-32 @max-[15rem]/cad-viewport:right-3'
      : 'left-1/2 w-80 max-w-[calc(100%-24px)] -translate-x-1/2',
    className,
  )}>
    <AnimationTransport runtime={runtime} disabled={disabled} responsive={avoidViewControl}/>
  </div>;
}

/** A file has animation when it has routines to play: no routines, no Animate tool and no playbar. */
export function animationControlsHaveContent(runtime) {
  return Array.isArray(runtime?.clips) && runtime.clips.length > 0;
}

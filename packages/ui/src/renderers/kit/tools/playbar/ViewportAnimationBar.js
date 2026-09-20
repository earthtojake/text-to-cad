import { Check, ListVideo, Pause, Play, Settings } from "lucide-react";
import { useState } from "react";
import { useAnimationClockValue } from "./animationClock.js";
import { animationClipOptions } from "./animationClipOptions.js";
import { Button } from "@hardcore/ui/primitives/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem,
  DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger,
} from "@hardcore/ui/primitives/dropdown-menu";
import { Slider } from "@hardcore/ui/primitives/slider";
import { cn } from "@hardcore/ui/utils";
import { TOOLBAR_ICON_BUTTON_CLASS } from "../ToolbarButton.js";
import { FILE_SHEET_PRECISION_SLIDER_CLASSES } from "../../inspector/FileSheet.js";

// The playbar: pick a routine, play it, scrub it, set its speed and loop.
//
// Every animation source shares this transport UI. The bar only edits the clip
// and clock state of the runtime it is handed; evaluating a clip is its owner's.
// Animation has no Inspector section: it is the Animate tool's bottom action,
// and the whole of fullscreen's animation control.
//
// runtime: { clips: [{ id, label, duration }], activeClipId, playing, elapsedSec,
//   speed, loopEnabled, clock, onClipSelect, onPlayToggle, onScrub, onSpeedChange,
//   onLoopToggle }. `clock` is the owner's live AnimationClock (`animationClock.js`).

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
      title={`${formatSeconds(value)} / ${formatSeconds(duration)}`}
    />
  );
}

/** Play/Pause and the scrubber over the renderer's live clock. Dragging the scrubber to the start is the restart. */
export function AnimationTransport({ runtime, compact = false, disabled = false, responsive = false }) {
  const activeClip = runtime?.clips?.find(clip => clip.id === runtime?.activeClipId);
  const duration = Math.max(Number(activeClip?.duration) || 1, 0.001);
  const buttonClass = compact ? TOOLBAR_ICON_BUTTON_CLASS : "size-7 shrink-0";
  const iconClass = compact ? "size-3" : "size-3.5";
  return <div className={cn("flex min-w-0 flex-1 items-center gap-1", compact ? "h-6" : "h-7 px-2",
    responsive && "@max-[8rem]/cad-viewport:h-auto @max-[8rem]/cad-viewport:flex-wrap")} data-animation-transport>
    <Button type="button" variant="ghost" size="icon-xs" className={buttonClass} disabled={disabled}
      onClick={() => runtime?.onPlayToggle?.()} aria-label={`${runtime?.playing ? "Pause" : "Play"} animation`}
      title={`${runtime?.playing ? "Pause" : "Play"} animation`}>
      {runtime?.playing ? <Pause className={iconClass} aria-hidden="true"/> : <Play className={iconClass} aria-hidden="true"/>}
    </Button>
    <div className={cn("min-w-0 flex-1 px-1", responsive && "@max-[8rem]/cad-viewport:order-last @max-[8rem]/cad-viewport:basis-full")}>
      <AnimationTimeControl playing={runtime?.playing === true} elapsedSec={runtime?.elapsedSec}
        duration={duration} onScrub={runtime?.onScrub} clock={runtime?.clock} disabled={disabled}/>
    </div>
  </div>;
}

const stopEscape = event => event.stopPropagation();
const MENU_PROPS = { side: "top", sideOffset: 8, collisionPadding: 8, onEscapeKeyDown: stopEscape };
// The speeds a player offers; an authored speed outside them is listed too, so the menu never lies.
export const PLAYBACK_SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3];
const speedLabel = speed => `${speed}×`;

// Which routine plays: a list button at the start of the bar, and only when
// there is a choice to make.
function PlaybarRoutine({ runtime, disabled, onOpenChange }) {
  const options = animationClipOptions(Array.isArray(runtime?.clips) ? runtime.clips : []);
  if (options.length < 2) return null;
  const active = options.find(option => option.value === runtime?.activeClipId) || options[0];
  return <DropdownMenu onOpenChange={onOpenChange}>
    <DropdownMenuTrigger asChild>
      <Button type="button" variant="ghost" size="icon-xs" className={TOOLBAR_ICON_BUTTON_CLASS} disabled={disabled}
        aria-label={`Animation routine: ${active?.label || ""}`} title={`Routine: ${active?.label || ""}`}>
        <ListVideo className="size-3" aria-hidden="true"/>
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent {...MENU_PROPS} align="start" className="max-w-60">
      <DropdownMenuLabel>Routine</DropdownMenuLabel>
      <DropdownMenuRadioGroup value={runtime?.activeClipId || ""} onValueChange={value => runtime?.onClipSelect?.(value)}>
        {options.map(option => <DropdownMenuRadioItem key={option.value} value={option.value}>{option.label}</DropdownMenuRadioItem>)}
      </DropdownMenuRadioGroup>
    </DropdownMenuContent>
  </DropdownMenu>;
}

// A player's settings menu: each setting is a row that says its value, Speed
// opening the list of speeds, Loop toggling in place.
function PlaybarSettings({ runtime, disabled, onOpenChange }) {
  const speed = Number(runtime?.speed) || 1;
  const speeds = PLAYBACK_SPEEDS.includes(speed) ? PLAYBACK_SPEEDS : [...PLAYBACK_SPEEDS, speed].sort((a, b) => a - b);
  const loopEnabled = runtime?.loopEnabled !== false;
  return <DropdownMenu onOpenChange={onOpenChange}>
    <DropdownMenuTrigger asChild>
      <Button type="button" variant="ghost" size="icon-xs" className={TOOLBAR_ICON_BUTTON_CLASS} disabled={disabled}
        aria-label="Playback settings" title="Playback settings">
        <Settings className="size-3" aria-hidden="true"/>
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent {...MENU_PROPS} align="end" className="w-48">
      <DropdownMenuSub>
        <DropdownMenuSubTrigger>
          {/* The value sits against the arrow, as Loop's check sits against the edge. */}
          <span className="flex-1">Speed</span><span className="text-muted-foreground tabular-nums">{speedLabel(speed)}</span>
        </DropdownMenuSubTrigger>
        <DropdownMenuSubContent className="w-32" onEscapeKeyDown={stopEscape}>
          <DropdownMenuRadioGroup value={String(speed)} onValueChange={value => runtime?.onSpeedChange?.(Number(value))}>
            {speeds.map(option => <DropdownMenuRadioItem key={option} value={String(option)}>{speedLabel(option)}</DropdownMenuRadioItem>)}
          </DropdownMenuRadioGroup>
        </DropdownMenuSubContent>
      </DropdownMenuSub>
      {/* Labels on the left, values on the right, as in any player: Speed's value and
          arrow, Loop's check. It stays open: a toggle is looked at after it is pressed. */}
      <DropdownMenuItem role="menuitemcheckbox" aria-checked={loopEnabled} onSelect={event => {
        event.preventDefault();
        runtime?.onLoopToggle?.(!loopEnabled);
      }}>
        Loop{loopEnabled ? <Check className="ml-auto size-3.5" aria-hidden="true"/> : null}
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>;
}

/**
 * The playbar: routine, transport and settings in one transparent row. It is
 * the Animate tool's bottom action in the regular view and the whole of
 * fullscreen's animation control; both mount this component over the same
 * runtime. It stays centered until it needs to make room for the XYZ control.
 */
export function ViewportAnimationBar({ runtime, disabled = false, avoidViewControl = false, className, onMenuOpenChange }) {
  const [open, setOpen] = useState({ routine: false, settings: false });
  const report = key => value => {
    const next = { ...open, [key]: value };
    setOpen(next);
    onMenuOpenChange?.(next.routine || next.settings);
  };
  if (!animationControlsHaveContent(runtime)) return null;
  return <div role="toolbar" aria-label="Animation playback" className={cn(
    'absolute bottom-3 z-30 flex items-center gap-0.5 p-1',
    avoidViewControl
      ? 'left-[max(0.75rem,calc(50%-12rem))] right-[max(8rem,calc(50%-12rem))] @max-[15rem]/cad-viewport:bottom-32 @max-[15rem]/cad-viewport:right-3'
      : 'left-1/2 w-96 max-w-[calc(100%-24px)] -translate-x-1/2',
    className,
  )}>
    <PlaybarRoutine runtime={runtime} disabled={disabled} onOpenChange={report('routine')}/>
    <AnimationTransport runtime={runtime} compact disabled={disabled} responsive={avoidViewControl}/>
    <PlaybarSettings runtime={runtime} disabled={disabled} onOpenChange={report('settings')}/>
  </div>;
}

/** A file has animation when it has routines to play: no routines, no Animate tool and no playbar. */
export function animationControlsHaveContent(runtime) {
  return Array.isArray(runtime?.clips) && runtime.clips.length > 0;
}

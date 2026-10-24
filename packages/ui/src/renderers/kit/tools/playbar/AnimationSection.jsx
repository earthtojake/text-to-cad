import { ChevronDown, Pause, Play, RotateCcw } from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger
} from "@text-to-cad/ui/primitives/dropdown-menu";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../../lib/floatingSurface.js";
import PlaybackMenu from "../PlaybackMenu.jsx";
import { SUB_TOOLBAR_SLIDER_CLASS } from "../SubToolbar.jsx";
import ToolPanel, { TOOL_PANEL_BUTTON_CLASS, ToolPanelHeadAction } from "../ToolPanel.jsx";
import { AnimationTimeControl, formatSeconds } from "./AnimationTimeControl.js";

/**
 * The file sidebar's Animation section, for a file with routines: the routine played in the tools
 * view, whose frame stays on the model when it pauses or the section closes, as a pose does: the
 * other tools work on the model as it stands (the renderer keeps one motion at a time: its other
 * motions put the routine back at rest, and playing it puts them at rest). Its heading holds Reset,
 * which puts the model back at rest, idle while it is; its body the routine, where there are
 * several, then Play or Pause, the scrubber and the Playback settings (Speed, Loop, Autoplay:
 * `PlaybackMenu.jsx`). Preview's routine is its own (`useRendererShell`). The runtime's `noun` names
 * the section and its controls: "Animation" (a mesh file's clips), or "Motion" (an engine document's
 * motions, `xbf/useXbfMotion.js`). Each routine in the dropdown says its duration.
 *
 * @param {{ runtime: object, autoplay: boolean, onAutoplayChange(value: boolean): void, disabled?: boolean }} props
 */
export default function AnimationSection({ runtime, autoplay, onAutoplayChange, disabled = false }) {
  const playing = runtime?.playing === true;
  const atRest = !playing && !(Number(runtime?.elapsedSec) > 0);
  const clips = runtime?.clips || [];
  const active = clips.find(clip => clip.id === runtime?.activeClipId);
  const noun = runtime?.noun || "Animation", word = noun.toLowerCase();
  // Its tile's dot: a routine's frame on the model (playing, or paused off its start).
  return <ToolPanel id="animation" title={noun} label={noun} fit="details" changed={!atRest}>
    <ToolPanelHeadAction>
      <TooltipHint content={`Reset ${word}`} side="bottom">
        <button type="button" aria-label={`Reset ${word}`} data-animation-reset="" disabled={disabled || atRest}
          onClick={() => runtime?.onRelease?.()} className={cn(TOOL_PANEL_BUTTON_CLASS, "disabled:pointer-events-none disabled:opacity-40")}>
          <RotateCcw className="size-3" aria-hidden="true" />
        </button>
      </TooltipHint>
    </ToolPanelHeadAction>
    {/* With several routines, the one in hand, a full-width row over the transport: a choice is at its start, at rest, until it plays. */}
    {clips.length > 1 ? <div className="flex h-8 items-center px-2" data-animation-routine="">
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <button type="button" aria-label={`${noun === "Animation" ? "Routine" : noun}: ${active?.label || ""}`} disabled={disabled}
            className="flex h-6 w-full min-w-0 items-center justify-between gap-1 rounded-md border border-input bg-transparent px-2 text-left text-tiny shadow-xs outline-none focus-visible:ring-2 focus-visible:ring-ring/45 aria-expanded:bg-accent disabled:opacity-50 dark:bg-input/30 dark:hover:bg-input/50">
            <span className="min-w-0 truncate">{active?.label}</span>
            <ChevronDown className="size-3 shrink-0 opacity-60" aria-hidden="true" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" sideOffset={4} collisionPadding={8} aria-label={noun === "Animation" ? "Routines" : `${noun}s`}
          className={cn(FLOATING_SURFACE_CLASS, "min-w-(--radix-dropdown-menu-trigger-width) data-[state=closed]:animate-none!")}>
          <DropdownMenuRadioGroup value={runtime?.activeClipId} onValueChange={id => runtime?.onClipSelect?.(id)}>
            {clips.map(clip => <DropdownMenuRadioItem key={clip.id} value={clip.id}>
              <span className="min-w-0 truncate">{clip.label}</span>
              {Number(clip.duration) > 0 ? <span className="ml-auto pl-2 tabular-nums text-muted-foreground">{formatSeconds(clip.duration)}</span> : null}
            </DropdownMenuRadioItem>)}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </div> : null}
    <div className="flex h-8 items-center gap-1 pl-1 pr-2" data-animation-transport="">
      <ToolbarButton tooltip={false} disabled={disabled} label={`${playing ? "Pause" : "Play"} ${word}`} onClick={() => runtime?.onPlayToggle?.()}>
        {playing ? <Pause className="size-3" strokeWidth={2} aria-hidden="true" /> : <Play className="size-3" strokeWidth={2} aria-hidden="true" />}
      </ToolbarButton>
      <AnimationTimeControl runtime={runtime} disabled={disabled} className={cn(SUB_TOOLBAR_SLIDER_CLASS, "min-w-0 flex-1")} />
      <PlaybackMenu animation={runtime} side="bottom" disabled={disabled} autoplay={autoplay} onAutoplayChange={onAutoplayChange} />
    </div>
  </ToolPanel>;
}

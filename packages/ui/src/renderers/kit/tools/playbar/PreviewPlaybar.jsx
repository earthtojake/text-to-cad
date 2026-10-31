import { ListVideo, Pause, Play } from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger
} from "@text-to-cad/ui/primitives/dropdown-menu";
import { Button } from "@text-to-cad/ui/primitives/button";
import { ToolbarButton, TOOLBAR_ICON_BUTTON_CLASS } from "@text-to-cad/ui/primitives/toolbar-button";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../../lib/floatingSurface.js";
import { PREVIEW_FADE_CLASS, usePreviewShown } from "../PreviewChrome.jsx";
import PlaybackMenu from "../PlaybackMenu.jsx";
import { AnimationTimeControl, animationControlsHaveContent, formatSeconds, playbarWords } from "./AnimationTimeControl.js";
import { useI18n } from "@text-to-cad/ui/i18n";

const ROUTINES_TRIGGER_CLASS = cn(TOOLBAR_ICON_BUTTON_CLASS, "aria-expanded:bg-sidebar-accent aria-expanded:text-sidebar-accent-foreground");

/** The routines, where there are several: a list from its icon at the playbar's left end, opening up. */
function RoutineMenu({ runtime, disabled }) {
  const { t } = useI18n();
  const clips = runtime?.clips || [];
  if (clips.length < 2) return null;
  const name = playbarWords(runtime, t).list;
  return <DropdownMenu modal={false}>
    <TooltipHint content={name} side="top">
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="ghost" size="icon-xs" aria-label={name} disabled={disabled} className={ROUTINES_TRIGGER_CLASS}>
          <ListVideo className="size-3.5" strokeWidth={1.5} aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
    </TooltipHint>
    <DropdownMenuContent side="top" align="start" sideOffset={6} collisionPadding={8} aria-label={name}
      className={cn(FLOATING_SURFACE_CLASS, "w-44 data-[state=closed]:animate-none!")}>
      <DropdownMenuRadioGroup value={runtime.activeClipId} onValueChange={id => runtime.onClipSelect?.(id)}>
        {clips.map(clip => <DropdownMenuRadioItem key={clip.id} value={clip.id}>
          <span className="min-w-0 truncate">{clip.label}</span>
          {Number(clip.duration) > 0 ? <span className="ml-auto pl-2 tabular-nums text-muted-foreground">{formatSeconds(clip.duration)}</span> : null}
        </DropdownMenuRadioItem>)}
      </DropdownMenuRadioGroup>
    </DropdownMenuContent>
  </DropdownMenu>;
}

/**
 * Preview's playbar, for a file with routines: one transparent row under the model, centred, as it
 * was before Preview had a sidebar — the Routines list at its left end where there are several,
 * Play or Pause, the scrubber, and the Playback settings (Speed, Loop, Autoplay) at its right end,
 * their menus opening up. Its buttons sit 4px apart, the scrubber as far from the button either
 * side of it. It plays Preview's own routine (`runtime`), never the tools view's. It comes and goes
 * with Preview's bar (`idle`, `createPreviewIdle`), its playing untouched by either.
 *
 * @param {{ runtime: object, autoplay: boolean, onAutoplayChange(value: boolean): void, disabled?: boolean,
 *   idle?: ReturnType<typeof import("../PreviewChrome.jsx").createPreviewIdle> | null }} props
 */
export default function PreviewPlaybar({ runtime, autoplay, onAutoplayChange, disabled = false, idle = null }) {
  const shown = usePreviewShown(idle);
  const { t } = useI18n();
  if (!animationControlsHaveContent(runtime)) return null;
  const playing = runtime.playing === true;
  const words = playbarWords(runtime, t);
  return <div role="toolbar" aria-label={words.playback} data-preview-playbar="" data-state={shown ? "visible" : "hidden"} {...idle?.hold("playbar")}
    className={cn("absolute bottom-4 left-1/2 z-30 flex w-96 max-w-[calc(100%-24px)] -translate-x-1/2 items-center gap-1 px-2 py-1", PREVIEW_FADE_CLASS,
      shown ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0")}>
    <RoutineMenu runtime={runtime} disabled={disabled} />
    <ToolbarButton tooltip={false} disabled={disabled} label={playing ? words.pause : words.play} onClick={() => runtime.onPlayToggle?.()}>
      {playing ? <Pause className="size-3.5" strokeWidth={1.5} aria-hidden="true" /> : <Play className="size-3.5" strokeWidth={1.5} aria-hidden="true" />}
    </ToolbarButton>
    <div className="min-w-0 flex-1 px-1">
      <AnimationTimeControl runtime={runtime} disabled={disabled} />
    </div>
    <PlaybackMenu animation={runtime} side="top" disabled={disabled} autoplay={autoplay} onAutoplayChange={onAutoplayChange} />
  </div>;
}

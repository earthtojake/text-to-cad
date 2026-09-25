import { DropdownMenuCheckboxItem, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger } from "@hardcore/ui/primitives/dropdown-menu";
import ToolPopover from "./ToolPopover.jsx";

import { PLAYBACK_SPEEDS as ANIMATION_SPEEDS } from "./playbar/ViewportAnimationBar.js";

export default function PlayMenu({ trigger, animation, onOpenChange, allowInactive = false }) {
  const animationSpeed = Number(animation?.speed) || 1;
  const animationSpeeds = ANIMATION_SPEEDS.includes(animationSpeed) ? ANIMATION_SPEEDS : [...ANIMATION_SPEEDS, animationSpeed].sort((a, b) => a - b);
  return <ToolPopover onOpenChange={onOpenChange} allowInactive={allowInactive} trigger={trigger} label="Animation options" className="w-40">
    {animation?.clips?.length > 1 && <DropdownMenuSub>
      <DropdownMenuSubTrigger>Routine</DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="w-44">
        <DropdownMenuRadioGroup value={animation.activeClipId} onValueChange={animation.onClipSelect}>
          {animation.clips.map(clip => <DropdownMenuRadioItem key={clip.id} value={clip.id}>{clip.label}</DropdownMenuRadioItem>)}
        </DropdownMenuRadioGroup>
      </DropdownMenuSubContent>
    </DropdownMenuSub>}
    {animation?.clips?.length > 0 && <>
      <DropdownMenuSub>
        <DropdownMenuSubTrigger><span className="flex-1">Speed</span><span className="text-muted-foreground tabular-nums">{animationSpeed}×</span></DropdownMenuSubTrigger>
        <DropdownMenuSubContent className="w-32">
          <DropdownMenuRadioGroup value={String(animationSpeed)} onValueChange={value => animation.onSpeedChange(Number(value))}>
            {animationSpeeds.map(value => <DropdownMenuRadioItem key={value} value={String(value)}>{value}×</DropdownMenuRadioItem>)}
          </DropdownMenuRadioGroup>
        </DropdownMenuSubContent>
      </DropdownMenuSub>
      <DropdownMenuCheckboxItem checked={animation.loopEnabled !== false} onCheckedChange={animation.onLoopToggle} onSelect={event => event.preventDefault()}>Loop</DropdownMenuCheckboxItem>
    </>}
  </ToolPopover>;
}

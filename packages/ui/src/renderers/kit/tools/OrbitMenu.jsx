import { Orbit } from "lucide-react";
import { cn } from "@hardcore/ui/utils";
import { FLOATING_SURFACE_CLASS } from "./floatingSurface.js";
import { DropdownMenuCheckboxItem, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger } from "@hardcore/ui/primitives/dropdown-menu";
import { ToolbarButton } from "./ToolbarButton.js";
import ToolPopover from "./ToolPopover.jsx";

const SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5];

/** Fullscreen camera motion is independent of animation playback. */
export default function OrbitMenu({ enabled, onEnabledChange, speed, onSpeedChange, onOpenChange }) {
  const speeds = SPEEDS.includes(speed) ? SPEEDS : [...SPEEDS, speed].sort((a, b) => a - b);
  return <ToolPopover allowInactive onOpenChange={onOpenChange} label="Orbit options"
    trigger={<ToolbarButton label="Orbit settings"><Orbit className="size-3.5" strokeWidth={1.5} aria-hidden="true" /></ToolbarButton>}>
    <DropdownMenuCheckboxItem checked={enabled} onCheckedChange={onEnabledChange}
      onSelect={event => event.preventDefault()}>Orbit</DropdownMenuCheckboxItem>
    <DropdownMenuSub>
      <DropdownMenuSubTrigger><span className="flex-1">Speed</span><span className="text-muted-foreground tabular-nums">{speed}×</span></DropdownMenuSubTrigger>
      <DropdownMenuSubContent className={cn(FLOATING_SURFACE_CLASS, "w-32")}>
        <DropdownMenuRadioGroup value={String(speed)} onValueChange={value => onSpeedChange(Number(value))}>
          {speeds.map(value => <DropdownMenuRadioItem key={value} value={String(value)}>{value}×</DropdownMenuRadioItem>)}
        </DropdownMenuRadioGroup>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  </ToolPopover>;
}

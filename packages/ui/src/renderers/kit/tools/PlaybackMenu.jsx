import { Settings } from "lucide-react";
import {
  DropdownMenuCheckboxItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator,
  DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger
} from "@hardcore/ui/primitives/dropdown-menu";
import { ToolbarButton } from "@hardcore/ui/primitives/toolbar-button";
import { cn } from "@hardcore/ui/utils";
import { FLOATING_SURFACE_CLASS } from "./floatingSurface.js";
import { PLAYBACK_SPEEDS } from "./playbar/ViewportAnimationBar.js";
import ToolPopover from "./ToolPopover.jsx";

export const ORBIT_SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5];

// A value's submenu: its name, the value in hand at the right against the chevron, and the radio list.
// `name` is the accessible name, for the two Speeds under their headings.
function SpeedSubmenu({ label, name = label, value, values, onChange }) {
  const options = values.includes(value) ? values : [...values, value].sort((a, b) => a - b);
  return <DropdownMenuSub>
    <DropdownMenuSubTrigger aria-label={`${name}: ${value}×`} className="[&>svg:last-child]:ml-0 [&>svg:last-child]:size-3">
      {label}<span className="ml-auto tabular-nums text-muted-foreground">{value}×</span>
    </DropdownMenuSubTrigger>
    <DropdownMenuSubContent aria-label={name} className={cn(FLOATING_SURFACE_CLASS, "min-w-24 data-[state=closed]:animate-none!")}>
      <DropdownMenuRadioGroup value={String(value)} onValueChange={next => onChange(Number(next))}>
        {options.map(option => <DropdownMenuRadioItem key={option} value={String(option)} className="tabular-nums">{option}×</DropdownMenuRadioItem>)}
      </DropdownMenuRadioGroup>
    </DropdownMenuSubContent>
  </DropdownMenuSub>;
}

/**
 * Preview mode's Playback settings: the cog at the right end of the playbar under the model, and
 * its dropdown, which opens upward. For a file with routines, **Animation** — the Routine (with
 * more than one), its Speed, Loop and Autoplay (whether entering preview starts it, the person's
 * across files) — then, for every file, **Orbit**: on or off, and its Speed. Ticking a checkbox
 * leaves the menu open. Play, pause and the scrubber are the playbar under the model.
 *
 * @param {{ animation?: object | null, autoplay: boolean, onAutoplayChange(value: boolean): void,
 *   orbit: boolean, onOrbitChange(value: boolean): void, orbitSpeed: number, onOrbitSpeedChange(value: number): void,
 *   onOpenChange?(open: boolean): void }} props  `animation` is the playbar runtime, or null for a static file.
 */
export default function PlaybackMenu({ animation = null, autoplay, onAutoplayChange, orbit, onOrbitChange, orbitSpeed,
  onOrbitSpeedChange, onOpenChange }) {
  const clips = animation?.clips || [];
  const keepOpen = event => event.preventDefault();
  return <ToolPopover allowInactive side="top" align="end" onOpenChange={onOpenChange} label="Playback settings" className="w-44"
    trigger={<ToolbarButton tooltip={false} label="Playback settings" className="size-6"><Settings className="size-3.5" strokeWidth={1.5} aria-hidden="true" /></ToolbarButton>}>
    {clips.length ? <>
      <DropdownMenuLabel className="text-muted-foreground">Animation</DropdownMenuLabel>
      {clips.length > 1 ? <DropdownMenuSub>
        <DropdownMenuSubTrigger className="[&>svg:last-child]:ml-0 [&>svg:last-child]:size-3">
          Routine<span className="ml-auto min-w-0 truncate pl-2 text-muted-foreground">{clips.find(clip => clip.id === animation.activeClipId)?.label}</span>
        </DropdownMenuSubTrigger>
        <DropdownMenuSubContent aria-label="Routine" className={cn(FLOATING_SURFACE_CLASS, "w-44 data-[state=closed]:animate-none!")}>
          <DropdownMenuRadioGroup value={animation.activeClipId} onValueChange={animation.onClipSelect}>
            {clips.map(clip => <DropdownMenuRadioItem key={clip.id} value={clip.id}>{clip.label}</DropdownMenuRadioItem>)}
          </DropdownMenuRadioGroup>
        </DropdownMenuSubContent>
      </DropdownMenuSub> : null}
      <SpeedSubmenu label="Speed" name="Animation speed" value={Number(animation.speed) || 1} values={PLAYBACK_SPEEDS} onChange={animation.onSpeedChange} />
      <DropdownMenuCheckboxItem checked={animation.loopEnabled !== false} onSelect={keepOpen}
        onCheckedChange={checked => animation.onLoopToggle(checked === true)}>Loop</DropdownMenuCheckboxItem>
      <DropdownMenuCheckboxItem checked={autoplay === true} onSelect={keepOpen}
        onCheckedChange={checked => onAutoplayChange?.(checked === true)}>Autoplay</DropdownMenuCheckboxItem>
      <DropdownMenuSeparator />
      <DropdownMenuLabel className="text-muted-foreground">Orbit</DropdownMenuLabel>
    </> : null}
    <DropdownMenuCheckboxItem checked={orbit} onSelect={keepOpen}
      onCheckedChange={checked => onOrbitChange(checked === true)}>Orbit</DropdownMenuCheckboxItem>
    <SpeedSubmenu label={clips.length ? "Speed" : "Orbit speed"} name="Orbit speed" value={orbitSpeed} values={ORBIT_SPEEDS} onChange={onOrbitSpeedChange} />
  </ToolPopover>;
}

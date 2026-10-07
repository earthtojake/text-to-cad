import { forwardRef } from "react";
import { ListVideo, Orbit, Settings } from "lucide-react";
import {
  DropdownMenuCheckboxItem, DropdownMenuRadioGroup, DropdownMenuRadioItem,
  DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger
} from "@text-to-cad/ui/primitives/dropdown-menu";
import { Button } from "@text-to-cad/ui/primitives/button";
import { TOOLBAR_ICON_BUTTON_CLASS } from "@text-to-cad/ui/primitives/toolbar-button";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { NAVBAR_CONTROL_CLASS } from "../../../lib/navbarRow.js";
import { PLAYBACK_SPEEDS } from "./playbar/ViewportAnimationBar.js";
import ToolPopover from "./ToolPopover.jsx";

// Preview's three menus: Orbit, in its corner, and the playbar's two, its Routines at its left end
// and its Playback settings at its right. Each trigger is lit while its menu is open.

export const ORBIT_SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5];

// The corner's buttons are the navbar's, as Display and Exit preview beside it are.
const CORNER_TRIGGER_CLASS = cn(NAVBAR_CONTROL_CLASS, "aria-expanded:bg-accent aria-expanded:text-accent-foreground");
// The playbar's are its transport's.
const PLAYBAR_TRIGGER_CLASS = cn(TOOLBAR_ICON_BUTTON_CLASS, "aria-expanded:bg-sidebar-accent aria-expanded:text-sidebar-accent-foreground");

// A value's submenu: its name, the value in hand at the right against the chevron, and the radio list.
// `name` is the accessible name, for the two Speeds.
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

/** A menu's icon button, named and, given a `hint` side, hinted by its name there. */
const MenuTrigger = forwardRef(function MenuTrigger({ label, hint = null, className, children, ...props }, ref) {
  const button = <Button ref={ref} type="button" variant="ghost" size="icon-xs" aria-label={label} className={className} {...props}>{children}</Button>;
  return hint ? <TooltipHint content={label} side={hint}>{button}</TooltipHint> : button;
});

const keepOpen = event => event.preventDefault();

/**
 * Preview's Orbit: the orbit icon at the left of its corner, before Display, which keeps its place
 * from the navbar, and its dropdown, which opens down from it: **Orbit** on or off, and its
 * **Speed**. Ticking it leaves the menu open. Orbit is the view's, not an animation's: every file
 * that previews has it, a static one too.
 *
 * @param {{ orbit: boolean, onOrbitChange(value: boolean): void, speed: number, onSpeedChange(value: number): void,
 *   onOpenChange?(open: boolean): void }} props
 */
export function OrbitMenu({ orbit, onOrbitChange, speed, onSpeedChange, onOpenChange }) {
  return <ToolPopover allowInactive side="bottom" align="end" onOpenChange={onOpenChange} label="Orbit" className="w-40"
    trigger={<MenuTrigger label="Orbit" hint="bottom" className={CORNER_TRIGGER_CLASS}><Orbit className="size-3.5" aria-hidden="true" /></MenuTrigger>}>
    <DropdownMenuCheckboxItem checked={orbit} onSelect={keepOpen}
      onCheckedChange={checked => onOrbitChange(checked === true)}>Orbit</DropdownMenuCheckboxItem>
    <SpeedSubmenu label="Speed" name="Orbit speed" value={speed} values={ORBIT_SPEEDS} onChange={onSpeedChange} />
  </ToolPopover>;
}

/**
 * The playbar's Routines, at its left end: the file's routines as a playlist, the one in hand
 * checked, opening up from its button. Choosing one plays it next and closes the list. A file
 * with one routine has nothing to choose, and so no list.
 *
 * @param {{ animation: object, onOpenChange?(open: boolean): void }} props  `animation` is the playbar runtime.
 */
export function RoutineMenu({ animation, onOpenChange }) {
  const clips = animation?.clips || [];
  if (clips.length < 2) return null;
  return <ToolPopover allowInactive side="top" align="start" onOpenChange={onOpenChange} label="Routines" className="w-44"
    trigger={<MenuTrigger label="Routines" hint="top" className={PLAYBAR_TRIGGER_CLASS}><ListVideo className="size-3.5" strokeWidth={1.5} aria-hidden="true" /></MenuTrigger>}>
    <DropdownMenuRadioGroup value={animation.activeClipId} onValueChange={animation.onClipSelect}>
      {clips.map(clip => <DropdownMenuRadioItem key={clip.id} value={clip.id}>
        <span className="min-w-0 truncate">{clip.label}</span>
      </DropdownMenuRadioItem>)}
    </DropdownMenuRadioGroup>
  </ToolPopover>;
}

/**
 * The playbar's Playback settings, at its right end: a cog whose dropdown opens up from it, with
 * the routine's **Speed**, **Loop**, and **Autoplay** (whether entering preview starts it). Ticking
 * a checkbox leaves the menu open.
 *
 * @param {{ animation: object, autoplay: boolean, onAutoplayChange(value: boolean): void,
 *   onOpenChange?(open: boolean): void }} props  `animation` is the playbar runtime.
 */
export default function PlaybackMenu({ animation, autoplay, onAutoplayChange, onOpenChange }) {
  return <ToolPopover allowInactive side="top" align="end" onOpenChange={onOpenChange} label="Playback settings" className="w-40"
    trigger={<MenuTrigger label="Playback settings" className={PLAYBAR_TRIGGER_CLASS}><Settings className="size-3.5" strokeWidth={1.5} aria-hidden="true" /></MenuTrigger>}>
    <SpeedSubmenu label="Speed" name="Animation speed" value={Number(animation.speed) || 1} values={PLAYBACK_SPEEDS} onChange={animation.onSpeedChange} />
    <DropdownMenuCheckboxItem checked={animation.loopEnabled !== false} onSelect={keepOpen}
      onCheckedChange={checked => animation.onLoopToggle(checked === true)}>Loop</DropdownMenuCheckboxItem>
    <DropdownMenuCheckboxItem checked={autoplay === true} onSelect={keepOpen}
      onCheckedChange={checked => onAutoplayChange?.(checked === true)}>Autoplay</DropdownMenuCheckboxItem>
  </ToolPopover>;
}

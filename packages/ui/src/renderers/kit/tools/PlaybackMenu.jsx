import { forwardRef } from "react";
import { Settings } from "lucide-react";
import {
  DropdownMenuCheckboxItem, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator,
  DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger
} from "@cad/ui/primitives/dropdown-menu";
import { Button } from "@cad/ui/primitives/button";
import { TOOLBAR_ICON_BUTTON_CLASS } from "@cad/ui/primitives/toolbar-button";
import { cn } from "@cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { PLAYBACK_SPEEDS, formatSeconds, playbarWords } from "./playbar/AnimationTimeControl.js";
import ToolPopover from "./ToolPopover.jsx";
import { useI18n } from "@cad/ui/i18n";

// The routine's playback settings (`PlaybackSettingsItems`), in Preview's playbar's cog (`PlaybackMenu`,
// `playbar/PreviewPlaybar.jsx`), opening from it (`side`), lit while its menu is open (the tools view's are the
// Animation tab's rows, `playbar/AnimationSection.jsx`); and
// Preview's Orbit speeds (`kit/shell/PreviewSettings.jsx`).

export const ORBIT_SPEEDS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5];

// The cog is a toolbar tile, as the section's Play beside it is.
const MENU_TRIGGER_CLASS = cn(TOOLBAR_ICON_BUTTON_CLASS, "aria-expanded:bg-sidebar-accent aria-expanded:text-sidebar-accent-foreground");

// A value's submenu: its name, the value in hand at the right against the chevron, and the radio list.
// `name` is the accessible name ("Animation speed").
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

/** The menu's icon button, named. */
const MenuTrigger = forwardRef(function MenuTrigger({ label, className, children, ...props }, ref) {
  return <Button ref={ref} type="button" variant="ghost" size="icon-xs" aria-label={label} className={className} {...props}>{children}</Button>;
});

const keepOpen = event => event.preventDefault();

/**
 * The routine's playback settings, as menu items: its **Speed** (a submenu) and **Loop**. Ticking the
 * checkbox leaves the menu open. Both are the file's, kept in its view.
 *
 * @param {{ animation: object }} props
 */
export function PlaybackSettingsItems({ animation }) {
  const { t } = useI18n();
  return <>
    <SpeedSubmenu label={t("playback.speed")} name={t("playback.animationSpeed")} value={Number(animation.speed) || 1} values={PLAYBACK_SPEEDS} onChange={animation.onSpeedChange} />
    <DropdownMenuCheckboxItem checked={animation.loopEnabled !== false} onSelect={keepOpen}
      onCheckedChange={checked => animation.onLoopToggle(checked === true)}>{t("playback.loop")}</DropdownMenuCheckboxItem>
  </>;
}

/**
 * The routines, where there are two or more, as menu items: a radio list, the one in hand ticked, each
 * with its duration muted at its right in tabular figures, then a rule. `onChoose(id)` is the choice.
 * @param {{ animation: object, onChoose(id: string): void }} props
 */
export function RoutineItems({ animation, onChoose }) {
  const { t } = useI18n();
  const clips = animation?.clips || [];
  if (clips.length < 2) return null;
  return <>
    <DropdownMenuRadioGroup value={animation.activeClipId} onValueChange={onChoose} aria-label={playbarWords(animation, t).list}>
      {clips.map(clip => <DropdownMenuRadioItem key={clip.id} value={clip.id} className="pr-8">
        <span className="min-w-0 truncate">{clip.label}</span>
        {Number(clip.duration) > 0 ? <span className="ml-auto pl-2 tabular-nums text-muted-foreground">{formatSeconds(clip.duration)}</span> : null}
      </DropdownMenuRadioItem>)}
    </DropdownMenuRadioGroup>
    <DropdownMenuSeparator />
  </>;
}

/**
 * A playbar's Playback settings, at the end of its row: a cog whose dropdown opens from it, with the
 * routine's playback settings (`PlaybackSettingsItems`) — after the routines where `onRoutine` is
 * given and there are two or more (`RoutineItems`: the tools view's playbar, whose row has no list of
 * its own).
 *
 * @param {{ animation: object,
 *   side?: "top" | "bottom", disabled?: boolean, onRoutine?: ((id: string) => void) | null, triggerClassName?: string }} props
 *   `animation` is the routine runtime; `side` is where the menu opens.
 */
export default function PlaybackMenu({ animation, side = "top", disabled = false, onRoutine = null, triggerClassName }) {
  const { t } = useI18n();
  const routines = Boolean(onRoutine) && (animation?.clips?.length || 0) > 1;
  return <ToolPopover allowInactive side={side} align="end" label={t("playback.settings")} className={routines ? "w-48" : "w-40"}
    trigger={<MenuTrigger label={t("playback.settings")} disabled={disabled} className={cn(MENU_TRIGGER_CLASS, triggerClassName)} data-playback-menu=""><Settings className="size-3.5" strokeWidth={1.5} aria-hidden="true" /></MenuTrigger>}>
    {routines ? <RoutineItems animation={animation} onChoose={onRoutine} /> : null}
    <PlaybackSettingsItems animation={animation} />
  </ToolPopover>;
}

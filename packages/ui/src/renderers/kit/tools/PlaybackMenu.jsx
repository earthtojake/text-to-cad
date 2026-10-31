import { forwardRef } from "react";
import { Settings } from "lucide-react";
import {
  DropdownMenuCheckboxItem, DropdownMenuRadioGroup, DropdownMenuRadioItem,
  DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger
} from "@text-to-cad/ui/primitives/dropdown-menu";
import { Button } from "@text-to-cad/ui/primitives/button";
import { TOOLBAR_ICON_BUTTON_CLASS } from "@text-to-cad/ui/primitives/toolbar-button";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { PLAYBACK_SPEEDS } from "./playbar/AnimationTimeControl.js";
import ToolPopover from "./ToolPopover.jsx";
import { useI18n } from "@text-to-cad/ui/i18n";

// The file sidebar's Animation section's Playback settings (`playbar/AnimationSection.jsx`), opening
// down from its cog (`side`), lit while its menu is open; and Preview's Orbit speeds
// (`kit/shell/PreviewSettings.jsx`).

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
 * The Animation section's Playback settings, at the end of its transport: a cog whose dropdown opens
 * from it, with the routine's **Speed**, **Loop**, and **Autoplay** (whether entering Preview
 * starts it). Ticking a checkbox leaves the menu open. All three are the file's, kept in its view.
 *
 * @param {{ animation: object, autoplay: boolean, onAutoplayChange(value: boolean): void,
 *   side?: "top" | "bottom", disabled?: boolean }} props
 *   `animation` is the routine runtime; `side` is where the menu opens.
 */
export default function PlaybackMenu({ animation, autoplay, onAutoplayChange, side = "top", disabled = false }) {
  const { t } = useI18n();
  return <ToolPopover allowInactive side={side} align="end" label={t("playback.settings")} className="w-40"
    trigger={<MenuTrigger label={t("playback.settings")} disabled={disabled} className={MENU_TRIGGER_CLASS}><Settings className="size-3.5" strokeWidth={1.5} aria-hidden="true" /></MenuTrigger>}>
    <SpeedSubmenu label={t("playback.speed")} name={t("playback.animationSpeed")} value={Number(animation.speed) || 1} values={PLAYBACK_SPEEDS} onChange={animation.onSpeedChange} />
    <DropdownMenuCheckboxItem checked={animation.loopEnabled !== false} onSelect={keepOpen}
      onCheckedChange={checked => animation.onLoopToggle(checked === true)}>{t("playback.loop")}</DropdownMenuCheckboxItem>
    <DropdownMenuCheckboxItem checked={autoplay === true} onSelect={keepOpen}
      onCheckedChange={checked => onAutoplayChange?.(checked === true)}>{t("playback.autoplay")}</DropdownMenuCheckboxItem>
  </ToolPopover>;
}

import { useEffect, useState } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@text-to-cad/ui/primitives/dropdown-menu";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";

/**
 * A settings popover under its own button: an ordinary dropdown, start-aligned unless `align`
 * says otherwise — preview mode's menus (`PlaybackMenu.jsx`: Orbit, opening down from preview's
 * corner, and the playbar's Routines and Playback settings, opening up from it). It is always
 * temporary. No tool on the strip has one: a tool's settings are its panel in the tool stack.
 *
 * It closes with no exit animation. A menu on its way out is still mounted, and its outside-
 * press layer still listens: a tap on the tool while the last menu was fading reopened the menu
 * at `pointerdown`, and the fading one then shut it again — the tap seemed to do nothing, or
 * only to take the stale menu away. Unmounting at once leaves no layer to hear that tap. The
 * primitive's `animate-out` is not a class `cn` knows to replace, so the override is important.
 */
export default function ToolPopover({ trigger, label, className, onOpenChange, allowInactive = false, align = "start", side = "bottom", children }) {
  const [open, setLocalOpen] = useState(false);
  const setOpen = value => {
    setLocalOpen(value);
    onOpenChange?.(value);
  };
  const active = allowInactive || trigger.props.active !== false;
  useEffect(() => { if (!active) setOpen(false); }, [active]);
  return <DropdownMenu open={open && active} onOpenChange={setOpen} modal={false}>
    <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
    <DropdownMenuContent side={side} align={align} sideOffset={8} collisionPadding={8} aria-label={label}
      className={cn(FLOATING_SURFACE_CLASS, "w-40 max-w-[calc(100vw-16px)] max-h-[min(24rem,var(--radix-popper-available-height))] data-[state=closed]:animate-none!", className)}
      onEscapeKeyDown={event => { event.stopPropagation(); setOpen(false); }}>
      {children}
    </DropdownMenuContent>
  </DropdownMenu>;
}

import { useEffect, useState } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@hardcore/ui/primitives/dropdown-menu";
import { cn } from "@hardcore/ui/utils";
import { FLOATING_SURFACE_CLASS } from "./floatingSurface.js";

/**
 * A tool's corner menu: an ordinary dropdown under its own button, start-aligned, which may
 * overlap the tool stack while it is open. It is always temporary; what a person keeps is a
 * panel in the stack.
 *
 * It closes with no exit animation. A menu on its way out is still mounted, and its outside-
 * press layer still listens: a tap on the tool while the last menu was fading reopened the menu
 * at `pointerdown`, and the fading one then shut it again — the tap seemed to do nothing, or
 * only to take the stale menu away. Unmounting at once leaves no layer to hear that tap. The
 * primitive's `animate-out` is not a class `cn` knows to replace, so the override is important.
 */
export default function ToolPopover({ trigger, label, className, open: controlledOpen, onOpenChange, onFocusOutside, allowInactive = false, children }) {
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? localOpen;
  const setOpen = value => {
    if (controlledOpen === undefined) setLocalOpen(value);
    onOpenChange?.(value);
  };
  const active = allowInactive || trigger.props.active !== false;
  useEffect(() => { if (!active) setOpen(false); }, [active]);
  return <DropdownMenu open={open && active} onOpenChange={setOpen} modal={false}>
    <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
    <DropdownMenuContent align="start" sideOffset={8} collisionPadding={8} aria-label={label}
      className={cn(FLOATING_SURFACE_CLASS, "w-40 max-w-[calc(100vw-16px)] max-h-[min(24rem,var(--radix-popper-available-height))] overflow-y-auto data-[state=closed]:animate-none!", className)}
      onFocusOutside={onFocusOutside}
      onEscapeKeyDown={event => { event.stopPropagation(); setOpen(false); }}>
      {children}
    </DropdownMenuContent>
  </DropdownMenu>;
}

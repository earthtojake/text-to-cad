import { useEffect, useState } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@hardcore/ui/primitives/dropdown-menu";
import { cn } from "@hardcore/ui/utils";

/** Corner options are always temporary; retained controls belong in the toolbar stack. */
export default function ToolPopover({ trigger, label, className, open: controlledOpen, onOpenChange, onFocusOutside, allowInactive = false, children }) {
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? localOpen;
  const setOpen = value => { if (controlledOpen === undefined) setLocalOpen(value); onOpenChange?.(value); };
  const active = allowInactive || trigger.props.active !== false;
  useEffect(() => { if (!active) setOpen(false); }, [active]);
  return <DropdownMenu open={open && active} onOpenChange={setOpen} modal={false}>
    <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
    <DropdownMenuContent align="end" sideOffset={8} collisionPadding={8} aria-label={label}
      className={cn("w-40 max-w-[calc(100vw-16px)] max-h-[min(24rem,var(--radix-popper-available-height))] overflow-y-auto text-tiny", className)}
      onFocusOutside={onFocusOutside}
      onEscapeKeyDown={event => { event.stopPropagation(); setOpen(false); }}>
      {children}
    </DropdownMenuContent>
  </DropdownMenu>;
}

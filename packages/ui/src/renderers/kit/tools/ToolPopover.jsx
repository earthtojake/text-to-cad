import { useEffect, useRef, useState } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "@hardcore/ui/primitives/dropdown-menu";
import { cn } from "@hardcore/ui/utils";
import { placementBesidePanels, useToolPanelStack } from "./toolPanelStack.js";

/** Corner options are always temporary; retained controls belong in the toolbar stack. */
export default function ToolPopover({ trigger, label, className, open: controlledOpen, onOpenChange, onFocusOutside, allowInactive = false, children }) {
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? localOpen;
  const stack = useToolPanelStack();
  const triggerRef = useRef(null);
  const [placement, setPlacement] = useState(null);
  const setOpen = value => {
    if (value) setPlacement(placementBesidePanels(stack?.current, triggerRef.current));
    if (controlledOpen === undefined) setLocalOpen(value);
    onOpenChange?.(value);
  };
  const active = allowInactive || trigger.props.active !== false;
  useEffect(() => { if (!active) setOpen(false); }, [active]);
  return <DropdownMenu open={open && active} onOpenChange={setOpen} modal={false}>
    <DropdownMenuTrigger asChild ref={triggerRef}>{trigger}</DropdownMenuTrigger>
    <DropdownMenuContent align={placement?.align ?? "end"} alignOffset={placement?.alignOffset ?? 0} sticky={placement ? "always" : "partial"} sideOffset={8} collisionPadding={8} aria-label={label}
      className={cn("w-40 max-w-[calc(100vw-16px)] max-h-[min(24rem,var(--radix-popper-available-height))] overflow-y-auto", className)}
      onFocusOutside={onFocusOutside}
      onEscapeKeyDown={event => { event.stopPropagation(); setOpen(false); }}>
      {children}
    </DropdownMenuContent>
  </DropdownMenu>;
}

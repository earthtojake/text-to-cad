import { X } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from "@text-to-cad/ui/primitives/popover";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { NAVBAR_CONTROL_CLASS } from "../../../lib/navbarRow.js";
import { PerspectiveProjectionIcon } from "../camera/ProjectionModeIcons.js";
import { FLOATING_SURFACE_CLASS } from "../tools/floatingSurface.js";
import { TOOL_PANEL_BUTTON_CLASS } from "../tools/ToolPanel.jsx";

/**
 * Display: a 3D view's settings (`children`: `useRendererShell`'s `frame.display`), a dropdown from
 * its button in the navbar, between the host's Settings and Preview. Its icon is the perspective
 * box. It is not a tool: opening it leaves the tool in hand as it is. It opens down from its button,
 * end-aligned, as wide as its two-a-row settings need (19rem: Projection's "Orthographic" in full
 * beside the host's appearance control), and never taller than the room below it: its sections
 * scroll inside it. It goes as any popover does: Escape, a press outside it, its button again, or the X
 * at the end of its first heading (`DisplayPopoverClose`). It closes with no exit animation, so a
 * quick second press always reaches the button.
 * @param {{ open: boolean, onOpenChange(open: boolean): void, disabled?: boolean, children: import("react").ReactNode }} props
 */
export default function DisplayPopover({ open, onOpenChange, disabled = false, children }) {
  return <Popover open={open && !disabled} onOpenChange={onOpenChange} modal={false}>
    <TooltipHint content="Display">
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="icon-xs" aria-label="Display" aria-pressed={open} disabled={disabled}
          className={NAVBAR_CONTROL_CLASS}>
          <PerspectiveProjectionIcon className="size-3.5" />
        </Button>
      </PopoverTrigger>
    </TooltipHint>
    <PopoverContent side="bottom" align="end" sideOffset={6} collisionPadding={8}
      aria-label="Display settings" data-display-popover=""
      className={cn(FLOATING_SURFACE_CLASS, "flex w-76 max-h-[var(--radix-popover-content-available-height)] flex-col overflow-hidden p-0 text-tiny data-[state=closed]:animate-none!")}>
      <ScrollArea className="min-h-0 flex-1">{children}</ScrollArea>
    </PopoverContent>
  </Popover>;
}

/** The X at the end of Display's first heading, after its Reset: it closes the dropdown it is drawn in. */
export function DisplayPopoverClose() {
  return <PopoverClose aria-label="Close display settings" className={TOOL_PANEL_BUTTON_CLASS}>
    <X className="size-3" aria-hidden="true" />
  </PopoverClose>;
}

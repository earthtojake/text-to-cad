import { Settings, X } from "lucide-react";
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from "@text-to-cad/ui/primitives/popover";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../tools/floatingSurface.js";
import { TOOL_PANEL_BUTTON_CLASS } from "../tools/ToolPanel.jsx";

/**
 * Display's settings: an ordinary popover from its button in the viewport's top-right bar,
 * before Preview (in preview, before its X), end-aligned under it. Its button is the settings cog. It is not a tool — opening it leaves the tool in hand
 * as it is — and it goes as any popover does: Escape, its button, its X, or a press anywhere
 * outside it, the model included. It is never taller than the viewer: its
 * sections scroll inside it. It closes with no exit animation, so a quick second press always
 * reaches the button.
 *
 * @param {{ open: boolean, onOpenChange(open: boolean): void, disabled?: boolean, children: import("react").ReactNode }} props
 *   `children`: the Display sections (`useRendererShell`'s `frame.display`).
 */
export default function DisplayPopover({ open, onOpenChange, disabled = false, children }) {
  return <Popover open={open && !disabled} onOpenChange={onOpenChange} modal={false}>
    <PopoverTrigger asChild>
      <ToolbarButton label="Display settings" active={open} aria-pressed={open} disabled={disabled}
        className={cn("size-5", !open && "bg-transparent hover:bg-transparent dark:hover:bg-transparent")}>
        <Settings className="size-3" strokeWidth={1.5} aria-hidden="true" />
      </ToolbarButton>
    </PopoverTrigger>
    <PopoverContent align="end" sideOffset={6} collisionPadding={14} aria-label="Display settings" data-display-popover=""
      // The X takes the Display section heading's right end; its Reset moves in beside it.
      className={cn(FLOATING_SURFACE_CLASS, "relative flex w-64 max-h-[var(--radix-popover-content-available-height)] flex-col overflow-hidden p-0 text-tiny data-[state=closed]:animate-none!",
        "[&_[data-settings-section=display]_[data-settings-section-heading]>div]:right-7")}>
      <ScrollArea className="min-h-0 flex-1">{children}</ScrollArea>
      <PopoverClose aria-label="Close display settings" className={cn(TOOL_PANEL_BUTTON_CLASS, "absolute right-1 top-1")}>
        <X className="size-3" aria-hidden="true" />
      </PopoverClose>
    </PopoverContent>
  </Popover>;
}

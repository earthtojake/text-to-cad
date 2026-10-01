import { Settings, X } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from "@text-to-cad/ui/primitives/popover";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../tools/floatingSurface.js";
import { TOOL_PANEL_BUTTON_CLASS } from "../tools/ToolPanel.jsx";

/**
 * Display's settings: an ordinary popover from its button among the view's controls in the
 * navbar, before Preview, opening down from it, end-aligned. Its button is the settings cog. It is
 * not a tool — opening it leaves the tool in hand as it is — and it goes as any popover does:
 * Escape, its button, its X, or a press anywhere outside it, the model included. It is never
 * taller than the room below it: its sections scroll inside it. It closes with no exit animation,
 * so a quick second press always reaches the button.
 * @param {{ open: boolean, onOpenChange(open: boolean): void, disabled?: boolean, children: import("react").ReactNode }} props
 *   `children`: the Display sections (`useRendererShell`'s `frame.display`).
 */
export default function DisplayPopover({ open, onOpenChange, disabled = false, children }) {
  return <Popover open={open && !disabled} onOpenChange={onOpenChange} modal={false}>
    <TooltipHint content="Display settings">
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="icon-xs" aria-label="Display settings" aria-pressed={open} disabled={disabled}
          className="size-6 text-muted-foreground hover:text-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground">
          <Settings className="size-3.5" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
    </TooltipHint>
    <PopoverContent side="bottom" align="end" sideOffset={6} collisionPadding={8}
      aria-label="Display settings" data-display-popover=""
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

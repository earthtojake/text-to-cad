import { Settings, X } from "lucide-react";
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from "@text-to-cad/ui/primitives/popover";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { ToolbarButton } from "@text-to-cad/ui/primitives/toolbar-button";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../tools/floatingSurface.js";
import { TOOL_PANEL_BUTTON_CLASS } from "../tools/ToolPanel.jsx";
import { VIEWPORT_INSET_PX, VIEWPORT_TOP_BAR_PX } from "./viewportLayout.js";

// However tall its sections, it stops below the tool strip at the top of the view.
const COLLISION_PADDING = Object.freeze({ top: VIEWPORT_TOP_BAR_PX + VIEWPORT_INSET_PX * 2, right: 14, bottom: 14, left: 14 });

/**
 * Display's settings: an ordinary popover from its button in the view's actions on top of the
 * cube, before Preview (in preview, before its X), opening up from it, start-aligned. Its button is the settings cog. It is not a tool — opening it leaves the tool in hand
 * as it is — and it goes as any popover does: Escape, its button, its X, or a press anywhere
 * outside it, the model included. It is never taller than the viewer below the tool strip: its
 * sections scroll inside it. It closes with no exit animation, so a quick second press always
 * reaches the button.
 *
 * @param {{ open: boolean, onOpenChange(open: boolean): void, disabled?: boolean, boundary?: Element | null,
 *   children: import("react").ReactNode }} props
 *   `children`: the Display sections (`useRendererShell`'s `frame.display`). `boundary`: the
 *   viewer, whose top (not the page's) the popover stays below the tool strip of.
 */
export default function DisplayPopover({ open, onOpenChange, disabled = false, boundary = null, children }) {
  return <Popover open={open && !disabled} onOpenChange={onOpenChange} modal={false}>
    <PopoverTrigger asChild>
      <ToolbarButton label="Display settings" tooltipSide="top" active={open} aria-pressed={open} disabled={disabled}
        className={cn("size-5", !open && "bg-transparent hover:bg-transparent dark:hover:bg-transparent")}>
        <Settings className="size-3" strokeWidth={1.5} aria-hidden="true" />
      </ToolbarButton>
    </PopoverTrigger>
    <PopoverContent side="top" align="start" sideOffset={6} collisionPadding={COLLISION_PADDING} collisionBoundary={boundary || undefined}
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

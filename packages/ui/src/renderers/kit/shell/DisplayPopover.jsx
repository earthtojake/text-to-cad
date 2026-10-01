import { Settings, X } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from "@text-to-cad/ui/primitives/popover";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { CommunityLinks } from "../../../file-viewer/navigation/NavbarLinks.jsx";
import { useViewerHost } from "../../../host/context.js";
import { FLOATING_SURFACE_CLASS } from "../tools/floatingSurface.js";
import { TOOL_PANEL_BUTTON_CLASS } from "../tools/ToolPanel.jsx";

/**
 * Settings: an ordinary popover from the settings cog among the view's controls in the navbar,
 * before Preview, opening down from it, end-aligned. Its header is "Settings", the version this
 * host runs in gray beside it, then GitHub and Discord as icon links and the X at its right end;
 * under it, the Display settings (`children`), whose own heading keeps its Reset. It is not a
 * tool — opening it leaves the tool in hand as it is — and it goes as any popover does: Escape,
 * its button, its X, or a press anywhere outside it, the model included. It is never taller than
 * the room below it: its sections scroll inside it, under the header. It closes with no exit
 * animation, so a quick second press always reaches the button.
 * @param {{ open: boolean, onOpenChange(open: boolean): void, disabled?: boolean, children: import("react").ReactNode }} props
 *   `children`: the Display sections (`useRendererShell`'s `frame.display`).
 */
export default function DisplayPopover({ open, onOpenChange, disabled = false, children }) {
  const { links } = useViewerHost();
  return <Popover open={open && !disabled} onOpenChange={onOpenChange} modal={false}>
    <TooltipHint content="Settings">
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="icon-xs" aria-label="Settings" aria-pressed={open} disabled={disabled}
          className="size-6 text-muted-foreground hover:text-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground">
          <Settings className="size-3.5" aria-hidden="true" />
        </Button>
      </PopoverTrigger>
    </TooltipHint>
    <PopoverContent side="bottom" align="end" sideOffset={6} collisionPadding={8}
      aria-label="Settings" data-display-popover=""
      className={cn(FLOATING_SURFACE_CLASS, "flex w-64 max-h-[var(--radix-popover-content-available-height)] flex-col overflow-hidden p-0 text-tiny data-[state=closed]:animate-none!")}>
      <div className="flex h-8 shrink-0 items-center gap-1.5 border-b border-border pl-2.5 pr-1" data-settings-header="">
        <h2 className="text-xs font-semibold text-foreground">Settings</h2>
        {links?.version ? <span className="text-tiny tabular-nums text-muted-foreground" data-settings-version="">v{links.version}</span> : null}
        <div className="ml-auto flex items-center gap-0.5">
          {links ? <CommunityLinks links={links} /> : null}
          <PopoverClose aria-label="Close settings" className={TOOL_PANEL_BUTTON_CLASS}>
            <X className="size-3" aria-hidden="true" />
          </PopoverClose>
        </div>
      </div>
      <ScrollArea className="min-h-0 flex-1">{children}</ScrollArea>
    </PopoverContent>
  </Popover>;
}
